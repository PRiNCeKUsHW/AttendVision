"""JSON endpoints used by the interactive dashboards."""
import json

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from accounts.session import student_required, teacher_required
from ml.face import image_bytes_to_array, recognise_faces
from ml.voice import process_bulk_audio

from . import services
from .models import Subject


def _error(message, status=400):
    return JsonResponse({"ok": False, "error": message}, status=status)


def _json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return None


def _teacher_subject(request, subject_id):
    return get_object_or_404(Subject, pk=subject_id, teacher=request.teacher)


# ----------------------------------------------------------------- teacher --

@teacher_required
@require_POST
def create_subject(request):
    data = _json_body(request)
    if data is None:
        return _error("Invalid request body.")
    try:
        subject = services.create_subject(
            request.teacher, data.get("subject_code"), data.get("name"), data.get("section")
        )
    except ValueError as exc:
        return _error(str(exc))
    return JsonResponse(
        {"ok": True, "subject": {"id": subject.pk, "code": subject.subject_code, "name": subject.name}}
    )


@teacher_required
@require_POST
def analyse_faces(request):
    subject = _teacher_subject(request, request.POST.get("subject_id"))
    photos = request.FILES.getlist("photos")
    if not photos:
        return _error("Add at least one classroom photo first.")
    if not services.enrolled_students(subject).exists():
        return _error("No students are enrolled in this subject yet.")

    profiles = services.all_face_profiles()
    evidence: dict[int, list[str]] = {}
    for index, upload in enumerate(photos, start=1):
        try:
            image = image_bytes_to_array(upload.read())
        except Exception:
            return _error(f"Photo {index} could not be read.")
        recognised, _ = recognise_faces(image, profiles, threshold=settings.FACE_MATCH_THRESHOLD)
        for student_id in recognised:
            evidence.setdefault(student_id, []).append(f"Photo {index}")

    review = services.build_review(subject, {k: ", ".join(v) for k, v in evidence.items()}, source="face")
    return JsonResponse({"ok": True, "review": review})


@teacher_required
@require_POST
def analyse_voice(request):
    subject = _teacher_subject(request, request.POST.get("subject_id"))
    audio = request.FILES.get("audio")
    if not audio:
        return _error("Record some classroom audio first.")
    students = list(services.enrolled_students(subject))
    if not students:
        return _error("No students are enrolled in this subject yet.")
    candidates = {s.pk: s.voice_embedding for s in students if s.voice_embedding}
    if not candidates:
        return _error("None of the enrolled students have a voice profile yet.")

    try:
        scores = process_bulk_audio(audio.read(), candidates, threshold=settings.VOICE_MATCH_THRESHOLD)
    except Exception:
        return _error("Could not process that audio. Please record again.")

    review = services.build_review(
        subject, {sid: f"match {score:.2f}" for sid, score in scores.items()}, source="voice"
    )
    return JsonResponse({"ok": True, "review": review})


@teacher_required
@require_POST
def save_attendance(request):
    data = _json_body(request)
    if data is None:
        return _error("Invalid request body.")
    subject = _teacher_subject(request, data.get("subject_id"))
    try:
        session_at = services.parse_session_at(data.get("session_at"))
    except ValueError:
        return _error("Invalid session time.")
    entries = data.get("rows") or []
    if not isinstance(entries, list) or not entries:
        return _error("Nothing to save.")
    source = data.get("source") if data.get("source") in ("face", "voice") else "face"
    saved = services.save_attendance(subject, session_at, entries, source=source)
    return JsonResponse({"ok": True, "saved": saved})


# ----------------------------------------------------------------- student --

@student_required
@require_POST
def enroll(request):
    data = _json_body(request)
    if data is None:
        return _error("Invalid request body.")
    code = (data.get("code") or "").strip()
    if not code:
        return _error("Please enter a subject code.")
    status, subject = services.enroll_by_code(request.student, code)
    if status == services.ENROLL_NOT_FOUND:
        return _error("No subject found with that code.", status=404)
    if status == services.ENROLL_ALREADY:
        return _error(f"You're already enrolled in {subject.name}.")
    return JsonResponse(
        {"ok": True, "subject": {"id": subject.pk, "name": subject.name, "code": subject.subject_code}}
    )


@student_required
@require_POST
def unenroll(request):
    data = _json_body(request)
    if data is None:
        return _error("Invalid request body.")
    if not services.unenroll(request.student, data.get("subject_id")):
        return _error("You're not enrolled in that subject.", status=404)
    return JsonResponse({"ok": True})
