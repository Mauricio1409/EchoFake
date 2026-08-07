class BaseRepository:
    """Encapsulates ALL ORM access for a single model. No business logic here."""

    model = None

    def get_by_id(self, pk):
        return self.model.objects.filter(pk=pk).first()

    def create(self, **kwargs):
        return self.model.objects.create(**kwargs)

    def update(self, instance, **kwargs):
        for field, value in kwargs.items():
            setattr(instance, field, value)
        instance.save(update_fields=list(kwargs.keys()))
        return instance

    def delete(self, instance):
        instance.delete()

    def all(self):
        return self.model.objects.all()
