"""Manual smoke check (tasks.md 11.2): with API keys unset (the real .env default in
this environment), a job/clone task must land in status=error and MUST NOT raise —
the Celery worker must stay alive. No real network calls happen because httpx raises
a connection error against the (unreachable/default) base_url, which is still an
httpx.HTTPError subclass caught by the clients."""

import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.api.models import Job, Subject
from apps.api.services.exceptions import ExternalAPIError
from apps.api.tasks import clone_voice_task, process_job_task

MEDIA_TMP = tempfile.mkdtemp()


def make_audio():
    return SimpleUploadedFile("sample.wav", b"fake-audio-bytes", content_type="audio/wav")


@override_settings(ELEVENLABS_API_KEY="", FAL_KEY="", MEDIA_ROOT=MEDIA_TMP)
class UnsetApiKeysSmokeTests(TestCase):
    @patch("apps.api.services.elevenlabs_client.ElevenLabsClient.add_voice")
    def test_clone_voice_task_with_unset_key_lands_in_error_without_raising(self, mock_add_voice):
        mock_add_voice.side_effect = ExternalAPIError("elevenlabs", "connection refused")
        subject = Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            audio_sample=make_audio(),
        )

        clone_voice_task(str(subject.pk))  # must not raise

        subject.refresh_from_db()
        self.assertEqual(subject.status, "error")

    @patch("apps.api.services.elevenlabs_client.ElevenLabsClient.text_to_speech")
    def test_process_job_task_with_unset_key_lands_in_error_without_raising(self, mock_tts):
        mock_tts.side_effect = ExternalAPIError("elevenlabs", "connection refused")
        subject = Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            voice_id="voice-123",
            status="voice_ready",
        )
        job = Job.objects.create(subject=subject, job_type="voice", texto="hola")

        process_job_task(str(job.pk))  # must not raise

        job.refresh_from_db()
        self.assertEqual(job.status, "error")
        self.assertTrue(job.error_msg)

    @patch("apps.api.services.fal_client.FalClient.upload_file")
    @patch("apps.api.services.elevenlabs_client.ElevenLabsClient.text_to_speech")
    def test_process_job_video_task_with_unset_fal_key_lands_in_error_without_raising(
        self, mock_tts, mock_upload_file
    ):
        mock_tts.return_value = b"mp3-bytes"
        mock_upload_file.side_effect = ExternalAPIError("fal", "connection refused")
        subject = Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            photo=SimpleUploadedFile("photo.jpg", b"fake-image-bytes", content_type="image/jpeg"),
            voice_id="voice-123",
            status="voice_ready",
        )
        job = Job.objects.create(subject=subject, job_type="video", texto="hola")

        process_job_task(str(job.pk))  # must not raise

        job.refresh_from_db()
        self.assertEqual(job.status, "error")
        self.assertTrue(job.error_msg)
        self.assertIn("fal", job.error_msg)
