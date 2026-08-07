import io
from unittest.mock import ANY, MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
import tempfile

from apps.api.exceptions import (
    ConsentRequired,
    InvalidJobType,
    SubjectNotFound,
    SubjectNotVoiceReady,
    TextoRequired,
)
from apps.api.models import Job, Subject
from apps.api.services.exceptions import ExternalAPIError, FalGenerationError, FalPollTimeout
from apps.api.services.job_service import JobService
from apps.api.services.subject_service import SubjectService

MEDIA_TMP = tempfile.mkdtemp()


def make_photo():
    return SimpleUploadedFile("photo.jpg", b"fake-image-bytes", content_type="image/jpeg")


def make_audio():
    return SimpleUploadedFile("sample.wav", b"fake-audio-bytes", content_type="audio/wav")


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class SubjectServiceTests(TestCase):
    def setUp(self):
        self.service = SubjectService()

    def test_create_subject_without_consent_raises(self):
        with self.assertRaises(ConsentRequired):
            self.service.create_subject(
                nombre_display="Ana",
                consent_signed=False,
                photo=make_photo(),
                audio_sample=make_audio(),
            )
        self.assertEqual(Subject.objects.count(), 0)

    @patch("apps.api.services.subject_service.clone_voice_task")
    def test_create_subject_with_consent_persists_and_enqueues(self, mock_task):
        with self.captureOnCommitCallbacks(execute=True):
            subject = self.service.create_subject(
                nombre_display="Ana",
                consent_signed=True,
                photo=make_photo(),
                audio_sample=make_audio(),
            )

        self.assertEqual(subject.status, "created")
        self.assertTrue(subject.photo.name)
        self.assertTrue(subject.audio_sample.name)
        mock_task.delay.assert_called_once_with(str(subject.pk))

    @patch("apps.api.services.subject_service.ElevenLabsClient")
    def test_clone_voice_success_sets_voice_ready(self, mock_client_cls):
        mock_client_cls.return_value.add_voice.return_value = "voice-123"
        subject = Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            photo=make_photo(),
            audio_sample=make_audio(),
        )

        self.service.clone_voice(str(subject.pk))

        subject.refresh_from_db()
        self.assertEqual(subject.voice_id, "voice-123")
        self.assertEqual(subject.status, "voice_ready")

    @patch("apps.api.services.subject_service.ElevenLabsClient")
    def test_clone_voice_failure_propagates_external_api_error(self, mock_client_cls):
        # Containment lives in the Celery task, not the Service (see clone_voice_task).
        mock_client_cls.return_value.add_voice.side_effect = ExternalAPIError("elevenlabs", "boom")
        subject = Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            photo=make_photo(),
            audio_sample=make_audio(),
        )

        with self.assertRaises(ExternalAPIError):
            self.service.clone_voice(str(subject.pk))

    def test_mark_error_sets_status(self):
        subject = Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            photo=make_photo(),
            audio_sample=make_audio(),
        )

        self.service.mark_error(str(subject.pk), "boom")

        subject.refresh_from_db()
        self.assertEqual(subject.status, "error")

    def test_purge_missing_subject_raises_not_found(self):
        with self.assertRaises(SubjectNotFound):
            self.service.purge("00000000-0000-0000-0000-000000000000")

    def _report_entry(self, report, surface):
        return next(entry for entry in report["report"] if entry["surface"] == surface)

    @patch("apps.api.services.subject_service.FalClient")
    @patch("apps.api.services.subject_service.ElevenLabsClient")
    def test_purge_full_success_removes_subject_and_jobs(self, mock_client_cls, mock_fal_cls):
        mock_fal_cls.return_value.set_file_acl.return_value = None
        mock_fal_cls.return_value.delete_request_payloads.return_value = None
        subject = Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            photo=make_photo(),
            audio_sample=make_audio(),
            voice_id="voice-123",
            status="voice_ready",
        )
        Job.objects.create(subject=subject, job_type="voice", texto="hola")
        Job.objects.create(
            subject=subject,
            job_type="video",
            texto="hola",
            fal_request_id="req-1",
            fal_image_url="https://fal.media/files/photo.jpg",
            fal_audio_url="https://fal.media/files/audio.mp3",
        )

        with self.settings(FAL_ADMIN_KEY="admin-secret"):
            report = self.service.purge(str(subject.pk))

        mock_client_cls.return_value.delete_voice.assert_called_once_with("voice-123")
        self.assertEqual(report["subject_id"], str(subject.pk))
        self.assertEqual(len(report["report"]), 4)
        self.assertEqual(self._report_entry(report, "elevenlabs_voice")["status"], "deleted")
        self.assertEqual(self._report_entry(report, "fal_inputs")["status"], "revoked")
        self.assertEqual(self._report_entry(report, "fal_output")["status"], "deleted")
        self.assertEqual(self._report_entry(report, "local")["status"], "deleted")
        self.assertEqual(Subject.objects.count(), 0)
        self.assertEqual(Job.objects.count(), 0)

    @patch("apps.api.services.subject_service.FalClient")
    @patch("apps.api.services.subject_service.ElevenLabsClient")
    def test_purge_without_voice_id_skips_remote_delete(self, mock_client_cls, mock_fal_cls):
        subject = Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            photo=make_photo(),
            audio_sample=make_audio(),
        )

        report = self.service.purge(str(subject.pk))

        mock_client_cls.return_value.delete_voice.assert_not_called()
        self.assertEqual(self._report_entry(report, "elevenlabs_voice")["status"], "skipped")
        self.assertEqual(Subject.objects.count(), 0)

    @patch("apps.api.services.subject_service.FalClient")
    @patch("apps.api.services.subject_service.ElevenLabsClient")
    def test_purge_elevenlabs_failure_still_cleans_up_locally(self, mock_client_cls, mock_fal_cls):
        mock_client_cls.return_value.delete_voice.side_effect = ExternalAPIError("elevenlabs", "boom")
        subject = Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            photo=make_photo(),
            audio_sample=make_audio(),
            voice_id="voice-123",
            status="voice_ready",
        )

        report = self.service.purge(str(subject.pk))

        self.assertEqual(self._report_entry(report, "elevenlabs_voice")["status"], "failed")
        self.assertEqual(self._report_entry(report, "local")["status"], "skipped")
        self.assertEqual(Subject.objects.count(), 1)
        subject.refresh_from_db()
        self.assertEqual(subject.status, "error")

    @patch("apps.api.services.subject_service.FalClient")
    @patch("apps.api.services.subject_service.ElevenLabsClient")
    def test_purge_fal_inputs_failure_still_runs_other_surfaces(self, mock_client_cls, mock_fal_cls):
        mock_fal_cls.return_value.set_file_acl.side_effect = ExternalAPIError("fal", "no assets:write")
        mock_fal_cls.return_value.delete_request_payloads.return_value = None
        subject = Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            photo=make_photo(),
            audio_sample=make_audio(),
            voice_id="voice-123",
            status="voice_ready",
        )
        Job.objects.create(
            subject=subject,
            job_type="video",
            texto="hola",
            fal_request_id="req-1",
            fal_image_url="https://fal.media/files/photo.jpg",
            fal_audio_url="https://fal.media/files/audio.mp3",
        )

        with self.settings(FAL_ADMIN_KEY="admin-secret"):
            report = self.service.purge(str(subject.pk))

        self.assertEqual(self._report_entry(report, "fal_inputs")["status"], "failed")
        self.assertEqual(self._report_entry(report, "elevenlabs_voice")["status"], "deleted")
        self.assertEqual(self._report_entry(report, "fal_output")["status"], "deleted")
        self.assertEqual(self._report_entry(report, "local")["status"], "skipped")
        subject.refresh_from_db()
        self.assertEqual(subject.status, "error")
        self.assertEqual(Subject.objects.count(), 1)

    @patch("apps.api.services.subject_service.FalClient")
    @patch("apps.api.services.subject_service.ElevenLabsClient")
    def test_purge_fal_output_failure_still_runs_other_surfaces(self, mock_client_cls, mock_fal_cls):
        mock_fal_cls.return_value.set_file_acl.return_value = None
        mock_fal_cls.return_value.delete_request_payloads.side_effect = ExternalAPIError("fal", "boom")
        subject = Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            photo=make_photo(),
            audio_sample=make_audio(),
            voice_id="voice-123",
            status="voice_ready",
        )
        Job.objects.create(
            subject=subject,
            job_type="video",
            texto="hola",
            fal_request_id="req-1",
            fal_image_url="https://fal.media/files/photo.jpg",
            fal_audio_url="https://fal.media/files/audio.mp3",
        )

        with self.settings(FAL_ADMIN_KEY="admin-secret"):
            report = self.service.purge(str(subject.pk))

        self.assertEqual(self._report_entry(report, "fal_output")["status"], "failed")
        self.assertEqual(self._report_entry(report, "elevenlabs_voice")["status"], "deleted")
        self.assertEqual(self._report_entry(report, "fal_inputs")["status"], "revoked")
        self.assertEqual(self._report_entry(report, "local")["status"], "skipped")
        subject.refresh_from_db()
        self.assertEqual(subject.status, "error")

    @patch("apps.api.services.subject_service.FalClient")
    @patch("apps.api.services.subject_service.ElevenLabsClient")
    def test_purge_without_admin_key_skips_fal_output_only(self, mock_client_cls, mock_fal_cls):
        mock_fal_cls.return_value.set_file_acl.return_value = None
        subject = Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            photo=make_photo(),
            audio_sample=make_audio(),
            voice_id="voice-123",
            status="voice_ready",
        )
        Job.objects.create(
            subject=subject,
            job_type="video",
            texto="hola",
            fal_request_id="req-1",
            fal_image_url="https://fal.media/files/photo.jpg",
            fal_audio_url="https://fal.media/files/audio.mp3",
        )

        with self.settings(FAL_ADMIN_KEY=""):
            report = self.service.purge(str(subject.pk))

        self.assertEqual(self._report_entry(report, "fal_output")["status"], "skipped")
        mock_fal_cls.return_value.delete_request_payloads.assert_not_called()
        self.assertEqual(self._report_entry(report, "elevenlabs_voice")["status"], "deleted")
        self.assertEqual(self._report_entry(report, "fal_inputs")["status"], "revoked")
        self.assertEqual(self._report_entry(report, "local")["status"], "deleted")
        self.assertEqual(Subject.objects.count(), 0)

    @patch("apps.api.services.subject_service.FalClient")
    @patch("apps.api.services.subject_service.ElevenLabsClient")
    def test_purge_voice_only_job_makes_no_fal_calls(self, mock_client_cls, mock_fal_cls):
        subject = Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            photo=make_photo(),
            audio_sample=make_audio(),
            voice_id="voice-123",
            status="voice_ready",
        )
        Job.objects.create(subject=subject, job_type="voice", texto="hola")

        with self.settings(FAL_ADMIN_KEY="admin-secret"):
            report = self.service.purge(str(subject.pk))

        mock_fal_cls.assert_not_called()
        self.assertEqual(self._report_entry(report, "fal_inputs")["status"], "skipped")
        self.assertEqual(self._report_entry(report, "fal_output")["status"], "skipped")
        self.assertEqual(Subject.objects.count(), 0)

    @patch("apps.api.services.subject_service.FalClient")
    @patch("apps.api.services.subject_service.ElevenLabsClient")
    def test_purge_retry_after_partial_failure_is_idempotent(self, mock_client_cls, mock_fal_cls):
        mock_client_cls.return_value.delete_voice.side_effect = ExternalAPIError("elevenlabs", "boom")
        mock_fal_cls.return_value.set_file_acl.return_value = None
        mock_fal_cls.return_value.delete_request_payloads.return_value = None
        subject = Subject.objects.create(
            nombre_display="Ana",
            consent_signed=True,
            photo=make_photo(),
            audio_sample=make_audio(),
            voice_id="voice-123",
            status="voice_ready",
        )
        Job.objects.create(
            subject=subject,
            job_type="video",
            texto="hola",
            fal_request_id="req-1",
            fal_image_url="https://fal.media/files/photo.jpg",
            fal_audio_url="https://fal.media/files/audio.mp3",
        )

        with self.settings(FAL_ADMIN_KEY="admin-secret"):
            first_report = self.service.purge(str(subject.pk))

        self.assertEqual(self._report_entry(first_report, "elevenlabs_voice")["status"], "failed")
        self.assertEqual(self._report_entry(first_report, "fal_inputs")["status"], "revoked")
        self.assertEqual(self._report_entry(first_report, "fal_output")["status"], "deleted")
        subject.refresh_from_db()
        self.assertEqual(subject.status, "error")

        # Second attempt: elevenlabs still fails, but already-cleared surfaces
        # must not error out — they report a terminal state, not new failures.
        with self.settings(FAL_ADMIN_KEY="admin-secret"):
            second_report = self.service.purge(str(subject.pk))

        self.assertEqual(self._report_entry(second_report, "elevenlabs_voice")["status"], "failed")
        self.assertEqual(self._report_entry(second_report, "fal_inputs")["status"], "skipped")
        self.assertEqual(self._report_entry(second_report, "fal_output")["status"], "skipped")
        self.assertEqual(self._report_entry(second_report, "local")["status"], "skipped")
        self.assertEqual(Subject.objects.count(), 1)


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class JobServiceTests(TestCase):
    def setUp(self):
        self.service = JobService()

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

    def test_create_job_invalid_job_type_raises(self):
        subject = self._voice_ready_subject()
        with self.assertRaises(InvalidJobType):
            self.service.create_job(subject_id=str(subject.pk), job_type="bogus", texto="hola")

    def test_create_job_gesture_raises_invalid_job_type(self):
        # "gesture" was removed from Job.JOB_TYPE_CHOICES entirely — a direct
        # service call (bypassing the serializer's ChoiceField) must still be
        # rejected via InvalidJobType, same as any other unknown job_type.
        subject = self._created_subject()
        with self.assertRaises(InvalidJobType):
            self.service.create_job(subject_id=str(subject.pk), job_type="gesture", texto="hola")

    def test_create_job_voice_without_texto_raises(self):
        subject = self._voice_ready_subject()
        with self.assertRaises(TextoRequired):
            self.service.create_job(subject_id=str(subject.pk), job_type="voice", texto="")

    def test_create_job_video_without_texto_raises(self):
        subject = self._voice_ready_subject()
        with self.assertRaises(TextoRequired):
            self.service.create_job(subject_id=str(subject.pk), job_type="video", texto="  ")

    def test_create_job_voice_on_non_voice_ready_subject_raises(self):
        subject = self._created_subject()
        with self.assertRaises(SubjectNotVoiceReady):
            self.service.create_job(subject_id=str(subject.pk), job_type="voice", texto="hola")

    @patch("apps.api.services.job_service.process_job_task")
    def test_create_job_voice_valid_enqueues_task(self, mock_task):
        subject = self._voice_ready_subject()
        with self.captureOnCommitCallbacks(execute=True):
            job = self.service.create_job(subject_id=str(subject.pk), job_type="voice", texto="hola")
        self.assertEqual(job.status, "pending")
        mock_task.delay.assert_called_once_with(str(job.pk))

    @patch("apps.api.services.job_service.ElevenLabsClient")
    def test_process_job_voice_success(self, mock_client_cls):
        mock_client_cls.return_value.text_to_speech.return_value = b"mp3-bytes"
        subject = self._voice_ready_subject()
        job = Job.objects.create(subject=subject, job_type="voice", texto="hola")

        self.service.process_job(str(job.pk))

        job.refresh_from_db()
        self.assertEqual(job.status, "done")
        self.assertTrue(job.audio.name)

    @patch("apps.api.services.job_service.FalClient")
    def test_fal_client_passes_platform_admin_and_ttl_settings(self, mock_fal_cls):
        with override_settings(
            FAL_PLATFORM_URL="https://api.fal.ai/v1",
            FAL_ADMIN_KEY="admin-secret",
            FAL_OBJECT_TTL_SECONDS=1800,
        ):
            self.service._fal_client()

        mock_fal_cls.assert_called_once_with(
            api_key=ANY,
            base_url=ANY,
            storage_url=ANY,
            model=ANY,
            platform_url="https://api.fal.ai/v1",
            admin_key="admin-secret",
            ttl_seconds=1800,
        )

    @patch("apps.api.services.job_service.FalClient")
    @patch("apps.api.services.job_service.ElevenLabsClient")
    def test_process_job_video_persists_fal_input_urls_before_submit(self, mock_el_cls, mock_fal_cls):
        mock_el_cls.return_value.text_to_speech.return_value = b"mp3-bytes"
        mock_fal_cls.return_value.upload_file.side_effect = [
            "https://fal.media/files/photo.jpg",
            "https://fal.media/files/audio.mp3",
        ]

        def _assert_urls_persisted_before_submit(**kwargs):
            job.refresh_from_db()
            self.assertEqual(job.fal_image_url, "https://fal.media/files/photo.jpg")
            self.assertEqual(job.fal_audio_url, "https://fal.media/files/audio.mp3")
            return "req-1"

        mock_fal_cls.return_value.submit_video.side_effect = _assert_urls_persisted_before_submit
        mock_fal_cls.return_value.get_status.return_value = {"status": "COMPLETED"}
        mock_fal_cls.return_value.get_result.return_value = "https://fal.media/files/out.mp4"
        mock_fal_cls.return_value.download.return_value = b"video-bytes"
        subject = self._voice_ready_subject()
        job = Job.objects.create(subject=subject, job_type="video", texto="hola")

        self.service.process_job(str(job.pk))

        job.refresh_from_db()
        self.assertEqual(job.fal_image_url, "https://fal.media/files/photo.jpg")
        self.assertEqual(job.fal_audio_url, "https://fal.media/files/audio.mp3")

    @patch("apps.api.services.job_service.FalClient")
    @patch("apps.api.services.job_service.ElevenLabsClient")
    def test_process_job_video_two_jobs_keep_distinct_fal_urls(self, mock_el_cls, mock_fal_cls):
        mock_el_cls.return_value.text_to_speech.return_value = b"mp3-bytes"
        mock_fal_cls.return_value.upload_file.side_effect = [
            "https://fal.media/files/photo-1.jpg",
            "https://fal.media/files/audio-1.mp3",
            "https://fal.media/files/photo-2.jpg",
            "https://fal.media/files/audio-2.mp3",
        ]
        mock_fal_cls.return_value.submit_video.side_effect = ["req-1", "req-2"]
        mock_fal_cls.return_value.get_status.return_value = {"status": "COMPLETED"}
        mock_fal_cls.return_value.get_result.return_value = "https://fal.media/files/out.mp4"
        mock_fal_cls.return_value.download.return_value = b"video-bytes"
        subject = self._voice_ready_subject()
        job1 = Job.objects.create(subject=subject, job_type="video", texto="hola")
        job2 = Job.objects.create(subject=subject, job_type="video", texto="chau")

        self.service.process_job(str(job1.pk))
        self.service.process_job(str(job2.pk))

        job1.refresh_from_db()
        job2.refresh_from_db()
        self.assertEqual(job1.fal_image_url, "https://fal.media/files/photo-1.jpg")
        self.assertEqual(job2.fal_image_url, "https://fal.media/files/photo-2.jpg")
        self.assertNotEqual(job1.fal_image_url, job2.fal_image_url)

    @patch("apps.api.services.job_service.FalClient")
    @patch("apps.api.services.job_service.ElevenLabsClient")
    def test_process_job_video_success(self, mock_el_cls, mock_fal_cls):
        mock_el_cls.return_value.text_to_speech.return_value = b"mp3-bytes"
        mock_fal_cls.return_value.upload_file.side_effect = [
            "https://fal.media/files/photo.jpg",
            "https://fal.media/files/audio.mp3",
        ]
        mock_fal_cls.return_value.submit_video.return_value = "req-1"
        mock_fal_cls.return_value.get_status.return_value = {"status": "COMPLETED"}
        mock_fal_cls.return_value.get_result.return_value = "https://fal.media/files/out.mp4"
        mock_fal_cls.return_value.download.return_value = b"video-bytes"
        subject = self._voice_ready_subject()
        job = Job.objects.create(subject=subject, job_type="video", texto="hola")

        self.service.process_job(str(job.pk))

        job.refresh_from_db()
        self.assertEqual(job.status, "done")
        self.assertTrue(job.audio.name)
        self.assertTrue(job.video.name)
        self.assertEqual(job.fal_request_id, "req-1")
        self.assertIsNotNone(job.finished_at)
        # Uses the URLs returned by fal.ai upload, not local photo.url
        mock_fal_cls.return_value.submit_video.assert_called_once_with(
            image_url="https://fal.media/files/photo.jpg",
            audio_url="https://fal.media/files/audio.mp3",
            resolution=ANY,
        )

    @patch("apps.api.services.job_service.FalClient")
    @patch("apps.api.services.job_service.ElevenLabsClient")
    def test_process_job_video_declares_real_photo_content_type(self, mock_el_cls, mock_fal_cls):
        """The photo's content type must come from the file, not a hardcoded guess.

        Volunteers upload PNG/GIF as often as JPEG; declaring the wrong type to
        fal storage stores the object with a mismatched Content-Type.
        """
        mock_el_cls.return_value.text_to_speech.return_value = b"mp3-bytes"
        mock_fal_cls.return_value.upload_file.side_effect = [
            "https://fal.media/files/photo.gif",
            "https://fal.media/files/audio.mp3",
        ]
        mock_fal_cls.return_value.submit_video.return_value = "req-1"
        mock_fal_cls.return_value.get_status.return_value = {"status": "COMPLETED"}
        mock_fal_cls.return_value.get_result.return_value = "https://fal.media/files/out.mp4"
        mock_fal_cls.return_value.download.return_value = b"video-bytes"
        subject = self._voice_ready_subject()
        subject.photo.save(
            "photo.png", SimpleUploadedFile("photo.png", b"png-bytes"), save=True
        )
        job = Job.objects.create(subject=subject, job_type="video", texto="hola")

        self.service.process_job(str(job.pk))

        photo_call, audio_call = mock_fal_cls.return_value.upload_file.call_args_list
        self.assertEqual(photo_call.kwargs["content_type"], "image/png")
        self.assertEqual(photo_call.kwargs["file_name"], "photo.png")
        self.assertEqual(audio_call.kwargs["content_type"], "audio/mpeg")

    @patch("apps.api.services.job_service.FalClient")
    @patch("apps.api.services.job_service.ElevenLabsClient")
    def test_process_job_video_upload_failure_sets_error(self, mock_el_cls, mock_fal_cls):
        mock_el_cls.return_value.text_to_speech.return_value = b"mp3-bytes"
        mock_fal_cls.return_value.upload_file.side_effect = ExternalAPIError("fal", "upload failed")
        subject = self._voice_ready_subject()
        job = Job.objects.create(subject=subject, job_type="video", texto="hola")

        with self.assertRaises(ExternalAPIError):
            self.service.process_job(str(job.pk))

    @patch("apps.api.services.job_service.FalClient")
    @patch("apps.api.services.job_service.ElevenLabsClient")
    def test_process_job_video_submit_failure_leaves_no_dangling_request_id(self, mock_el_cls, mock_fal_cls):
        mock_el_cls.return_value.text_to_speech.return_value = b"mp3-bytes"
        mock_fal_cls.return_value.upload_file.side_effect = [
            "https://fal.media/files/photo.jpg",
            "https://fal.media/files/audio.mp3",
        ]
        mock_fal_cls.return_value.submit_video.side_effect = ExternalAPIError("fal", "submit failed")
        subject = self._voice_ready_subject()
        job = Job.objects.create(subject=subject, job_type="video", texto="hola")

        with self.assertRaises(ExternalAPIError):
            self.service.process_job(str(job.pk))

        job.refresh_from_db()
        self.assertFalse(job.fal_request_id)

    @patch("apps.api.services.job_service.time")
    @patch("apps.api.services.job_service.FalClient")
    @patch("apps.api.services.job_service.ElevenLabsClient")
    def test_process_job_video_poll_timeout_raises_fal_poll_timeout(self, mock_el_cls, mock_fal_cls, mock_time):
        mock_el_cls.return_value.text_to_speech.return_value = b"mp3-bytes"
        mock_fal_cls.return_value.upload_file.side_effect = [
            "https://fal.media/files/photo.jpg",
            "https://fal.media/files/audio.mp3",
        ]
        mock_fal_cls.return_value.submit_video.return_value = "req-1"
        mock_fal_cls.return_value.get_status.return_value = {"status": "IN_PROGRESS"}
        # monotonic() called once for the deadline, then keeps advancing past it
        mock_time.monotonic.side_effect = [0.0, 1000.0, 1000.0]
        subject = self._voice_ready_subject()
        job = Job.objects.create(subject=subject, job_type="video", texto="hola")

        with self.assertRaises(FalPollTimeout):
            self.service.process_job(str(job.pk))

        job.refresh_from_db()
        self.assertEqual(job.fal_request_id, "req-1")

    @patch("apps.api.services.job_service.FalClient")
    @patch("apps.api.services.job_service.ElevenLabsClient")
    def test_process_job_video_fal_generation_error_raises(self, mock_el_cls, mock_fal_cls):
        mock_el_cls.return_value.text_to_speech.return_value = b"mp3-bytes"
        mock_fal_cls.return_value.upload_file.side_effect = [
            "https://fal.media/files/photo.jpg",
            "https://fal.media/files/audio.mp3",
        ]
        mock_fal_cls.return_value.submit_video.return_value = "req-1"
        mock_fal_cls.return_value.get_status.return_value = {"status": "ERROR", "error": "model failed"}
        subject = self._voice_ready_subject()
        job = Job.objects.create(subject=subject, job_type="video", texto="hola")

        with self.assertRaises(FalGenerationError):
            self.service.process_job(str(job.pk))

    def test_handlers_contain_only_voice_and_video(self):
        self.assertEqual(set(self.service._handlers.keys()), {"voice", "video"})

    @patch("apps.api.services.job_service.ElevenLabsClient")
    def test_process_job_external_failure_propagates(self, mock_client_cls):
        # Containment lives in the Celery task, not the Service (see process_job_task).
        mock_client_cls.return_value.text_to_speech.side_effect = ExternalAPIError("elevenlabs", "boom")
        subject = self._voice_ready_subject()
        job = Job.objects.create(subject=subject, job_type="voice", texto="hola")

        with self.assertRaises(ExternalAPIError):
            self.service.process_job(str(job.pk))

    def test_mark_error_sets_status_and_error_msg(self):
        subject = self._voice_ready_subject()
        job = Job.objects.create(subject=subject, job_type="voice", texto="hola")

        self.service.mark_error(str(job.pk), "boom")

        job.refresh_from_db()
        self.assertEqual(job.status, "error")
        self.assertEqual(job.error_msg, "boom")
