from apps.api.models import Subject
from apps.api.repositories.base_repository import BaseRepository


class SubjectRepository(BaseRepository):
    model = Subject
