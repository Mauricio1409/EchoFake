from django.db import models
import uuid


class Subject(models.Model):
    STATUS_CHOICES = [
        ("created", "Creado"),
        ("voice_ready", "Voz lista"),
        ("deleted", "Borrado"),
    ]

    id = models.CharField(max_length=20, primary_key=True, default=uuid.uuid4, editable=False)
    nombre_display = models.CharField(max_length=100)
    consent_signed = models.BooleanField(default=False)
    photo = models.ImageField(upload_to="subjects/%(id)s/", blank=True, null=True)
    voice_id = models.CharField(max_length=100, blank=True, null=True)  # de ElevenLabs
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="created")
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.nombre_display


class Job(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("audio_ready", "Audio listo"),
        ("video_processing", "Procesando video"),
        ("done", "Terminado"),
        ("error", "Error"),
    ]

    id = models.CharField(max_length=20, primary_key=True, default=uuid.uuid4, editable=False)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="jobs")
    texto = models.TextField()
    audio = models.FileField(upload_to="jobs/%(id)s/", blank=True, null=True)
    did_talk_id = models.CharField(max_length=100, blank=True, null=True)
    video = models.FileField(upload_to="jobs/%(id)s/", blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    error_msg = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.subject.nombre_display} - {self.texto[:30]}"