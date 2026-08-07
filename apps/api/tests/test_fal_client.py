import io
import json

import httpx
from django.test import SimpleTestCase

from apps.api.services.fal_client import FalClient
from apps.api.services.exceptions import ExternalAPIError


def make_client(handler, *, storage_handler=None, platform_handler=None, admin_key="", ttl_seconds=0):
    transport = httpx.MockTransport(handler)
    storage_transport = httpx.MockTransport(storage_handler or handler)
    platform_transport = httpx.MockTransport(platform_handler or handler)

    class PatchedClient(FalClient):
        def _client(self):
            return httpx.Client(transport=transport, base_url=self.base_url, timeout=30.0)

        def _storage_client(self):
            return httpx.Client(transport=storage_transport, base_url=self.storage_url, timeout=30.0)

        def _platform_client(self):
            return httpx.Client(transport=platform_transport, base_url=self.platform_url, timeout=30.0)

    return PatchedClient(
        api_key="key",
        base_url="https://queue.fal.run",
        storage_url="https://rest.fal.ai",
        model="veed/fabric-1.0",
        platform_url="https://api.fal.ai/v1",
        admin_key=admin_key,
        ttl_seconds=ttl_seconds,
    )


class FalClientTests(SimpleTestCase):
    def test_upload_file_initiates_then_puts_and_returns_file_url(self):
        """fal storage is a two-step protocol: initiate, then PUT to the signed URL.

        Asserts the real contract from fal-ai/fal `_upload_via_storage`, not the
        single multipart POST this client originally guessed (which 404'd).
        """
        seen = []

        def handler(request):
            seen.append(request)
            if request.url.path == "/storage/upload/initiate":
                return httpx.Response(
                    200,
                    json={
                        "upload_url": "https://storage.googleapis.com/signed/put",
                        "file_url": "https://v3.fal.media/files/photo.jpg",
                    },
                )
            return httpx.Response(200)

        client = make_client(None, storage_handler=handler)

        url = client.upload_file(
            io.BytesIO(b"image-bytes"), content_type="image/jpeg", file_name="photo.jpg"
        )

        self.assertEqual(url, "https://v3.fal.media/files/photo.jpg")
        self.assertEqual(len(seen), 2)

        initiate, upload = seen
        self.assertEqual(initiate.method, "POST")
        self.assertEqual(initiate.url.host, "rest.fal.ai")
        # "gcs" is fal's legacy fallback repository and is rejected with
        # {"detail": "Invalid storage type"} — verified against the live API.
        self.assertEqual(initiate.url.params.get("storage_type"), "fal-cdn-v3")
        self.assertEqual(initiate.headers["Authorization"], "Key key")
        self.assertEqual(
            json.loads(initiate.content),
            {"file_name": "photo.jpg", "content_type": "image/jpeg"},
        )

        self.assertEqual(upload.method, "PUT")
        self.assertEqual(str(upload.url), "https://storage.googleapis.com/signed/put")
        self.assertEqual(upload.headers["Content-Type"], "image/jpeg")
        self.assertEqual(upload.content, b"image-bytes")

    def test_upload_file_defaults_file_name_when_missing(self):
        def handler(request):
            if request.url.path == "/storage/upload/initiate":
                return httpx.Response(
                    200,
                    json={"upload_url": "https://signed/put", "file_url": "https://f/x"},
                )
            return httpx.Response(200)

        client = make_client(None, storage_handler=handler)

        url = client.upload_file(io.BytesIO(b"bytes"), content_type="audio/mpeg")

        self.assertEqual(url, "https://f/x")

    def test_upload_file_initiate_error_raises_external_api_error(self):
        def handler(request):
            return httpx.Response(404)

        client = make_client(None, storage_handler=handler)

        with self.assertRaises(ExternalAPIError):
            client.upload_file(io.BytesIO(b"image-bytes"), content_type="image/jpeg")

    def test_upload_file_sends_ttl_header_on_initiate(self):
        seen = []

        def handler(request):
            seen.append(request)
            if request.url.path == "/storage/upload/initiate":
                return httpx.Response(
                    200,
                    json={"upload_url": "https://signed/put", "file_url": "https://f/x"},
                )
            return httpx.Response(200)

        client = make_client(None, storage_handler=handler, ttl_seconds=3600)

        client.upload_file(io.BytesIO(b"bytes"), content_type="audio/mpeg")

        initiate = seen[0]
        self.assertEqual(
            initiate.headers["X-Fal-Object-Lifecycle-Preference"],
            json.dumps({"expiration_duration_seconds": 3600}),
        )

    def test_upload_file_put_error_raises_external_api_error(self):
        def handler(request):
            if request.url.path == "/storage/upload/initiate":
                return httpx.Response(
                    200,
                    json={"upload_url": "https://signed/put", "file_url": "https://f/x"},
                )
            return httpx.Response(403)

        client = make_client(None, storage_handler=handler)

        with self.assertRaises(ExternalAPIError):
            client.upload_file(io.BytesIO(b"image-bytes"), content_type="image/jpeg")

    def test_submit_video_returns_request_id(self):
        def handler(request):
            return httpx.Response(200, json={"request_id": "req-1"})

        client = make_client(handler)

        request_id = client.submit_video(
            image_url="https://fal.media/files/photo.jpg",
            audio_url="https://fal.media/files/audio.mp3",
            resolution="480p",
        )

        self.assertEqual(request_id, "req-1")

    def test_submit_video_sends_ttl_header(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(200, json={"request_id": "req-1"})

        client = make_client(handler, ttl_seconds=3600)

        client.submit_video(
            image_url="https://fal.media/files/photo.jpg",
            audio_url="https://fal.media/files/audio.mp3",
            resolution="480p",
        )

        self.assertEqual(
            seen[0].headers["X-Fal-Object-Lifecycle-Preference"],
            json.dumps({"expiration_duration_seconds": 3600}),
        )

    def test_submit_video_error_raises_external_api_error(self):
        def handler(request):
            return httpx.Response(400, json={"detail": "bad request"})

        client = make_client(handler)

        with self.assertRaises(ExternalAPIError):
            client.submit_video(
                image_url="https://fal.media/files/photo.jpg",
                audio_url="https://fal.media/files/audio.mp3",
                resolution="480p",
            )

    def test_get_status_returns_status_dict(self):
        def handler(request):
            return httpx.Response(200, json={"status": "IN_PROGRESS"})

        client = make_client(handler)

        data = client.get_status("req-1")

        self.assertEqual(data["status"], "IN_PROGRESS")

    def test_get_status_error_raises_external_api_error(self):
        def handler(request):
            return httpx.Response(404)

        client = make_client(handler)

        with self.assertRaises(ExternalAPIError):
            client.get_status("req-1")

    def test_get_result_returns_video_url(self):
        def handler(request):
            return httpx.Response(200, json={"video": {"url": "https://fal.media/files/out.mp4"}})

        client = make_client(handler)

        url = client.get_result("req-1")

        self.assertEqual(url, "https://fal.media/files/out.mp4")

    def test_get_result_error_raises_external_api_error(self):
        def handler(request):
            return httpx.Response(500)

        client = make_client(handler)

        with self.assertRaises(ExternalAPIError):
            client.get_result("req-1")

    def test_download_returns_bytes(self):
        def handler(request):
            return httpx.Response(200, content=b"video-bytes")

        client = make_client(handler)

        content = client.download("https://fal.media/files/out.mp4")

        self.assertEqual(content, b"video-bytes")

    def test_download_error_raises_external_api_error(self):
        def handler(request):
            return httpx.Response(500)

        client = make_client(handler)

        with self.assertRaises(ExternalAPIError):
            client.download("https://fal.media/files/out.mp4")

    def test_delete_request_payloads_success_hits_platform_endpoint(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(204)

        client = make_client(None, platform_handler=handler, admin_key="admin-key")

        client.delete_request_payloads("req-1")

        self.assertEqual(len(seen), 1)
        request = seen[0]
        self.assertEqual(request.method, "DELETE")
        self.assertEqual(str(request.url), "https://api.fal.ai/v1/models/requests/req-1/payloads")
        self.assertEqual(request.headers["Authorization"], "Key admin-key")

    def test_delete_request_payloads_sets_idempotency_key_header(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(204)

        client = make_client(None, platform_handler=handler, admin_key="admin-key")

        client.delete_request_payloads("req-1", idempotency_key="idem-1")

        self.assertEqual(seen[0].headers["Idempotency-Key"], "idem-1")

    def test_delete_request_payloads_404_is_silent_noop(self):
        def handler(request):
            return httpx.Response(404)

        client = make_client(None, platform_handler=handler, admin_key="admin-key")

        client.delete_request_payloads("req-1")  # must not raise

    def test_delete_request_payloads_410_is_silent_noop(self):
        def handler(request):
            return httpx.Response(410)

        client = make_client(None, platform_handler=handler, admin_key="admin-key")

        client.delete_request_payloads("req-1")  # must not raise

    def test_delete_request_payloads_http_error_raises_external_api_error(self):
        def handler(request):
            return httpx.Response(500)

        client = make_client(None, platform_handler=handler, admin_key="admin-key")

        with self.assertRaises(ExternalAPIError):
            client.delete_request_payloads("req-1")

    def test_set_file_acl_success_hits_platform_endpoint(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(200)

        client = make_client(None, platform_handler=handler)

        client.set_file_acl("https://v3.fal.media/files/b/abc/photo.jpg")

        self.assertEqual(len(seen), 1)
        request = seen[0]
        self.assertEqual(request.method, "PUT")
        self.assertEqual(request.url.path, "/v1/storage/files/acl")
        self.assertEqual(
            request.url.params.get("url"), "https://v3.fal.media/files/b/abc/photo.jpg"
        )
        self.assertEqual(request.headers["Authorization"], "Key key")
        self.assertEqual(json.loads(request.content), {"default": "hide"})

    def test_set_file_acl_custom_default_sent_in_body(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(200)

        client = make_client(None, platform_handler=handler)

        client.set_file_acl("https://v3.fal.media/files/b/abc/photo.jpg", default="allow")

        self.assertEqual(json.loads(seen[0].content), {"default": "allow"})

    def test_set_file_acl_http_error_raises_external_api_error(self):
        def handler(request):
            return httpx.Response(403)

        client = make_client(None, platform_handler=handler)

        with self.assertRaises(ExternalAPIError):
            client.set_file_acl("https://v3.fal.media/files/b/abc/photo.jpg")

    def test_ttl_headers_empty_when_ttl_seconds_falsy(self):
        client = make_client(None, ttl_seconds=0)

        self.assertEqual(client._ttl_headers(), {})

    def test_ttl_headers_present_when_ttl_seconds_set(self):
        client = make_client(None, ttl_seconds=3600)

        self.assertEqual(
            client._ttl_headers(),
            {"X-Fal-Object-Lifecycle-Preference": json.dumps({"expiration_duration_seconds": 3600})},
        )
