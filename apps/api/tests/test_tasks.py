from unittest.mock import patch

from django.test import SimpleTestCase

from apps.api.tasks import clone_voice_task, process_job_task


class CloneVoiceTaskTests(SimpleTestCase):
    @patch("apps.api.services.subject_service.SubjectService.clone_voice")
    @patch("apps.api.services.subject_service.SubjectService.mark_error")
    def test_calls_service_clone_voice(self, mock_mark_error, mock_clone_voice):
        clone_voice_task("subject-1")

        mock_clone_voice.assert_called_once_with("subject-1")
        mock_mark_error.assert_not_called()

    @patch("apps.api.services.subject_service.SubjectService.clone_voice")
    @patch("apps.api.services.subject_service.SubjectService.mark_error")
    def test_swallows_exception_and_marks_error(self, mock_mark_error, mock_clone_voice):
        mock_clone_voice.side_effect = RuntimeError("boom")

        clone_voice_task("subject-1")  # must NOT raise

        mock_mark_error.assert_called_once_with("subject-1", "boom")


class ProcessJobTaskTests(SimpleTestCase):
    @patch("apps.api.services.job_service.JobService.process_job")
    @patch("apps.api.services.job_service.JobService.mark_error")
    def test_calls_service_process_job(self, mock_mark_error, mock_process_job):
        process_job_task("job-1")

        mock_process_job.assert_called_once_with("job-1")
        mock_mark_error.assert_not_called()

    @patch("apps.api.services.job_service.JobService.process_job")
    @patch("apps.api.services.job_service.JobService.mark_error")
    def test_swallows_exception_and_marks_error(self, mock_mark_error, mock_process_job):
        mock_process_job.side_effect = RuntimeError("boom")

        process_job_task("job-1")  # must NOT raise

        mock_mark_error.assert_called_once_with("job-1", "boom")
