from apps.api.models import Job
from apps.api.repositories.base_repository import BaseRepository


class JobRepository(BaseRepository):
    model = Job

    def list_by_subject(self, subject_id):
        return self.model.objects.filter(subject_id=subject_id).order_by("created_at")
