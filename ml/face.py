"""Face detection, embedding and recognition built on dlib.

Models are loaded once per process. The recognition classifier is rebuilt
whenever the set of known students changes (compared by a fingerprint of
their ids), mirroring the Streamlit cache-clearing behaviour.
"""
from __future__ import annotations

import io
import threading
from dataclasses import dataclass

import numpy as np

_models_lock = threading.Lock()
_models = None

_classifier_lock = threading.Lock()
_classifier_cache: dict = {"fingerprint": None, "model": None}


def _load_models():
    global _models
    if _models is None:
        with _models_lock:
            if _models is None:
                import dlib
                import face_recognition_models

                detector = dlib.get_frontal_face_detector()
                shape_predictor = dlib.shape_predictor(face_recognition_models.pose_predictor_model_location())
                face_rec = dlib.face_recognition_model_v1(face_recognition_models.face_recognition_model_location())
                _models = (detector, shape_predictor, face_rec)
    return _models


def image_bytes_to_array(data: bytes) -> np.ndarray:
    """Decode uploaded image bytes into an RGB uint8 array."""
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        return np.array(img)


def get_face_embeddings(image_np: np.ndarray) -> list[np.ndarray]:
    """Return one 128-d embedding per face found in the image."""
    detector, shape_predictor, face_rec = _load_models()
    faces = detector(image_np, 1)
    encodings = []
    for face in faces:
        shape = shape_predictor(image_np, face)
        descriptor = face_rec.compute_face_descriptor(image_np, shape, 1)
        encodings.append(np.array(descriptor))
    return encodings


@dataclass
class FaceModel:
    ids: list[int]
    embeddings: list[np.ndarray]
    clf: object | None  # sklearn SVC when >= 2 classes, else None

    def predict_id(self, encoding: np.ndarray) -> int:
        if self.clf is not None:
            return int(self.clf.predict([encoding])[0])
        return int(self.ids[0])

    def distance_to(self, student_id: int, encoding: np.ndarray) -> float:
        stored = self.embeddings[self.ids.index(student_id)]
        return float(np.linalg.norm(stored - encoding))


def build_face_model(students: list[tuple[int, list[float]]]) -> FaceModel | None:
    """Build a recognition model from (student_id, embedding) pairs."""
    ids, embeddings = [], []
    for student_id, embedding in students:
        if embedding:
            ids.append(int(student_id))
            embeddings.append(np.asarray(embedding, dtype=float))
    if not ids:
        return None

    clf = None
    if len(set(ids)) >= 2:
        from sklearn.svm import SVC

        clf = SVC(kernel="linear", probability=True, class_weight="balanced")
        clf.fit(np.vstack(embeddings), ids)
    return FaceModel(ids=ids, embeddings=embeddings, clf=clf)


def get_face_model(students: list[tuple[int, list[float]]]) -> FaceModel | None:
    """Cached wrapper around build_face_model keyed on the student ids present."""
    fingerprint = tuple(sorted(int(sid) for sid, emb in students if emb))
    with _classifier_lock:
        if _classifier_cache["fingerprint"] != fingerprint:
            _classifier_cache["model"] = build_face_model(students)
            _classifier_cache["fingerprint"] = fingerprint
        return _classifier_cache["model"]


def invalidate_face_model():
    with _classifier_lock:
        _classifier_cache["fingerprint"] = None
        _classifier_cache["model"] = None


def recognise_faces(
    image_np: np.ndarray,
    students: list[tuple[int, list[float]]],
    threshold: float = 0.6,
) -> tuple[set[int], int]:
    """Identify known students in an image.

    Returns (set of recognised student ids, number of faces detected).
    """
    encodings = get_face_embeddings(image_np)
    model = get_face_model(students)
    recognised: set[int] = set()
    if model is None or not encodings:
        return recognised, len(encodings)

    for encoding in encodings:
        predicted = model.predict_id(encoding)
        if model.distance_to(predicted, encoding) <= threshold:
            recognised.add(predicted)
    return recognised, len(encodings)
