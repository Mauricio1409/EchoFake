from django.db import models
import uuid


def subject_upload_to(instance, filename):
    return f"subjects/{instance.pk}/{filename}"


def job_upload_to(instance, filename):
    return f"jobs/{instance.pk}/{filename}"


class Subject(models.Model):
    STATUS_CHOICES = [
        ("created", "Creado"),
        ("voice_ready", "Voz lista"),
        ("error", "Error"),
        ("deleted", "Borrado"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre_display = models.CharField(max_length=100)
    consent_signed = models.BooleanField(default=False)
    photo = models.ImageField(upload_to=subject_upload_to, blank=True, null=True)
    audio_sample = models.FileField(upload_to=subject_upload_to, blank=True, null=True)
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

    JOB_TYPE_CHOICES = [
        ("voice", "Voz"),
        ("video", "Video"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="jobs")
    job_type = models.CharField(max_length=20, choices=JOB_TYPE_CHOICES, default="voice")
    texto = models.TextField(blank=True, default="")
    audio = models.FileField(upload_to=job_upload_to, blank=True, null=True)
    fal_request_id = models.CharField(max_length=100, blank=True, null=True)
    fal_image_url = models.URLField(max_length=500, blank=True, null=True)
    fal_audio_url = models.URLField(max_length=500, blank=True, null=True)
    video = models.FileField(upload_to=job_upload_to, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    error_msg = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.subject.nombre_display} - {self.texto[:30]}"
