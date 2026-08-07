class ExternalAPIError(Exception):
    """Raised by API clients (services/ layer) on network/timeout/HTTP errors.

    Plain Exception, NOT a DRF APIException — clients must stay transport-only.
    Services are responsible for translating this into user-facing behavior
    (status="error" + error_msg), never propagating it to the HTTP layer directly.
    """

    def __init__(self, provider: str, detail: str):
        self.provider = provider
        self.detail = detail
        super().__init__(f"{provider}: {detail}")


class FalPollTimeout(ExternalAPIError):
    """Raised when polling fal.ai for a request result exceeds FAL_POLL_TIMEOUT.

    Plain Exception subclass (via ExternalAPIError) — fal.ai is only ever
    invoked from within Celery (process_job_task), never during an HTTP
    request/response cycle, so there is no client to respond to here.
    """

    def __init__(self, request_id: str, timeout: float):
        self.request_id = request_id
        self.timeout = timeout
        super().__init__("fal", f"polling request {request_id} exceeded {timeout}s timeout")


class FalGenerationError(ExternalAPIError):
    """Raised when fal.ai reports a terminal error/failure status for a request."""

    def __init__(self, request_id: str, detail: str):
        self.request_id = request_id
        super().__init__("fal", f"request {request_id} failed: {detail}")
