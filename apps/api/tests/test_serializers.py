import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.api.models import Subject
from apps.api.serializers import JobCreateSerializer, SubjectCreateSerializer

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


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class SubjectCreateSerializerTests(TestCase):
    def test_valid_data_is_valid(self):
        serializer = SubjectCreateSerializer(
            data={
                "nombre_display": "Ana",
                "consent_signed": True,
                "photo": make_photo(),
                "audio_sample": make_audio(),
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_missing_photo_is_invalid(self):
        serializer = SubjectCreateSerializer(
            data={
                "nombre_display": "Ana",
                "consent_signed": True,
                "audio_sample": make_audio(),
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("photo", serializer.errors)

    def test_missing_audio_sample_is_invalid(self):
        serializer = SubjectCreateSerializer(
            data={
                "nombre_display": "Ana",
                "consent_signed": True,
                "photo": make_photo(),
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("audio_sample", serializer.errors)

    def test_consent_false_is_invalid(self):
        serializer = SubjectCreateSerializer(
            data={
                "nombre_display": "Ana",
                "consent_signed": False,
                "photo": make_photo(),
                "audio_sample": make_audio(),
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("consent_signed", serializer.errors)


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class JobCreateSerializerTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            photo=make_photo(),
            audio_sample=make_audio(),
            voice_id="voice-123",
            status="voice_ready",
        )

    def test_voice_with_texto_is_valid(self):
        serializer = JobCreateSerializer(
            data={"subject": str(self.subject.pk), "job_type": "voice", "texto": "hola"}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_voice_without_texto_is_invalid(self):
        serializer = JobCreateSerializer(
            data={"subject": str(self.subject.pk), "job_type": "voice", "texto": ""}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("texto", serializer.errors)

    def test_gesture_is_not_a_valid_job_type_choice(self):
        # "gesture" was removed from Job.JOB_TYPE_CHOICES — the ChoiceField
        # must reject it at the serializer level, before it reaches the service.
        serializer = JobCreateSerializer(
            data={"subject": str(self.subject.pk), "job_type": "gesture"}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("job_type", serializer.errors)

    def test_invalid_job_type_choice_is_invalid(self):
        serializer = JobCreateSerializer(
            data={"subject": str(self.subject.pk), "job_type": "bogus", "texto": "hola"}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("job_type", serializer.errors)


class PurgeReportSerializerTests(TestCase):
    def test_purge_surface_serializer_emits_surface_status_detail(self):
        from apps.api.serializers import PurgeSurfaceSerializer

        serializer = PurgeSurfaceSerializer(
            {"surface": "elevenlabs_voice", "status": "deleted", "detail": ""}
        )

        self.assertEqual(
            serializer.data,
            {"surface": "elevenlabs_voice", "status": "deleted", "detail": ""},
        )

    def test_purge_report_serializer_emits_subject_id_and_report_list(self):
        from apps.api.serializers import PurgeReportSerializer

        report = {
            "subject_id": "00000000-0000-0000-0000-000000000000",
            "report": [
                {"surface": "elevenlabs_voice", "status": "deleted", "detail": ""},
                {"surface": "fal_inputs", "status": "revoked", "detail": "expira en <=3600s"},
                {"surface": "fal_output", "status": "skipped", "detail": "sin admin key"},
                {"surface": "local", "status": "deleted", "detail": ""},
            ],
        }

        serializer = PurgeReportSerializer(report)

        self.assertEqual(serializer.data["subject_id"], "00000000-0000-0000-0000-000000000000")
        self.assertEqual(len(serializer.data["report"]), 4)
        self.assertEqual(serializer.data["report"][1]["surface"], "fal_inputs")
        self.assertEqual(serializer.data["report"][1]["status"], "revoked")
