from django.conf import settings
from django.db import transaction

from apps.api.exceptions import ConsentRequired, SubjectNotFound
from apps.api.repositories.job_repository import JobRepository
from apps.api.repositories.subject_repository import SubjectRepository
from apps.api.services.elevenlabs_client import ElevenLabsClient
from apps.api.services.exceptions import ExternalAPIError
from apps.api.services.fal_client import FalClient
from apps.api.tasks import clone_voice_task


class SubjectService:
    def __init__(self):
        self.repository = SubjectRepository()
        self.job_repository = JobRepository()

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
    def create_subject(self, *, nombre_display, consent_signed, photo, audio_sample):
        if not consent_signed:
            raise ConsentRequired()

        subject = self.repository.create(
            nombre_display=nombre_display,
            consent_signed=consent_signed,
            photo=photo,
            audio_sample=audio_sample,
        )
        transaction.on_commit(lambda: clone_voice_task.delay(str(subject.pk)))
        return subject

    def clone_voice(self, subject_id):
        """Perform the ElevenLabs voice-clone call. Raises ExternalAPIError on failure —
        failure containment (mark_error) lives in clone_voice_task, not here."""
        subject = self.repository.get_by_id(subject_id)
        if subject is None:
            return

        client = self._elevenlabs_client()
        voice_id = client.add_voice(subject.nombre_display, subject.audio_sample.open("rb"))
        self.repository.update(subject, voice_id=voice_id, status="voice_ready")

    def mark_error(self, subject_id, error_detail=None):
        subject = self.repository.get_by_id(subject_id)
        if subject is None:
            return
        self.repository.update(subject, status="error")

    def purge(self, subject_id):
        """Orchestrate deletion/revocation across 4 surfaces and return a per-surface report.

        Never raises on an individual surface failure (see full-data-purge design.md
        decision #5) — SubjectNotFound is the only failure that aborts the operation.
        Remote surfaces run first, while identifiers still exist in the DB; local
        runs last and only if none of the remote surfaces failed.
        """
        subject = self.repository.get_by_id(subject_id)
        if subject is None:
            raise SubjectNotFound()

        subject_pk = str(subject.pk)
        jobs = list(subject.jobs.all())
        voice_id = subject.voice_id

        report = [
            self._purge_voice(subject, voice_id),
            self._purge_fal_inputs(jobs),
            self._purge_fal_output(jobs),
        ]
        report.append(self._purge_local(subject, jobs, report))

        return {"subject_id": subject_pk, "report": report}

    def _purge_voice(self, subject, voice_id):
        if not voice_id:
            return {"surface": "elevenlabs_voice", "status": "skipped", "detail": "sin voz clonada"}

        try:
            self._elevenlabs_client().delete_voice(voice_id)
        except ExternalAPIError as exc:
            return {"surface": "elevenlabs_voice", "status": "failed", "detail": str(exc)}

        self.repository.update(subject, voice_id=None)
        return {"surface": "elevenlabs_voice", "status": "deleted", "detail": ""}

    def _purge_fal_inputs(self, jobs):
        targets = []
        for job in jobs:
            if job.fal_image_url:
                targets.append((job, "fal_image_url", job.fal_image_url))
            if job.fal_audio_url:
                targets.append((job, "fal_audio_url", job.fal_audio_url))

        if not targets:
            return {"surface": "fal_inputs", "status": "skipped", "detail": "sin objetos en fal"}

        fal = self._fal_client()
        succeeded = 0
        failed = 0
        for job, field_name, url in targets:
            try:
                fal.set_file_acl(url, "hide")
            except ExternalAPIError:
                failed += 1
                continue
            self.job_repository.update(job, **{field_name: None})
            succeeded += 1

        if failed:
            return {
                "surface": "fal_inputs",
                "status": "failed",
                "detail": f"{succeeded}/{len(targets)} revocados; {failed} fallaron",
            }
        return {
            "surface": "fal_inputs",
            "status": "revoked",
            "detail": f"{succeeded} objeto(s) revocado(s); expiran en <={settings.FAL_OBJECT_TTL_SECONDS}s",
        }

    def _purge_fal_output(self, jobs):
        if not settings.FAL_ADMIN_KEY:
            return {"surface": "fal_output", "status": "skipped", "detail": "FAL_ADMIN_KEY no configurada"}

        targets = [job for job in jobs if job.fal_request_id]
        if not targets:
            return {"surface": "fal_output", "status": "skipped", "detail": "sin objetos en fal"}

        fal = self._fal_client()
        succeeded = 0
        failed = 0
        for job in targets:
            try:
                fal.delete_request_payloads(job.fal_request_id)
            except ExternalAPIError:
                failed += 1
                continue
            self.job_repository.update(job, fal_request_id=None)
            succeeded += 1

        if failed:
            return {
                "surface": "fal_output",
                "status": "failed",
                "detail": f"{succeeded}/{len(targets)} eliminados; {failed} fallaron",
            }
        return {"surface": "fal_output", "status": "deleted", "detail": ""}

    def _purge_local(self, subject, jobs, report):
        failed_surfaces = [entry["surface"] for entry in report if entry["status"] == "failed"]
        if failed_surfaces:
            self.repository.update(subject, status="error")
            return {
                "surface": "local",
                "status": "skipped",
                "detail": f"conservado para reintento: {', '.join(failed_surfaces)} fallaron",
            }

        with transaction.atomic():
            for job in jobs:
                self._delete_file(job.audio)
                self._delete_file(job.video)
                self.job_repository.delete(job)
            self._delete_file(subject.photo)
            self._delete_file(subject.audio_sample)
            self.repository.delete(subject)

        return {"surface": "local", "status": "deleted", "detail": ""}

    @staticmethod
    def _delete_file(file_field):
        if file_field and file_field.name:
            file_field.delete(save=False)
