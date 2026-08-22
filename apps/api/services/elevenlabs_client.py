import httpx

from apps.api.services.exceptions import ExternalAPIError

__all__ = ["ElevenLabsClient", "ExternalAPIError"]


class ElevenLabsClient:
    """Thin transport-only wrapper around the ElevenLabs REST API.

    The ONLY code allowed to reach the network for voice cloning / TTS.
    """

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=30.0)

    def _headers(self) -> dict:
        return {"xi-api-key": self.api_key}

    def add_voice(self, name: str, audio_file) -> str:
        try:
            with self._client() as client:
                response = client.post(
                    "/v1/voices/add",
                    headers=self._headers(),
                    data={"name": name},
                    files={"files": audio_file},
                )
                response.raise_for_status()
                return response.json()["voice_id"]
        except httpx.HTTPError as exc:
            raise ExternalAPIError("elevenlabs", str(exc)) from exc

    def text_to_speech(self, voice_id: str, text: str) -> bytes:
        try:
            with self._client() as client:
                response = client.post(
                    f"/v1/text-to-speech/{voice_id}",
                    headers=self._headers(),
                    json={
                        "text": text,
                        "model_id": "eleven_multilingual_v2",
                        "voice_settings": {
                            "stability": 0.30,
                            "similarity_boost": 1.0,
                            "style": 0.20,
                            "use_speaker_boost": True,
                            "speed": 0.84,
                        },
                    },
                )
                response.raise_for_status()
                return response.content
        except httpx.HTTPError as exc:
            raise ExternalAPIError("elevenlabs", str(exc)) from exc

    def delete_voice(self, voice_id: str) -> None:
        try:
            with self._client() as client:
                response = client.delete(
                    f"/v1/voices/{voice_id}",
                    headers=self._headers(),
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ExternalAPIError("elevenlabs", str(exc)) from exc
