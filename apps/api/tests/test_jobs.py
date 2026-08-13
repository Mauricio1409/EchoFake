import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.api.models import Job, Subject

MEDIA_TMP = tempfile.mkdtemp()

GIF_1PX = (
    b"GIF87a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff\x21\xf9\x04"
    b"\x00\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
    b"\x44\x01\x00\x3b"
)


def make_photo():
    return SimpleUploadedFile("photo.gif", GIF_1PX, content_type="image/gif")


def make_audio():
    return SimpleUploadedFile("sample.wav", b"fake-audio-bytes", content_type="audio/wav")


@override_settings(MEDIA_ROOT=MEDIA_TMP, CELERY_TASK_ALWAYS_EAGER=True)
class JobViewSetTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="operador", password="pass12345")
        self.client.force_authenticate(user=self.user)

    def _voice_ready_subject(self):
        return Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            photo=make_photo(),
            audio_sample=make_audio(),
            voice_id="voice-123",
            status="voice_ready",
        )

    def _created_subject(self):
        return Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            photo=make_photo(),
            audio_sample=make_audio(),
        )

    @patch("apps.api.services.job_service.ElevenLabsClient")
    def test_create_job_voice_success(self, mock_client_cls):
        mock_client_cls.return_value.text_to_speech.return_value = b"mp3-bytes"
        subject = self._voice_ready_subject()

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/jobs/",
                data={"subject": str(subject.pk), "job_type": "voice", "texto": "hola"},
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        job = Job.objects.get(pk=response.data["id"])
        self.assertEqual(job.status, "done")

    def test_create_job_voice_without_texto_returns_400(self):
        subject = self._voice_ready_subject()

        response = self.client.post(
            "/api/jobs/",
            data={"subject": str(subject.pk), "job_type": "voice", "texto": ""},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_job_voice_on_non_voice_ready_subject_returns_400(self):
        subject = self._created_subject()

        response = self.client.post(
            "/api/jobs/",
            data={"subject": str(subject.pk), "job_type": "voice", "texto": "hola"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_job_gesture_rejected_with_400_and_no_row_created(self):
        # "gesture" is no longer in Job.JOB_TYPE_CHOICES, so the serializer's
        # ChoiceField rejects it before JobService.create_job is ever called
        # (see test_services.JobServiceTests.test_create_job_gesture_raises_invalid_job_type
        # for the direct-service-call path, which DOES hit InvalidJobType).
        subject = self._created_subject()

        response = self.client.post(
            "/api/jobs/",
            data={"subject": str(subject.pk), "job_type": "gesture", "texto": "hola"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("job_type", response.data)
        self.assertEqual(Job.objects.count(), 0)

    def test_create_job_invalid_job_type_returns_400(self):
        subject = self._voice_ready_subject()

        response = self.client.post(
            "/api/jobs/",
            data={"subject": str(subject.pk), "job_type": "bogus", "texto": "hola"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_job(self):
        subject = self._voice_ready_subject()
        job = Job.objects.create(subject=subject, job_type="voice", texto="hola")

        response = self.client.get(f"/api/jobs/{job.pk}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(job.pk))

    def test_list_jobs_filtered_by_subject_returns_only_that_subjects_jobs_in_order(self):
        subject = self._voice_ready_subject()
        other_subject = self._voice_ready_subject()
        job_1 = Job.objects.create(subject=subject, job_type="voice", texto="primero")
        job_2 = Job.objects.create(subject=subject, job_type="video", texto="segundo")
        Job.objects.create(subject=other_subject, job_type="voice", texto="ajeno")

        response = self.client.get(f"/api/jobs/?subject={subject.pk}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in response.data],
            [str(job_1.pk), str(job_2.pk)],
        )

    def test_list_jobs_without_subject_filter_returns_all_jobs(self):
        subject = self._voice_ready_subject()
        Job.objects.create(subject=subject, job_type="voice", texto="uno")
        Job.objects.create(subject=subject, job_type="video", texto="dos")

        response = self.client.get("/api/jobs/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class JobViewSetUnauthenticatedTests(APITestCase):
    def test_list_jobs_without_credentials_returns_401(self):
        response = self.client.get("/api/jobs/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
