from rest_framework import serializers

from apps.api.models import Job, Subject


class SubjectCreateSerializer(serializers.ModelSerializer):
    photo = serializers.ImageField(required=True)
    audio_sample = serializers.FileField(required=True)

    class Meta:
        model = Subject
        fields = ["nombre_display", "consent_signed", "photo", "audio_sample"]

    def validate_consent_signed(self, value):
        if not value:
            raise serializers.ValidationError("Consent must be signed.")
        return value


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = [
            "id",
            "nombre_display",
            "status",
            "photo",
            "created_at",
        ]
        read_only_fields = fields


class JobCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = ["subject", "job_type", "texto"]

    def validate(self, attrs):
        job_type = attrs.get("job_type")
        texto = attrs.get("texto", "")
        if job_type in ("voice", "video") and not texto.strip():
            raise serializers.ValidationError({"texto": "texto is required for this job type."})
        return attrs


class PurgeSurfaceSerializer(serializers.Serializer):
    surface = serializers.CharField()
    status = serializers.CharField()
    detail = serializers.CharField()


class PurgeReportSerializer(serializers.Serializer):
    subject_id = serializers.CharField()
    report = PurgeSurfaceSerializer(many=True)


class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = [
            "id",
            "subject",
            "job_type",
            "status",
            "error_msg",
            "audio",
            "video",
            "created_at",
            "finished_at",
        ]
        read_only_fields = fields
