from .session import current_student, current_teacher


def current_user(request):
    return {
        "current_teacher": current_teacher(request),
        "current_student": current_student(request),
    }
