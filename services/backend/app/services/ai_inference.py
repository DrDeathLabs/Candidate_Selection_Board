from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.admin_settings import AdminSettingsService


class GatewayInvocationRequest(BaseModel):
    purpose: str
    prompt: str
    system_prompt: str = ""
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    response_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GatewayInvocationResponse(BaseModel):
    accepted: bool
    provider: str
    model: str
    content: str = ""
    structured_output: dict[str, Any] | list[Any] | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)
    fallback_used: bool = False


@dataclass(slots=True)
class ProviderRuntimeConfig:
    provider: str
    label: str
    base_url: str
    model: str
    api_key_env_var: str
    api_key: str | None
    temperature: float
    max_tokens: int


class AIProviderResolver:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.admin_settings_service = AdminSettingsService()

    def resolve(
        self,
        db: Session,
        *,
        provider_hint: str | None,
        model_hint: str | None,
        temperature_hint: float | None,
        max_tokens_hint: int | None,
    ) -> ProviderRuntimeConfig:
        ai_settings = self.admin_settings_service.get_ai_settings(db)
        provider = provider_hint or ai_settings.default_provider
        provider_config = ai_settings.providers.get(provider)
        if provider_config is None:
            raise ValueError(f"Provider '{provider}' is not configured.")
        if not provider_config.enabled:
            raise ValueError(f"Provider '{provider}' is disabled.")

        model = model_hint or provider_config.default_model
        allowed_models = set(self.settings.allowed_models)
        if allowed_models and model not in allowed_models and model != provider_config.default_model:
            raise ValueError(f"Model '{model}' is not allowed.")

        api_key = os.getenv(provider_config.api_key_env_var) if provider_config.api_key_env_var else None
        return ProviderRuntimeConfig(
            provider=provider,
            label=provider_config.label,
            base_url=provider_config.base_url.rstrip("/"),
            model=model,
            api_key_env_var=provider_config.api_key_env_var,
            api_key=api_key,
            temperature=temperature_hint if temperature_hint is not None else 0.2,
            max_tokens=max_tokens_hint if max_tokens_hint is not None else 4000,
        )


