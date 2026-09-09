import json
from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import Student
from accounts.tests import PNG_1x1, make_teacher

from . import services
from .models import AttendanceLog, Enrollment, Subject


class ServiceTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.subject = Subject.objects.create(teacher=self.teacher, subject_code="CS101", name="Intro CS", section="A")
        self.a = Student.objects.create(name="Aisha", face_embedding=[0.1] * 128)
        self.b = Student.objects.create(name="Bilal", face_embedding=[0.2] * 128, voice_embedding=[0.3] * 256)
        Enrollment.objects.create(student=self.a, subject=self.subject)
        Enrollment.objects.create(student=self.b, subject=self.subject)

    def test_create_subject_validates(self):
        with self.assertRaises(ValueError):
            services.create_subject(self.teacher, "", "x", "y")
        with self.assertRaises(ValueError):
            services.create_subject(self.teacher, "cs101", "dup", "B")
        created = services.create_subject(self.teacher, " ma201 ", "Maths", "B")
        self.assertEqual(created.subject_code, "MA201")

    def test_enroll_by_code_flow(self):
        c = Student.objects.create(name="Chen")
        self.assertEqual(services.enroll_by_code(c, "nope"), (services.ENROLL_NOT_FOUND, None))
        status, subject = services.enroll_by_code(c, "cs101")
        self.assertEqual((status, subject), (services.ENROLL_OK, self.subject))
        status, _ = services.enroll_by_code(c, "CS101")
        self.assertEqual(status, services.ENROLL_ALREADY)
        self.assertTrue(services.unenroll(c, self.subject.pk))
        self.assertFalse(services.unenroll(c, self.subject.pk))

    def test_review_and_save_and_stats(self):
        review = services.build_review(self.subject, {self.a.pk: "Photo 1, Photo 2"}, source="face")
        self.assertEqual(review["present"], 1)
        self.assertEqual(review["total"], 2)
        rows = {r["name"]: r for r in review["rows"]}
        self.assertTrue(rows["Aisha"]["is_present"])
        self.assertEqual(rows["Aisha"]["source"], "Photo 1, Photo 2")
        self.assertFalse(rows["Bilal"]["is_present"])

        session_at = services.parse_session_at(review["session_at"])
        saved = services.save_attendance(
            self.subject, session_at, review["rows"] + [{"student_id": 999, "is_present": True}]
        )
        self.assertEqual(saved, 2)

        # Second session an hour later where both are present.
        later = session_at + timedelta(hours=1)
        services.save_attendance(
            self.subject,
            later,
            [{"student_id": self.a.pk, "is_present": True}, {"student_id": self.b.pk, "is_present": True}],
            "voice",
        )

        subjects = list(services.subjects_with_stats(self.teacher))
        self.assertEqual(subjects[0].total_students, 2)
        self.assertEqual(subjects[0].total_classes, 2)

        summaries = services.session_summaries(self.teacher)
        self.assertEqual(len(summaries), 2)
        self.assertEqual(summaries[0]["session_at"], later)  # newest first
        self.assertEqual((summaries[0]["present"], summaries[0]["total"]), (2, 2))
        self.assertEqual((summaries[1]["present"], summaries[1]["total"]), (1, 2))

        cards = services.student_subjects_with_stats(self.b)
        self.assertEqual(cards[0]["total"], 2)
        self.assertEqual(cards[0]["attended"], 1)
        self.assertEqual(cards[0]["percent"], 50)


class TeacherApiTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.other = make_teacher(username="other", name="Other")
        self.subject = Subject.objects.create(teacher=self.teacher, subject_code="CS101", name="Intro CS", section="A")
        self.student = Student.objects.create(name="Aisha", face_embedding=[0.1] * 128, voice_embedding=[0.2] * 256)
        Enrollment.objects.create(student=self.student, subject=self.subject)
        session = self.client.session
        session["teacher_id"] = self.teacher.pk
        session.save()

    def _json(self, name, payload):
        return self.client.post(reverse(name), json.dumps(payload), content_type="application/json")

    def test_dashboard_renders(self):
        resp = self.client.get(reverse("classroom:teacher_dashboard"))
        self.assertContains(resp, "Intro CS")
        self.assertContains(resp, "/join/CS101/")

    def test_create_subject(self):
        resp = self._json("classroom:api_create_subject", {"subject_code": "ma1", "name": "Maths", "section": "B"})
        self.assertTrue(resp.json()["ok"])
        self.assertTrue(Subject.objects.filter(subject_code="MA1", teacher=self.teacher).exists())
        resp = self._json("classroom:api_create_subject", {"subject_code": "MA1", "name": "Maths", "section": "B"})
        self.assertEqual(resp.status_code, 400)

    @patch("classroom.api.recognise_faces")
    def test_analyse_faces_then_save(self, mock_rec):
        mock_rec.side_effect = [({self.student.pk}, 1), (set(), 0)]
        resp = self.client.post(
            reverse("classroom:api_analyse_faces"),
            {
                "subject_id": self.subject.pk,
                "photos": [
                    SimpleUploadedFile("a.png", PNG_1x1, "image/png"),
                    SimpleUploadedFile("b.png", PNG_1x1, "image/png"),
                ],
            },
        )
        review = resp.json()["review"]
        self.assertEqual(review["present"], 1)
        self.assertEqual(review["rows"][0]["source"], "Photo 1")

        resp = self._json(
            "classroom:api_save_attendance",
            {"subject_id": self.subject.pk, "session_at": review["session_at"], "rows": review["rows"], "source": "face"},
        )
        self.assertEqual(resp.json()["saved"], 1)
        log = AttendanceLog.objects.get()
        self.assertTrue(log.is_present)
        self.assertEqual(log.source, "face")

    def test_analyse_faces_requires_photos(self):
        resp = self.client.post(reverse("classroom:api_analyse_faces"), {"subject_id": self.subject.pk})
        self.assertEqual(resp.status_code, 400)

    def test_cannot_use_other_teachers_subject(self):
        foreign = Subject.objects.create(teacher=self.other, subject_code="X1", name="X", section="A")
        resp = self._json("classroom:api_save_attendance", {"subject_id": foreign.pk, "rows": [{"student_id": 1}]})
        self.assertEqual(resp.status_code, 404)

    @patch("classroom.api.process_bulk_audio")
    def test_analyse_voice(self, mock_voice):
        mock_voice.return_value = {self.student.pk: 0.81}
        resp = self.client.post(
            reverse("classroom:api_analyse_voice"),
            {"subject_id": self.subject.pk, "audio": SimpleUploadedFile("c.wav", b"RIFF", "audio/wav")},
        )
        review = resp.json()["review"]
        self.assertEqual(review["source"], "voice")
        self.assertEqual(review["rows"][0]["source"], "match 0.81")

    def test_api_requires_login(self):
        self.client.logout()
        resp = self.client.post(reverse("classroom:api_create_subject"), "{}", content_type="application/json")
        self.assertEqual(resp.status_code, 401)


class StudentFlowTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.subject = Subject.objects.create(teacher=self.teacher, subject_code="CS101", name="Intro CS", section="A")
        self.student = Student.objects.create(name="Aisha")
        session = self.client.session
        session["student_id"] = self.student.pk
        session.save()

    def _json(self, name, payload):
        return self.client.post(reverse(name), json.dumps(payload), content_type="application/json")

    def test_enroll_and_unenroll_api(self):
        resp = self._json("classroom:api_enroll", {"code": "cs101"})
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(self._json("classroom:api_enroll", {"code": "cs101"}).status_code, 400)
        self.assertEqual(self._json("classroom:api_enroll", {"code": "zz"}).status_code, 404)
        resp = self.client.get(reverse("classroom:student_dashboard"))
        self.assertContains(resp, "Intro CS")
        resp = self._json("classroom:api_unenroll", {"subject_id": self.subject.pk})
        self.assertTrue(resp.json()["ok"])
        self.assertFalse(Enrollment.objects.exists())

    def test_join_link_enrolls(self):
        resp = self.client.get(reverse("classroom:join_subject", args=["CS101"]))
        self.assertContains(resp, "Intro CS")
        resp = self.client.post(reverse("classroom:join_subject", args=["CS101"]))
        self.assertRedirects(resp, reverse("classroom:student_dashboard"))
        self.assertTrue(Enrollment.objects.filter(student=self.student, subject=self.subject).exists())

    def test_join_link_redirects_anonymous_to_login(self):
        self.client.logout()
        resp = self.client.get(reverse("classroom:join_subject", args=["CS101"]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("next=/join/CS101/", resp.url)

    def test_unknown_join_code(self):
        resp = self.client.get(reverse("classroom:join_subject", args=["NOPE"]))
        self.assertContains(resp, "NOPE")
        self.assertContains(resp, "not find")
