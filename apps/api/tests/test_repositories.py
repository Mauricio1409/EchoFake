from django.test import TestCase

from apps.api.models import Subject
from apps.api.repositories.subject_repository import SubjectRepository


class BaseRepositoryTests(TestCase):
    def setUp(self):
        self.repo = SubjectRepository()

    def test_create_persists_instance(self):
        subject = self.repo.create(nombre_display="Ana", consent_signed=True)

        self.assertIsNotNone(subject.pk)
        self.assertEqual(Subject.objects.count(), 1)

    def test_get_by_id_returns_instance(self):
        subject = self.repo.create(nombre_display="Ana", consent_signed=True)

        found = self.repo.get_by_id(subject.pk)

        self.assertEqual(found, subject)

    def test_get_by_id_returns_none_when_missing(self):
        found = self.repo.get_by_id("00000000-0000-0000-0000-000000000000")

        self.assertIsNone(found)

    def test_update_sets_fields(self):
        subject = self.repo.create(nombre_display="Ana", consent_signed=True)

        updated = self.repo.update(subject, status="voice_ready")

        self.assertEqual(updated.status, "voice_ready")
        subject.refresh_from_db()
        self.assertEqual(subject.status, "voice_ready")

    def test_delete_removes_instance(self):
        subject = self.repo.create(nombre_display="Ana", consent_signed=True)

        self.repo.delete(subject)

        self.assertEqual(Subject.objects.count(), 0)

    def test_all_returns_queryset_of_all_instances(self):
        self.repo.create(nombre_display="Ana", consent_signed=True)
        self.repo.create(nombre_display="Beto", consent_signed=True)

        self.assertEqual(self.repo.all().count(), 2)
