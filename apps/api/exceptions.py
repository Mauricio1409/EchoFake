from rest_framework.exceptions import APIException
from rest_framework import status


class ConsentRequired(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Consent must be signed to create a Subject."
    default_code = "consent_required"


class SubjectNotVoiceReady(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Subject must have a ready voice clone for this job type."
    default_code = "subject_not_voice_ready"


class TextoRequired(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "texto is required for this job type."
    default_code = "texto_required"


class InvalidJobType(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid job_type."
    default_code = "invalid_job_type"


class SubjectNotFound(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Subject not found."
    default_code = "subject_not_found"
