import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.api.models import Subject

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
class SubjectViewSetTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="operador", password="pass12345")
        self.client.force_authenticate(user=self.user)

    @patch("apps.api.services.subject_service.ElevenLabsClient")
    def test_create_subject_success(self, mock_client_cls):
        mock_client_cls.return_value.add_voice.return_value = "voice-123"
        response = self.client.post(
            "/api/subjects/",
            data={
                "nombre_display": "Ana",
                "consent_signed": True,
                "photo": make_photo(),
                "audio_sample": make_audio(),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Subject.objects.count(), 1)

    def test_create_subject_missing_consent_returns_400(self):
        response = self.client.post(
            "/api/subjects/",
            data={
                "nombre_display": "Ana",
                "consent_signed": False,
                "photo": make_photo(),
                "audio_sample": make_audio(),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Subject.objects.count(), 0)

    def test_create_subject_missing_audio_sample_returns_400(self):
        response = self.client.post(
            "/api/subjects/",
            data={
                "nombre_display": "Ana",
                "consent_signed": True,
                "photo": make_photo(),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_subject(self):
        subject = Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            photo=make_photo(),
            audio_sample=make_audio(),
        )

        response = self.client.get(f"/api/subjects/{subject.pk}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(subject.pk))

    def test_purge_subject_success(self):
        subject = Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            photo=make_photo(),
            audio_sample=make_audio(),
        )

        response = self.client.delete(f"/api/subjects/{subject.pk}/purge/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["subject_id"], str(subject.pk))
        self.assertEqual(len(response.data["report"]), 4)
        self.assertEqual(
            [entry["surface"] for entry in response.data["report"]],
            ["elevenlabs_voice", "fal_inputs", "fal_output", "local"],
        )
        self.assertEqual(Subject.objects.count(), 0)

    def test_purge_subject_not_found_returns_404(self):
        response = self.client.delete("/api/subjects/00000000-0000-0000-0000-000000000000/purge/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class SubjectViewSetUnauthenticatedTests(APITestCase):
    def test_list_subjects_without_credentials_returns_401(self):
        response = self.client.get("/api/subjects/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_subject_without_credentials_returns_401(self):
        response = self.client.post(
            "/api/subjects/",
            data={
                "nombre_display": "Ana",
                "consent_signed": True,
                "photo": make_photo(),
                "audio_sample": make_audio(),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Subject.objects.count(), 0)
