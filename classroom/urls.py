from django.urls import path

from . import api, views

app_name = "classroom"

urlpatterns = [
    path("teacher/", views.teacher_dashboard, name="teacher_dashboard"),
    path("teacher/api/subjects/", api.create_subject, name="api_create_subject"),
    path("teacher/api/attendance/faces/", api.analyse_faces, name="api_analyse_faces"),
    path("teacher/api/attendance/voice/", api.analyse_voice, name="api_analyse_voice"),
    path("teacher/api/attendance/save/", api.save_attendance, name="api_save_attendance"),
    path("student/", views.student_dashboard, name="student_dashboard"),
    path("student/api/enroll/", api.enroll, name="api_enroll"),
    path("student/api/unenroll/", api.unenroll, name="api_unenroll"),
    path("join/<str:code>/", views.join_subject, name="join_subject"),
]
