"""Business logic shared by the dashboards and JSON endpoints."""
from __future__ import annotations

import base64
import io
from collections import OrderedDict
from datetime import datetime

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import Student

from .models import AttendanceLog, Enrollment, Subject


# ---------------------------------------------------------------- subjects --

def subjects_with_stats(teacher):
    """Teacher's subjects annotated with student and class-session counts."""
    return (
        Subject.objects.filter(teacher=teacher)
        .annotate(
            total_students=Count("enrollments", distinct=True),
            total_classes=Count("attendance_logs__session_at", distinct=True),
        )
        .order_by("-created_at")
    )


def create_subject(teacher, subject_code, name, section):
    subject_code = (subject_code or "").strip().upper()
    name = (name or "").strip()
    section = (section or "").strip()
    if not (subject_code and name and section):
        raise ValueError("Please fill in the subject code, name and section.")
    if Subject.objects.filter(subject_code__iexact=subject_code).exists():
        raise ValueError(f"Subject code {subject_code} is already in use.")
    return Subject.objects.create(teacher=teacher, subject_code=subject_code, name=name, section=section)


def make_join_qr_data_url(join_url: str) -> str:
    import segno

    qr = segno.make(join_url, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=8, border=1, dark="#1a1a2e", light="#ffffff")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# -------------------------------------------------------------- enrolment --

ENROLL_NOT_FOUND = "not_found"
ENROLL_ALREADY = "already_enrolled"
ENROLL_OK = "enrolled"


def find_subject_by_code(code: str):
    code = (code or "").strip()
    if not code:
        return None
    return Subject.objects.filter(subject_code__iexact=code).select_related("teacher").first()


def enroll_by_code(student, code: str):
    subject = find_subject_by_code(code)
    if subject is None:
        return ENROLL_NOT_FOUND, None
    return enroll(student, subject), subject


def enroll(student, subject):
    try:
        with transaction.atomic():
            Enrollment.objects.create(student=student, subject=subject)
    except IntegrityError:
        return ENROLL_ALREADY
    return ENROLL_OK


def unenroll(student, subject_id) -> bool:
    deleted, _ = Enrollment.objects.filter(student=student, subject_id=subject_id).delete()
    return deleted > 0


def student_subjects_with_stats(student):
    """Enrolled subjects for a student with total sessions and attended counts."""
    enrollments = Enrollment.objects.filter(student=student).select_related("subject", "subject__teacher")
    stats = {
        row["subject_id"]: {"total": row["total"], "attended": row["attended"]}
        for row in AttendanceLog.objects.filter(student=student)
        .values("subject_id")
        .annotate(total=Count("id"), attended=Count("id", filter=Q(is_present=True)))
    }

    result = []
    for enrollment in enrollments:
        subject = enrollment.subject
        s = stats.get(subject.pk, {"total": 0, "attended": 0})
        percent = round(100 * s["attended"] / s["total"]) if s["total"] else None
        result.append({"subject": subject, "total": s["total"], "attended": s["attended"], "percent": percent})
    return result


# ------------------------------------------------------------- attendance --

def enrolled_students(subject):
    return Student.objects.filter(enrollments__subject=subject).order_by("name")


def all_face_profiles():
    return [(s.pk, s.face_embedding) for s in Student.objects.exclude(face_embedding=None).only("pk", "face_embedding")]


def build_review(subject, evidence: dict[int, str], source: str):
    """Turn recognition evidence into a review payload the UI can confirm.

    evidence maps student_id -> a human readable "why" (photo names or a score).
    """
    session_at = timezone.now().replace(microsecond=0)
    rows = []
    for student in enrolled_students(subject):
        why = evidence.get(student.pk)
        rows.append(
            {
                "student_id": student.pk,
                "name": student.name,
                "source": why if why else "-",
                "is_present": bool(why),
            }
        )
    present = sum(1 for r in rows if r["is_present"])
    return {
        "subject_id": subject.pk,
        "subject": f"{subject.name} ({subject.subject_code})",
        "session_at": session_at.isoformat(),
        "source": source,
        "present": present,
        "total": len(rows),
        "rows": rows,
    }


def parse_session_at(value: str | None):
    if not value:
        return timezone.now().replace(microsecond=0)
    parsed = datetime.fromisoformat(value)
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed.replace(microsecond=0)


def save_attendance(subject, session_at, entries: list[dict], source: str = "face") -> int:
    """Persist one attendance log per enrolled student in `entries`."""
    enrolled_ids = set(enrolled_students(subject).values_list("pk", flat=True))
    logs = []
    for entry in entries:
        try:
            student_id = int(entry.get("student_id"))
        except (TypeError, ValueError):
            continue
        if student_id not in enrolled_ids:
            continue
        logs.append(
            AttendanceLog(
                student_id=student_id,
                subject=subject,
                session_at=session_at,
                is_present=bool(entry.get("is_present")),
                source=source,
            )
        )
    AttendanceLog.objects.bulk_create(logs)
    return len(logs)


def session_summaries(teacher):
    """Attendance sessions for a teacher, newest first, with per-student detail."""
    logs = (
        AttendanceLog.objects.filter(subject__teacher=teacher)
        .select_related("subject", "student")
        .order_by("-session_at", "student__name")
    )
    sessions: "OrderedDict[tuple, dict]" = OrderedDict()
    for log in logs:
        key = (log.subject_id, log.session_at)
        if key not in sessions:
            sessions[key] = {
                "session_at": log.session_at,
                "subject": log.subject,
                "source": log.source,
                "present": 0,
                "total": 0,
                "students": [],
            }
        entry = sessions[key]
        entry["total"] += 1
        entry["present"] += 1 if log.is_present else 0
        entry["students"].append({"name": log.student.name, "is_present": log.is_present})
    return list(sessions.values())
