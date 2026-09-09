from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.home, name="home"),
    path("teacher/login/", views.teacher_login, name="teacher_login"),
    path("teacher/register/", views.teacher_register, name="teacher_register"),
    path("teacher/logout/", views.logout_view, name="teacher_logout"),
    path("student/login/", views.student_login, name="student_login"),
    path("student/logout/", views.logout_view, name="student_logout"),
    path("student/api/face-login/", views.student_face_login, name="student_face_login"),
    path("student/api/register/", views.student_register, name="student_register"),
]
