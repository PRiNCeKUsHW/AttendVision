from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from ml.face import get_face_embeddings, image_bytes_to_array, invalidate_face_model, recognise_faces
from ml.voice import get_voice_embedding

from . import session
from .models import Student, Teacher


def _safe_next(request, fallback):
    """Return the requested `next` URL only if it stays on this host."""
    nxt = request.GET.get("next") or request.POST.get("next")
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return nxt
    return fallback


def home(request):
    return render(request, "home.html")


# ----------------------------------------------------------------- teacher --

@require_http_methods(["GET", "POST"])
def teacher_login(request):
    if session.current_teacher(request):
        return redirect("classroom:teacher_dashboard")
    error = None
    username = ""
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        teacher = Teacher.objects.filter(username__iexact=username).first()
        if teacher and teacher.check_password(password):
            session.login_teacher(request, teacher)
            messages.success(request, f"Welcome back, {teacher.name}!")
            return redirect(_safe_next(request, reverse("classroom:teacher_dashboard")))
        error = "Invalid username and password combination."
    return render(
        request,
        "accounts/teacher_login.html",
        {"error": error, "username": username, "next": request.GET.get("next", "")},
    )


@require_http_methods(["GET", "POST"])
def teacher_register(request):
    if session.current_teacher(request):
        return redirect("classroom:teacher_dashboard")
    error = None
    form = {"username": "", "name": ""}
    if request.method == "POST":
        form = {
            "username": request.POST.get("username", "").strip(),
            "name": request.POST.get("name", "").strip(),
        }
        password = request.POST.get("password", "")
        confirm = request.POST.get("password_confirm", "")
        if not (form["username"] and form["name"] and password):
            error = "All fields are required."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif password != confirm:
            error = "Passwords do not match."
        elif Teacher.objects.filter(username__iexact=form["username"]).exists():
            error = "That username is already taken."
        else:
            teacher = Teacher(username=form["username"], name=form["name"])
            teacher.set_password(password)
            teacher.save()
            messages.success(request, "Profile created! You can log in now.")
            return redirect("accounts:teacher_login")
    return render(request, "accounts/teacher_register.html", {"error": error, "form": form})


@require_POST
def logout_view(request):
    session.logout(request)
    return redirect("accounts:home")


# ----------------------------------------------------------------- student --

def student_login(request):
    if session.current_student(request):
        return redirect(_safe_next(request, reverse("classroom:student_dashboard")))
    return render(request, "accounts/student_login.html", {"next": request.GET.get("next", "")})


def _read_image(request):
    upload = request.FILES.get("image")
    if not upload:
        return None, JsonResponse({"ok": False, "error": "No image received."}, status=400)
    try:
        return image_bytes_to_array(upload.read()), None
    except Exception:
        return None, JsonResponse({"ok": False, "error": "Could not read that image."}, status=400)


@require_POST
def student_face_login(request):
    """Recognise the face in the uploaded snapshot and log the student in."""
    image, err = _read_image(request)
    if err:
        return err

    profiles = [(s.pk, s.face_embedding) for s in Student.objects.exclude(face_embedding=None)]
    recognised, num_faces = recognise_faces(image, profiles, threshold=settings.FACE_MATCH_THRESHOLD)

    if num_faces == 0:
        return JsonResponse({"ok": True, "status": "no_face", "message": "No face found. Move closer to the camera."})
    if num_faces > 1:
        return JsonResponse(
            {"ok": True, "status": "multiple_faces", "message": "Multiple faces found. Only one person, please."}
        )
    if recognised:
        student = Student.objects.filter(pk=next(iter(recognised))).first()
        if student:
            session.login_student(request, student)
            return JsonResponse(
                {
                    "ok": True,
                    "status": "recognised",
                    "student": {"id": student.pk, "name": student.name},
                    "redirect": _safe_next(request, reverse("classroom:student_dashboard")),
                }
            )
    return JsonResponse(
        {"ok": True, "status": "unknown", "message": "Face not recognised. You might be a new student!"}
    )


@require_POST
def student_register(request):
    """Create a student profile from a snapshot, a name and an optional voice sample."""
    name = request.POST.get("name", "").strip()
    if not name:
        return JsonResponse({"ok": False, "error": "Please enter your name."}, status=400)

    image, err = _read_image(request)
    if err:
        return err
    encodings = get_face_embeddings(image)
    if not encodings:
        return JsonResponse(
            {"ok": False, "error": "Couldn't capture your facial features. Try again with better lighting."},
            status=400,
        )
    if len(encodings) > 1:
        return JsonResponse({"ok": False, "error": "Multiple faces found. Only one person, please."}, status=400)

    voice_embedding = None
    audio = request.FILES.get("audio")
    if audio:
        voice_embedding = get_voice_embedding(audio.read())

    student = Student.objects.create(
        name=name,
        face_embedding=encodings[0].tolist(),
        voice_embedding=voice_embedding,
    )
    invalidate_face_model()
    session.login_student(request, student)
    return JsonResponse(
        {
            "ok": True,
            "student": {"id": student.pk, "name": student.name, "has_voice": bool(voice_embedding)},
            "voice_warning": bool(audio) and voice_embedding is None,
            "redirect": _safe_next(request, reverse("classroom:student_dashboard")),
        }
    )
