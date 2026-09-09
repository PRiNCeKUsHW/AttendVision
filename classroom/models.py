from django.db import models


class Subject(models.Model):
    subject_code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=160)
    section = models.CharField(max_length=32)
    teacher = models.ForeignKey("accounts.Teacher", on_delete=models.CASCADE, related_name="subjects")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject_code} · {self.name} ({self.section})"


class Enrollment(models.Model):
    student = models.ForeignKey("accounts.Student", on_delete=models.CASCADE, related_name="enrollments")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="enrollments")
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("student", "subject")]
        ordering = ["-enrolled_at"]

    def __str__(self):
        return f"{self.student} → {self.subject}"


class AttendanceLog(models.Model):
    student = models.ForeignKey("accounts.Student", on_delete=models.CASCADE, related_name="attendance_logs")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="attendance_logs")
    session_at = models.DateTimeField(db_index=True)
    is_present = models.BooleanField(default=False)
    source = models.CharField(max_length=16, default="face")  # face | voice

    class Meta:
        ordering = ["-session_at"]
        indexes = [models.Index(fields=["subject", "session_at"])]

    def __str__(self):
        state = "present" if self.is_present else "absent"
        return f"{self.student} {state} in {self.subject.subject_code} @ {self.session_at:%Y-%m-%d %H:%M}"
