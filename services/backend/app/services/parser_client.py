from __future__ import annotations

import httpx

from app.core.config import get_settings


class ParserClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.parser_service_url.rstrip("/")

    def parse_document(self, *, file_name: str, content_type: str, data: bytes) -> dict:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{self.base_url}/v1/parse",
                files={"file": (file_name, data, content_type)},
            )
            response.raise_for_status()
            return response.json()
