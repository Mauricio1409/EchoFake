import mimetypes
import os
import time

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.api.exceptions import InvalidJobType, SubjectNotFound, SubjectNotVoiceReady, TextoRequired
from apps.api.models import Job
from apps.api.repositories.job_repository import JobRepository
from apps.api.repositories.subject_repository import SubjectRepository
from apps.api.services.elevenlabs_client import ElevenLabsClient
from apps.api.services.exceptions import FalGenerationError, FalPollTimeout
from apps.api.services.fal_client import FalClient
from apps.api.tasks import process_job_task

TEXTO_REQUIRED_TYPES = ("voice", "video")
VOICE_READY_REQUIRED_TYPES = ("voice", "video")

FAL_TERMINAL_SUCCESS_STATUSES = ("COMPLETED",)
FAL_IN_PROGRESS_STATUSES = ("IN_QUEUE", "IN_PROGRESS")


class JobService:
    def __init__(self):
        self.repository = JobRepository()
        self.subject_repository = SubjectRepository()
        self._handlers = {
            "voice": self._process_voice,
            "video": self._process_video,
        }

    def _elevenlabs_client(self) -> ElevenLabsClient:
        return ElevenLabsClient(
            api_key=settings.ELEVENLABS_API_KEY,
            base_url=settings.ELEVENLABS_BASE_URL,
        )

    def _fal_client(self) -> FalClient:
        return FalClient(
            api_key=settings.FAL_KEY,
            base_url=settings.FAL_BASE_URL,
            storage_url=settings.FAL_STORAGE_URL,
            model=settings.FAL_MODEL,
            platform_url=settings.FAL_PLATFORM_URL,
            admin_key=settings.FAL_ADMIN_KEY,
            ttl_seconds=settings.FAL_OBJECT_TTL_SECONDS,
        )

    @transaction.atomic
    def create_job(self, *, subject_id, job_type, texto=""):
        if job_type not in dict(Job.JOB_TYPE_CHOICES):
            raise InvalidJobType()

        subject = self.subject_repository.get_by_id(subject_id)
        if subject is None:
            raise SubjectNotFound()

        if job_type in TEXTO_REQUIRED_TYPES and not texto.strip():
            raise TextoRequired()

        if job_type in VOICE_READY_REQUIRED_TYPES and subject.status != "voice_ready":
            raise SubjectNotVoiceReady()

        job = self.repository.create(subject=subject, job_type=job_type, texto=texto)
        transaction.on_commit(lambda: process_job_task.delay(str(job.pk)))
        return job

    def process_job(self, job_id):
        job = self.repository.get_by_id(job_id)
        if job is None:
            return

        handler = self._handlers.get(job.job_type)
        if handler is None:
            raise InvalidJobType()

        handler(job)

    def mark_error(self, job_id, error_msg):
        job = self.repository.get_by_id(job_id)
        if job is None:
            return
        self.repository.update(job, status="error", error_msg=error_msg, finished_at=timezone.now())

    def _process_voice(self, job):
        subject = job.subject
        client = self._elevenlabs_client()
        audio_bytes = client.text_to_speech(subject.voice_id, job.texto)
        job.audio.save(f"{job.pk}.mp3", ContentFile(audio_bytes), save=False)
        self.repository.update(job, audio=job.audio, status="done", finished_at=timezone.now())

    def _process_video(self, job):
        subject = job.subject
        elevenlabs = self._elevenlabs_client()
        fal = self._fal_client()

        audio_bytes = elevenlabs.text_to_speech(subject.voice_id, job.texto)
        job.audio.save(f"{job.pk}.mp3", ContentFile(audio_bytes), save=False)
        self.repository.update(job, audio=job.audio, status="audio_ready")

        image_url = fal.upload_file(
            subject.photo.open("rb"),
            content_type=self._guess_content_type(subject.photo.name, "image/jpeg"),
            file_name=os.path.basename(subject.photo.name),
        )
        audio_url = fal.upload_file(
            job.audio.open("rb"),
            content_type="audio/mpeg",  # always TTS output, written as .mp3
            file_name=os.path.basename(job.audio.name),
        )

        self.repository.update(job, fal_image_url=image_url, fal_audio_url=audio_url)

        request_id = fal.submit_video(
            image_url=image_url,
            audio_url=audio_url,
            resolution=settings.FAL_RESOLUTION,
        )
        self.repository.update(job, fal_request_id=request_id, status="video_processing")

        self._poll_fal(fal, request_id)

        video_url = fal.get_result(request_id)
        video_bytes = fal.download(video_url)
        job.video.save(f"{job.pk}.mp4", ContentFile(video_bytes), save=False)
        self.repository.update(job, video=job.video, status="done", finished_at=timezone.now())

    @staticmethod
    def _guess_content_type(file_name, fallback):
        """fal stores the object with whatever Content-Type we declare, so it has
        to match the real file (volunteers upload PNG/GIF as often as JPEG)."""
        return mimetypes.guess_type(file_name)[0] or fallback

    @staticmethod
    def _poll_fal(fal, request_id):
        deadline = time.monotonic() + settings.FAL_POLL_TIMEOUT
        status = fal.get_status(request_id)

        while status.get("status") in FAL_IN_PROGRESS_STATUSES:
            if time.monotonic() >= deadline:
                raise FalPollTimeout(request_id, settings.FAL_POLL_TIMEOUT)
            time.sleep(settings.FAL_POLL_INTERVAL)
            status = fal.get_status(request_id)

        if status.get("status") not in FAL_TERMINAL_SUCCESS_STATUSES:
            raise FalGenerationError(request_id, status.get("error") or status.get("status", "unknown"))