class AIGatewayService:
    def __init__(self) -> None:
        self.provider_resolver = AIProviderResolver()

    def invoke(self, db: Session, request: GatewayInvocationRequest) -> GatewayInvocationResponse:
        runtime = self.provider_resolver.resolve(
            db,
            provider_hint=request.provider,
            model_hint=request.model,
            temperature_hint=request.temperature,
            max_tokens_hint=request.max_tokens,
        )

        system_prompt = request.system_prompt.strip()
        user_prompt = request.prompt.strip()
        if request.response_schema:
            user_prompt = (
                f"{user_prompt}\n\n"
                "Return only JSON. The JSON must match this schema exactly:\n"
                f"{json.dumps(request.response_schema, ensure_ascii=True)}"
            )

        if runtime.provider == "ollama":
            raw_response = self._invoke_ollama(runtime, system_prompt, user_prompt, request.response_schema)
        elif runtime.provider == "openai":
            raw_response = self._invoke_openai(runtime, system_prompt, user_prompt, request.response_schema)
        elif runtime.provider == "claude":
            raw_response = self._invoke_claude(runtime, system_prompt, user_prompt)
        elif runtime.provider == "gemini":
            raw_response = self._invoke_gemini(runtime, system_prompt, user_prompt, request.response_schema)
        else:
            raise ValueError(f"Provider '{runtime.provider}' is not supported.")

        structured_output, validation_errors = self._extract_structured_output(
            raw_response["content"],
            request.response_schema,
        )

        return GatewayInvocationResponse(
            accepted=bool(raw_response["content"]) and (not request.response_schema or structured_output is not None),
            provider=runtime.provider,
            model=runtime.model,
            content=raw_response["content"],
            structured_output=structured_output,
            usage=raw_response["usage"],
            validation_errors=validation_errors,
        )

    def _invoke_ollama(
        self,
        runtime: ProviderRuntimeConfig,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": runtime.model,
            "messages": self._build_messages(system_prompt, user_prompt),
            "stream": False,
            "options": {
                "temperature": runtime.temperature,
                "num_predict": runtime.max_tokens,
            },
        }
        if response_schema:
            payload["format"] = response_schema

        with httpx.Client(timeout=60.0) as client:
            response = client.post(f"{runtime.base_url}/api/chat", json=payload)
            response.raise_for_status()
            body = response.json()

        return {
            "content": str(body.get("message", {}).get("content") or "").strip(),
            "usage": {
                "input_tokens": body.get("prompt_eval_count"),
                "output_tokens": body.get("eval_count"),
            },
        }

    def _invoke_openai(
        self,
        runtime: ProviderRuntimeConfig,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not runtime.api_key:
            raise ValueError(f"Missing API key for provider '{runtime.provider}'.")

        payload: dict[str, Any] = {
            "model": runtime.model,
            "messages": self._build_messages(system_prompt, user_prompt),
            "temperature": runtime.temperature,
            "max_tokens": runtime.max_tokens,
        }
        if response_schema:
            payload["response_format"] = {"type": "json_object"}

        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{runtime.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {runtime.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()

        message = ((body.get("choices") or [{}])[0]).get("message", {})
        return {
            "content": str(message.get("content") or "").strip(),
            "usage": body.get("usage") or {},
        }

    def _invoke_claude(
        self,
        runtime: ProviderRuntimeConfig,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        if not runtime.api_key:
            raise ValueError(f"Missing API key for provider '{runtime.provider}'.")

        payload: dict[str, Any] = {
            "model": runtime.model,
            "max_tokens": runtime.max_tokens,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt
        if runtime.temperature is not None:
            payload["temperature"] = min(max(runtime.temperature, 0.0), 1.0)

        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{runtime.base_url}/messages",
                headers={
                    "x-api-key": runtime.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()

        text_blocks = [block.get("text", "") for block in (body.get("content") or []) if block.get("type") == "text"]
        return {
            "content": "\n".join(block.strip() for block in text_blocks if block).strip(),
            "usage": body.get("usage") or {},
        }

    def _invoke_gemini(
        self,
        runtime: ProviderRuntimeConfig,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not runtime.api_key:
            raise ValueError(f"Missing API key for provider '{runtime.provider}'.")

        generation_config: dict[str, Any] = {
            "temperature": runtime.temperature,
            "maxOutputTokens": runtime.max_tokens,
        }
        if response_schema:
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseJsonSchema"] = response_schema

        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": generation_config,
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{runtime.base_url}/models/{runtime.model}:generateContent?key={runtime.api_key}",
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()

        parts = (((body.get("candidates") or [{}])[0]).get("content") or {}).get("parts") or []
        text = "\n".join(str(part.get("text") or "").strip() for part in parts if part.get("text"))
        return {
            "content": text.strip(),
            "usage": body.get("usageMetadata") or {},
        }

    def _build_messages(self, system_prompt: str, user_prompt: str) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        return messages

    def _extract_structured_output(
        self,
        content: str,
        response_schema: dict[str, Any] | None,
    ) -> tuple[dict[str, Any] | list[Any] | None, list[dict[str, Any]]]:
        if not response_schema:
            return None, []

        parsed = self._parse_json(content)
        if parsed is None:
            return None, [{"message": "Model response was not valid JSON."}]

        validation_errors = self._validate_required_fields(parsed, response_schema)
        return parsed, validation_errors

    def _parse_json(self, content: str) -> dict[str, Any] | list[Any] | None:
        text = content.strip()
        if not text:
            return None

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        start_positions = [position for position in (text.find("{"), text.find("[")) if position >= 0]
        if not start_positions:
            return None
        start = min(start_positions)

        end_object = text.rfind("}")
        end_array = text.rfind("]")
        end_candidates = [position for position in (end_object, end_array) if position >= 0]
        if not end_candidates:
            return None
        end = max(end_candidates) + 1

        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            return None

    def _validate_required_fields(self, payload: Any, schema: dict[str, Any]) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
        if not isinstance(payload, dict):
            return errors

        for field_name in schema.get("required") or []:
            if field_name not in payload:
                errors.append({"message": f"Missing required field '{field_name}'."})
        return errors


class AIGatewayClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.ai_gateway_url.rstrip("/")

    def invoke(self, request: GatewayInvocationRequest) -> GatewayInvocationResponse:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(f"{self.base_url}/v1/invoke", json=request.model_dump(mode="json"))
            response.raise_for_status()
            return GatewayInvocationResponse.model_validate(response.json())
