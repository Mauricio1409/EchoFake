import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def clone_voice_task(subject_id):
    from apps.api.services.subject_service import SubjectService

    service = SubjectService()
    try:
        service.clone_voice(subject_id)
    except Exception as exc:  # noqa: BLE001 - worker must never crash
        logger.exception("clone_voice_task failed for subject %s", subject_id)
        service.mark_error(subject_id, str(exc))


@shared_task
def process_job_task(job_id):
    from apps.api.services.job_service import JobService

    service = JobService()
    try:
        service.process_job(job_id)
    except Exception as exc:  # noqa: BLE001 - worker must never crash
        logger.exception("process_job_task failed for job %s", job_id)
        service.mark_error(job_id, str(exc))
