from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse

from accounts.session import current_student, student_required, teacher_required

from . import services


@teacher_required
def teacher_dashboard(request):
    teacher = request.teacher
    subjects = list(services.subjects_with_stats(teacher))
    subject_payload = []
    for s in subjects:
        join_url = request.build_absolute_uri(reverse("classroom:join_subject", args=[s.subject_code]))
        subject_payload.append(
            {
                "id": s.pk,
                "code": s.subject_code,
                "name": s.name,
                "section": s.section,
                "students": s.total_students,
                "classes": s.total_classes,
                "join_url": join_url,
                "qr": services.make_join_qr_data_url(join_url),
            }
        )
    sessions = services.session_summaries(teacher)
    return render(
        request,
        "classroom/teacher_dashboard.html",
        {
            "teacher": teacher,
            "subjects": subjects,
            "subjects_json": subject_payload,
            "sessions": sessions,
            "total_students": sum(s.total_students for s in subjects),
        },
    )


@student_required
def student_dashboard(request):
    student = request.student
    cards = services.student_subjects_with_stats(student)
    return render(request, "classroom/student_dashboard.html", {"student": student, "cards": cards})


def join_subject(request, code):
    """Landing page for shared join links / QR codes."""
    subject = services.find_subject_by_code(code)
    student = current_student(request)
    if student is None:
        login_url = reverse("accounts:student_login")
        return redirect(f"{login_url}?next={request.get_full_path()}")

    if request.method == "POST" and subject is not None:
        status = services.enroll(student, subject)
        if status == services.ENROLL_OK:
            messages.success(request, f"You're enrolled in {subject.name}!")
        else:
            messages.info(request, f"You're already enrolled in {subject.name}.")
        return redirect("classroom:student_dashboard")

    already = subject is not None and subject.enrollments.filter(student=student).exists()
    return render(
        request,
        "classroom/join.html",
        {"subject": subject, "code": code, "already": already, "student": student},
    )
