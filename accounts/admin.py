from django.contrib import admin

from .models import Student, Teacher


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ("name", "username", "created_at")
    search_fields = ("name", "username")
    exclude = ("password",)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("name", "has_voice_profile", "created_at")
    search_fields = ("name",)
    exclude = ("face_embedding", "voice_embedding")
