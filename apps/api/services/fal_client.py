import json

import httpx

from apps.api.services.exceptions import ExternalAPIError

__all__ = ["FalClient", "ExternalAPIError"]


class FalClient:
    """Thin transport-only wrapper around the fal.ai REST API (queue + storage).

    The ONLY code allowed to reach the network for fal.ai video generation
    (`veed/fabric-1.0`). Pure transport: no ORM access, no `time.sleep`, no
    polling loop, no orchestration — that lives in `JobService._process_video`
    / `JobService._poll_fal`, invoked only from Celery.

    Storage uploads follow fal's two-step protocol (see `_upload_via_storage`
    in fal-ai/fal): POST `/storage/upload/initiate` to get a signed
    `upload_url` plus the final `file_url`, then PUT the bytes to that signed
    URL. The signed URL points at GCS, not at fal, and takes no auth header.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        storage_url: str,
        model: str,
        *,
        platform_url: str = "",
        admin_key: str = "",
        ttl_seconds: int = 0,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.storage_url = storage_url
        self.model = model
        self.platform_url = platform_url
        self.admin_key = admin_key
        self.ttl_seconds = ttl_seconds

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=30.0)

    def _storage_client(self) -> httpx.Client:
        return httpx.Client(base_url=self.storage_url, timeout=30.0)

    def _platform_client(self) -> httpx.Client:
        return httpx.Client(base_url=self.platform_url, timeout=30.0)

    def _headers(self) -> dict:
        return {"Authorization": f"Key {self.api_key}"}

    def _admin_headers(self) -> dict:
        return {"Authorization": f"Key {self.admin_key}"}

    def _ttl_headers(self) -> dict:
        if not self.ttl_seconds:
            return {}
        return {
            "X-Fal-Object-Lifecycle-Preference": json.dumps(
                {"expiration_duration_seconds": self.ttl_seconds}
            )
        }

    def upload_file(self, file_obj, content_type: str, file_name: str | None = None) -> str:
        name = file_name or getattr(file_obj, "name", None) or "upload.bin"
        try:
            with self._storage_client() as client:
                initiated = client.post(
                    "/storage/upload/initiate",
                    params={"storage_type": "fal-cdn-v3"},
                    headers={**self._headers(), "Accept": "application/json", **self._ttl_headers()},
                    json={"file_name": name, "content_type": content_type},
                )
                initiated.raise_for_status()
                payload = initiated.json()

                # The signed URL is pre-authorized; sending our API key there is
                # both unnecessary and rejected by GCS.
                uploaded = client.put(
                    payload["upload_url"],
                    content=file_obj.read(),
                    headers={"Content-Type": content_type},
                )
                uploaded.raise_for_status()

                return payload["file_url"]
        except httpx.HTTPError as exc:
            raise ExternalAPIError("fal", str(exc)) from exc
        except (KeyError, ValueError) as exc:
            raise ExternalAPIError("fal", f"respuesta de storage inesperada: {exc}") from exc

    def submit_video(self, image_url: str, audio_url: str, resolution: str) -> str:
        try:
            with self._client() as client:
                response = client.post(
                    f"/{self.model}",
                    headers={**self._headers(), **self._ttl_headers()},
                    json={
                        "image_url": image_url,
                        "audio_url": audio_url,
                        "resolution": resolution,
                    },
                )
                response.raise_for_status()
                return response.json()["request_id"]
        except httpx.HTTPError as exc:
            raise ExternalAPIError("fal", str(exc)) from exc

    def get_status(self, request_id: str) -> dict:
        try:
            with self._client() as client:
                response = client.get(
                    f"/{self.model}/requests/{request_id}/status",
                    headers=self._headers(),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise ExternalAPIError("fal", str(exc)) from exc

    def get_result(self, request_id: str) -> str:
        try:
            with self._client() as client:
                response = client.get(
                    f"/{self.model}/requests/{request_id}",
                    headers=self._headers(),
                )
                response.raise_for_status()
                return response.json()["video"]["url"]
        except httpx.HTTPError as exc:
            raise ExternalAPIError("fal", str(exc)) from exc

    def delete_request_payloads(self, request_id: str, idempotency_key: str | None = None) -> None:
        headers = self._admin_headers()
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            with self._platform_client() as client:
                response = client.delete(
                    f"/models/requests/{request_id}/payloads",
                    headers=headers,
                )
                if response.status_code in (404, 410):
                    return  # already gone — idempotent no-op
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ExternalAPIError("fal", str(exc)) from exc

    def set_file_acl(self, file_url: str, default: str = "hide") -> None:
        try:
            with self._platform_client() as client:
                response = client.put(
                    "/storage/files/acl",
                    params={"url": file_url},
                    headers=self._headers(),
                    json={"default": default},
                )
                if response.status_code in (404, 410):
                    return  # ya expiró solo (TTL) — idempotente, no hay nada que revocar
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ExternalAPIError("fal", str(exc)) from exc

    def download(self, url: str) -> bytes:
        try:
            with self._client() as client:
                response = client.get(url)
                response.raise_for_status()
                return response.content
        except httpx.HTTPError as exc:
            raise ExternalAPIError("fal", str(exc)) from exc
