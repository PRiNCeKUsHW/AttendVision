"""Helpers for the session-based teacher/student login used across the app."""
from functools import wraps

from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from .models import Student, Teacher

TEACHER_KEY = "teacher_id"
STUDENT_KEY = "student_id"


def login_teacher(request, teacher):
    request.session.pop(STUDENT_KEY, None)
    request.session[TEACHER_KEY] = teacher.pk


def login_student(request, student):
    request.session.pop(TEACHER_KEY, None)
    request.session[STUDENT_KEY] = student.pk


def logout(request):
    request.session.flush()


def current_teacher(request):
    if not hasattr(request, "_cached_teacher"):
        pk = request.session.get(TEACHER_KEY)
        request._cached_teacher = Teacher.objects.filter(pk=pk).first() if pk else None
    return request._cached_teacher


def current_student(request):
    if not hasattr(request, "_cached_student"):
        pk = request.session.get(STUDENT_KEY)
        request._cached_student = Student.objects.filter(pk=pk).first() if pk else None
    return request._cached_student


def _guard(getter, login_url_name, attr):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            user = getter(request)
            if user is None:
                wants_json = request.headers.get("Accept", "").startswith("application/json") or request.path.startswith(
                    ("/teacher/api/", "/student/api/")
                )
                if wants_json:
                    return JsonResponse({"ok": False, "error": "Please log in first."}, status=401)
                return redirect(f"{reverse(login_url_name)}?next={request.get_full_path()}")
            setattr(request, attr, user)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


teacher_required = _guard(current_teacher, "accounts:teacher_login", "teacher")
student_required = _guard(current_student, "accounts:student_login", "student")
