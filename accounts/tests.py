from unittest.mock import patch

import numpy as np
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import Student, Teacher

PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


def make_teacher(username="ananya", password="secret123", name="Ananya Roy"):
    teacher = Teacher(username=username, name=name)
    teacher.set_password(password)
    teacher.save()
    return teacher


class TeacherAuthTests(TestCase):
    def test_register_then_login(self):
        resp = self.client.post(
            reverse("accounts:teacher_register"),
            {"username": "ananya", "name": "Ananya Roy", "password": "secret123", "password_confirm": "secret123"},
        )
        self.assertRedirects(resp, reverse("accounts:teacher_login"))
        teacher = Teacher.objects.get(username="ananya")
        self.assertTrue(teacher.check_password("secret123"))
        self.assertNotEqual(teacher.password, "secret123")

        resp = self.client.post(reverse("accounts:teacher_login"), {"username": "ananya", "password": "secret123"})
        self.assertRedirects(resp, reverse("classroom:teacher_dashboard"))
        self.assertEqual(self.client.session["teacher_id"], teacher.pk)

    def test_register_rejects_mismatch_and_duplicates(self):
        make_teacher()
        resp = self.client.post(
            reverse("accounts:teacher_register"),
            {"username": "ananya", "name": "Other", "password": "secret123", "password_confirm": "secret123"},
        )
        self.assertContains(resp, "already taken")
        resp = self.client.post(
            reverse("accounts:teacher_register"),
            {"username": "new", "name": "New", "password": "secret123", "password_confirm": "nope"},
        )
        self.assertContains(resp, "do not match")

    def test_login_next_rejects_offsite_redirects(self):
        make_teacher()
        for evil in ("https://evil.example/", "//evil.example", "/\\evil.example", "///evil.example"):
            resp = self.client.post(
                reverse("accounts:teacher_login") + "?next=" + evil,
                {"username": "ananya", "password": "secret123"},
            )
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, reverse("classroom:teacher_dashboard"), evil)
            self.client.logout()
        resp = self.client.post(
            reverse("accounts:teacher_login") + "?next=/join/CS101/",
            {"username": "ananya", "password": "secret123"},
        )
        self.assertEqual(resp.url, "/join/CS101/")

    def test_bad_login_shows_error(self):
        make_teacher()
        resp = self.client.post(reverse("accounts:teacher_login"), {"username": "ananya", "password": "wrong"})
        self.assertContains(resp, "Invalid username")
        self.assertNotIn("teacher_id", self.client.session)

    def test_dashboard_requires_login(self):
        resp = self.client.get(reverse("classroom:teacher_dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:teacher_login"), resp.url)

    def test_logout_clears_session(self):
        teacher = make_teacher()
        session = self.client.session
        session["teacher_id"] = teacher.pk
        session.save()
        resp = self.client.post(reverse("accounts:teacher_logout"))
        self.assertRedirects(resp, reverse("accounts:home"))
        self.assertNotIn("teacher_id", self.client.session)


class StudentFaceLoginTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create(name="Hamza", face_embedding=[0.1] * 128)
        self.url = reverse("accounts:student_face_login")

    def _post(self):
        return self.client.post(self.url, {"image": SimpleUploadedFile("snap.png", PNG_1x1, "image/png")})

    @patch("accounts.views.recognise_faces")
    def test_recognised_face_logs_in(self, mock_rec):
        mock_rec.return_value = ({self.student.pk}, 1)
        data = self._post().json()
        self.assertEqual(data["status"], "recognised")
        self.assertEqual(data["student"]["name"], "Hamza")
        self.assertEqual(self.client.session["student_id"], self.student.pk)

    @patch("accounts.views.recognise_faces", return_value=(set(), 0))
    def test_no_face(self, _):
        self.assertEqual(self._post().json()["status"], "no_face")

    @patch("accounts.views.recognise_faces", return_value=(set(), 2))
    def test_multiple_faces(self, _):
        self.assertEqual(self._post().json()["status"], "multiple_faces")

    @patch("accounts.views.recognise_faces", return_value=(set(), 1))
    def test_unknown_face(self, _):
        self.assertEqual(self._post().json()["status"], "unknown")
        self.assertNotIn("student_id", self.client.session)

    def test_missing_image_is_400(self):
        self.assertEqual(self.client.post(self.url).status_code, 400)


class StudentRegisterTests(TestCase):
    def _post(self, **extra):
        payload = {"image": SimpleUploadedFile("snap.png", PNG_1x1, "image/png"), "name": "Akash"}
        payload.update(extra)
        return self.client.post(reverse("accounts:student_register"), payload)

    @patch("accounts.views.get_voice_embedding", return_value=[0.5] * 256)
    @patch("accounts.views.get_face_embeddings", return_value=[np.ones(128)])
    def test_registers_with_voice(self, _face, _voice):
        data = self._post(audio=SimpleUploadedFile("v.wav", b"RIFF", "audio/wav")).json()
        self.assertTrue(data["ok"])
        student = Student.objects.get(name="Akash")
        self.assertEqual(len(student.face_embedding), 128)
        self.assertTrue(student.has_voice_profile)
        self.assertEqual(self.client.session["student_id"], student.pk)

    @patch("accounts.views.get_face_embeddings", return_value=[])
    def test_no_face_rejected(self, _):
        resp = self._post()
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Student.objects.count(), 0)

    def test_name_required(self):
        self.assertEqual(self._post(name="").status_code, 400)
