from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.api.serializers import (
    JobCreateSerializer,
    JobSerializer,
    PurgeReportSerializer,
    SubjectCreateSerializer,
    SubjectSerializer,
)
from apps.api.services.job_service import JobService
from apps.api.services.subject_service import SubjectService


class SubjectViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = SubjectService()

    def get_serializer_class(self):
        if self.action == "create":
            return SubjectCreateSerializer
        return SubjectSerializer

    def get_queryset(self):
        return self.service.repository.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subject = self.service.create_subject(**serializer.validated_data)
        output = SubjectSerializer(subject, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"])
    def purge(self, request, pk=None):
        report = self.service.purge(pk)
        return Response(PurgeReportSerializer(report).data, status=status.HTTP_200_OK)


class JobViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = JobService()

    def get_serializer_class(self):
        if self.action == "create":
            return JobCreateSerializer
        return JobSerializer

    def get_queryset(self):
        return self.service.repository.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = self.service.create_job(
            subject_id=str(serializer.validated_data["subject"].pk),
            job_type=serializer.validated_data["job_type"],
            texto=serializer.validated_data.get("texto", ""),
        )
        output = JobSerializer(job, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)
