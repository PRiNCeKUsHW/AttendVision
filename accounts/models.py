from django.contrib.auth.hashers import check_password, make_password
from django.db import models


class Teacher(models.Model):
    username = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    password = models.CharField(max_length=256)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} (@{self.username})"

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)


class Student(models.Model):
    name = models.CharField(max_length=120)
    face_embedding = models.JSONField(null=True, blank=True)
    voice_embedding = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def has_voice_profile(self):
        return bool(self.voice_embedding)
