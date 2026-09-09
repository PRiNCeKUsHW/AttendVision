"""Speaker embedding and identification built on Resemblyzer.

Audio is expected as bytes of a format librosa can decode without ffmpeg
(the browser sends 16 kHz mono WAV).
"""
from __future__ import annotations

import io
import threading

import numpy as np

_encoder = None
_encoder_lock = threading.Lock()

SAMPLE_RATE = 16000


def _load_encoder():
    global _encoder
    if _encoder is None:
        with _encoder_lock:
            if _encoder is None:
                from resemblyzer import VoiceEncoder

                _encoder = VoiceEncoder()
    return _encoder


def _load_audio(audio_bytes: bytes):
    import librosa

    audio, _ = librosa.load(io.BytesIO(audio_bytes), sr=SAMPLE_RATE, mono=True)
    return audio


def get_voice_embedding(audio_bytes: bytes) -> list[float] | None:
    """Embed a single-speaker recording. Returns None if the audio is unusable."""
    from resemblyzer import preprocess_wav

    try:
        audio = _load_audio(audio_bytes)
        wav = preprocess_wav(audio)
        if len(wav) == 0:
            return None
        return _load_encoder().embed_utterance(wav).tolist()
    except Exception:
        return None


def identify_speaker(embedding, candidates: dict[int, list[float]], threshold: float = 0.65):
    """Return (student_id, score) for the best-matching candidate above threshold."""
    if embedding is None or not candidates:
        return None, 0.0
    best_id, best_score = None, -1.0
    vec = np.asarray(embedding, dtype=float)
    for student_id, stored in candidates.items():
        if not stored:
            continue
        score = float(np.dot(vec, np.asarray(stored, dtype=float)))
        if score > best_score:
            best_id, best_score = student_id, score
    if best_score >= threshold:
        return best_id, best_score
    return None, best_score


def process_bulk_audio(audio_bytes: bytes, candidates: dict[int, list[float]], threshold: float = 0.65) -> dict[int, float]:
    """Split classroom audio into voiced segments and identify each speaker.

    Returns {student_id: best_similarity_score} for every recognised student.
    """
    import librosa
    from resemblyzer import preprocess_wav

    audio = _load_audio(audio_bytes)
    segments = librosa.effects.split(audio, top_db=30)
    encoder = _load_encoder()
    results: dict[int, float] = {}
    min_len = int(SAMPLE_RATE * 0.5)

    for start, end in segments:
        if end - start < min_len:
            continue
        wav = preprocess_wav(audio[start:end])
        if len(wav) == 0:
            continue
        embedding = encoder.embed_utterance(wav)
        student_id, score = identify_speaker(embedding, candidates, threshold)
        if student_id is not None and score > results.get(student_id, -1.0):
            results[student_id] = round(score, 3)
    return results
