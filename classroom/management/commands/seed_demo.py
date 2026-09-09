"""Populate the database with a demo teacher, students, subjects and sessions.

Usage: python manage.py seed_demo

The demo students have random embeddings, so they will never match a real
face or voice; register yourself through the student portal to try recognition.
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Student, Teacher
from classroom.models import AttendanceLog, Enrollment, Subject

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo123"


class Command(BaseCommand):
    help = "Create demo data: teacher demo/demo123, five students, two subjects and a few attendance sessions."

    def handle(self, *args, **options):
        rng = random.Random(7)

        teacher, _ = Teacher.objects.get_or_create(username=DEMO_USERNAME, defaults={"name": "Ananya Roy"})
        teacher.set_password(DEMO_PASSWORD)
        teacher.save()

        students = []
        for index, name in enumerate(["Hamza Rizvi", "Akash Verma", "Priya Nair", "Sana Khan", "Rohan Das"]):
            student, _ = Student.objects.get_or_create(
                name=name,
                defaults={
                    "face_embedding": [rng.uniform(-0.2, 0.2) for _ in range(128)],
                    "voice_embedding": [rng.uniform(-0.1, 0.1) for _ in range(256)] if index % 2 == 0 else None,
                },
            )
            students.append(student)

        subjects = []
        for code, name, section in [
            ("CS101", "Introduction to Computer Science", "A"),
            ("MA201", "Discrete Mathematics", "B"),
        ]:
            subject, _ = Subject.objects.get_or_create(
                subject_code=code, defaults={"name": name, "section": section, "teacher": teacher}
            )
            subjects.append(subject)

        for student in students:
            Enrollment.objects.get_or_create(student=student, subject=subjects[0])
        for student in students[:3]:
            Enrollment.objects.get_or_create(student=student, subject=subjects[1])

        if not AttendanceLog.objects.filter(subject__in=subjects).exists():
            now = timezone.now().replace(microsecond=0)
            for day in range(4):
                at = now - timedelta(days=day, hours=2)
                for student in students:
                    AttendanceLog.objects.create(
                        student=student,
                        subject=subjects[0],
                        session_at=at,
                        is_present=rng.random() > 0.3,
                        source="face" if day % 2 else "voice",
                    )
            for day in range(2):
                at = now - timedelta(days=day, hours=5)
                for student in students[:3]:
                    AttendanceLog.objects.create(
                        student=student, subject=subjects[1], session_at=at, is_present=rng.random() > 0.2
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data ready. Teacher login: {DEMO_USERNAME} / {DEMO_PASSWORD}. "
                f"{Student.objects.count()} students, {Subject.objects.count()} subjects, "
                f"{AttendanceLog.objects.count()} attendance logs."
            )
        )
