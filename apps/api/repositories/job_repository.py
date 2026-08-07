from apps.api.models import Job
from apps.api.repositories.base_repository import BaseRepository


class JobRepository(BaseRepository):
    model = Job
