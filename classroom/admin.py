from django.contrib import admin

from .models import AttendanceLog, Enrollment, Subject


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("subject_code", "name", "section", "teacher", "created_at")
    search_fields = ("subject_code", "name")
    list_filter = ("teacher",)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "subject", "enrolled_at")
    list_filter = ("subject",)


@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
    list_display = ("student", "subject", "session_at", "is_present", "source")
    list_filter = ("subject", "is_present", "source")
