import io

import httpx
from django.test import SimpleTestCase

from apps.api.services.elevenlabs_client import ElevenLabsClient, ExternalAPIError


def make_client(handler):
    transport = httpx.MockTransport(handler)

    class PatchedClient(ElevenLabsClient):
        def _client(self):
            return httpx.Client(transport=transport, base_url=self.base_url, timeout=30.0)

    return PatchedClient(api_key="key", base_url="https://api.elevenlabs.io")


class ElevenLabsClientTests(SimpleTestCase):
    def test_add_voice_returns_voice_id(self):
        def handler(request):
            return httpx.Response(200, json={"voice_id": "abc123"})

        client = make_client(handler)

        voice_id = client.add_voice("Ana", io.BytesIO(b"audio-bytes"))

        self.assertEqual(voice_id, "abc123")

    def test_add_voice_timeout_raises_external_api_error(self):
        def handler(request):
            raise httpx.TimeoutException("timed out")

        client = make_client(handler)

        with self.assertRaises(ExternalAPIError):
            client.add_voice("Ana", io.BytesIO(b"audio-bytes"))

    def test_add_voice_4xx_raises_external_api_error(self):
        def handler(request):
            return httpx.Response(422, json={"detail": "bad request"})

        client = make_client(handler)

        with self.assertRaises(ExternalAPIError):
            client.add_voice("Ana", io.BytesIO(b"audio-bytes"))

    def test_text_to_speech_returns_bytes(self):
        def handler(request):
            return httpx.Response(200, content=b"mp3-bytes")

        client = make_client(handler)

        audio = client.text_to_speech("voice-id", "hola mundo")

        self.assertEqual(audio, b"mp3-bytes")

    def test_text_to_speech_error_raises_external_api_error(self):
        def handler(request):
            return httpx.Response(500)

        client = make_client(handler)

        with self.assertRaises(ExternalAPIError):
            client.text_to_speech("voice-id", "hola mundo")

    def test_delete_voice_succeeds(self):
        def handler(request):
            return httpx.Response(200, json={"status": "ok"})

        client = make_client(handler)

        client.delete_voice("voice-id")  # should not raise

    def test_delete_voice_error_raises_external_api_error(self):
        def handler(request):
            return httpx.Response(404)

        client = make_client(handler)

        with self.assertRaises(ExternalAPIError):
            client.delete_voice("voice-id")
