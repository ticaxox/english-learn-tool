from __future__ import annotations

import asyncio
import base64
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.config import Settings

_BLOCKED_HOSTS = {
    "metadata",
    "metadata.google.internal",
    "metadata.azure.com",
    "169.254.169.254",
    "100.100.100.200",
}
_TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}


@dataclass
class ProviderRequestError(Exception):
    code: str
    message: str
    retryable: bool
    status_code: int | None = None

    def __str__(self) -> str:
        return self.message


def _is_private_or_local(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def validate_provider_url(url: str, settings: Settings) -> str:
    """Validate a provider URL and resolve every address before any request is made."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ProviderRequestError(
            code="AI_PROVIDER_URL_INVALID",
            message="The provider URL is invalid.",
            retryable=False,
        ) from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port is not None
        and not 1 <= port <= 65535
    ):
        raise ProviderRequestError(
            code="AI_PROVIDER_URL_INVALID",
            message="The provider URL is invalid.",
            retryable=False,
        )
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname in _BLOCKED_HOSTS or hostname.endswith(".localhost"):
        raise ProviderRequestError(
            code="AI_PROVIDER_URL_BLOCKED",
            message="The provider URL is not allowed.",
            retryable=False,
        )
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ProviderRequestError(
            code="AI_PROVIDER_DNS_FAILED",
            message="The provider host could not be resolved.",
            retryable=False,
        ) from exc
    resolved = {entry[4][0] for entry in addresses}
    if not resolved:
        raise ProviderRequestError(
            code="AI_PROVIDER_DNS_FAILED",
            message="The provider host could not be resolved.",
            retryable=False,
        )
    for address in resolved:
        if address in _BLOCKED_HOSTS:
            raise ProviderRequestError(
                code="AI_PROVIDER_URL_BLOCKED",
                message="The provider URL is not allowed.",
                retryable=False,
            )
        if not settings.ai_allow_private_provider_urls and _is_private_or_local(address):
            raise ProviderRequestError(
                code="AI_PROVIDER_URL_BLOCKED",
                message="The provider URL is not allowed.",
                retryable=False,
            )
    return url.rstrip("/")


def _same_origin(left: str, right: str) -> bool:
    left_parts = urlsplit(left)
    right_parts = urlsplit(right)
    return (
        left_parts.scheme,
        left_parts.hostname,
        left_parts.port,
    ) == (
        right_parts.scheme,
        right_parts.hostname,
        right_parts.port,
    )


class ProviderHttpClient:
    """Minimal OpenAI-compatible HTTP adapter with bounded redirects and safe error mapping."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def _request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        timeout_seconds: int,
        json: dict[str, object] | None = None,
    ) -> dict[str, object]:
        current = await validate_provider_url(url, self.settings)
        redirects = 0
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            while True:
                try:
                    # A hard wall-clock deadline: httpx phase timeouts alone let a
                    # slow-drip response hold the worker far beyond the budget.
                    async with asyncio.timeout(timeout_seconds):
                        response = await client.request(method, current, headers=headers, json=json)
                except (TimeoutError, httpx.TimeoutException) as exc:
                    raise ProviderRequestError(
                        code="AI_PROVIDER_TIMEOUT",
                        message="The AI provider timed out.",
                        retryable=True,
                    ) from exc
                except httpx.HTTPError as exc:
                    raise ProviderRequestError(
                        code="AI_PROVIDER_NETWORK",
                        message="The AI provider could not be reached.",
                        retryable=True,
                    ) from exc

                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location or redirects >= self.settings.ai_provider_redirect_limit:
                        raise ProviderRequestError(
                            code="AI_PROVIDER_REDIRECT_BLOCKED",
                            message="The AI provider returned an unsafe redirect.",
                            retryable=False,
                        )
                    next_url = urljoin(current, location)
                    if not _same_origin(current, next_url):
                        raise ProviderRequestError(
                            code="AI_PROVIDER_REDIRECT_BLOCKED",
                            message="The AI provider returned an unsafe redirect.",
                            retryable=False,
                        )
                    current = await validate_provider_url(next_url, self.settings)
                    redirects += 1
                    continue

                if response.status_code >= 400:
                    raise self._map_status(response.status_code)
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise ProviderRequestError(
                        code="AI_PROVIDER_INVALID_JSON",
                        message="The AI provider returned invalid JSON.",
                        retryable=False,
                    ) from exc
                if not isinstance(payload, dict):
                    raise ProviderRequestError(
                        code="AI_PROVIDER_INVALID_JSON",
                        message="The AI provider returned an invalid response.",
                        retryable=False,
                    )
                return payload

    @staticmethod
    def _map_status(status: int) -> ProviderRequestError:
        if status in {401, 403}:
            return ProviderRequestError(
                code="AI_PROVIDER_AUTH_FAILED",
                message="The AI provider rejected its credentials.",
                retryable=False,
                status_code=status,
            )
        if status in {400, 404, 405, 409, 422}:
            return ProviderRequestError(
                code="AI_PROVIDER_INVALID_REQUEST",
                message="The AI provider rejected the request.",
                retryable=False,
                status_code=status,
            )
        if status == 429:
            return ProviderRequestError(
                code="AI_PROVIDER_RATE_LIMITED",
                message="The AI provider is rate limited.",
                retryable=True,
                status_code=status,
            )
        if status in _TRANSIENT_STATUS or status >= 500:
            return ProviderRequestError(
                code="AI_PROVIDER_UNAVAILABLE",
                message="The AI provider is temporarily unavailable.",
                retryable=True,
                status_code=status,
            )
        return ProviderRequestError(
            code="AI_PROVIDER_HTTP_ERROR",
            message="The AI provider request failed.",
            retryable=False,
            status_code=status,
        )

    def headers(self, api_key: str, custom_headers: dict[str, str]) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}", **custom_headers}

    async def list_models(
        self,
        *,
        base_url: str,
        api_key: str,
        custom_headers: dict[str, str],
        timeout_seconds: int,
    ) -> list[str]:
        payload = await self._request(
            method="GET",
            url=f"{base_url.rstrip('/')}/models",
            headers=self.headers(api_key, custom_headers),
            timeout_seconds=timeout_seconds,
        )
        data = payload.get("data")
        if not isinstance(data, list):
            raise ProviderRequestError(
                code="AI_PROVIDER_INVALID_RESPONSE",
                message="The AI provider returned an invalid model list.",
                retryable=False,
            )
        models = []
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                models.append(item["id"])
        return sorted(set(models))

    async def embeddings(
        self,
        *,
        base_url: str,
        api_key: str,
        custom_headers: dict[str, str],
        model_id: str,
        timeout_seconds: int,
        texts: list[str],
    ) -> list[list[float]]:
        """OpenAI-compatible embeddings; one vector per input, in order."""
        payload = await self._request(
            method="POST",
            url=f"{base_url.rstrip('/')}/embeddings",
            headers=self.headers(api_key, custom_headers),
            timeout_seconds=timeout_seconds,
            json={"model": model_id, "input": texts},
        )
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise ProviderRequestError(
                code="AI_PROVIDER_INVALID_RESPONSE",
                message="The AI provider returned an invalid embedding response.",
                retryable=False,
            )
        vectors: list[list[float]] = []
        for item in data:
            vector = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(vector, list) or not vector:
                raise ProviderRequestError(
                    code="AI_PROVIDER_INVALID_RESPONSE",
                    message="The AI provider returned an invalid embedding vector.",
                    retryable=False,
                )
            vectors.append([float(value) for value in vector])
        return vectors

    async def chat_json(
        self,
        *,
        base_url: str,
        api_key: str,
        custom_headers: dict[str, str],
        model_id: str,
        timeout_seconds: int,
        system_prompt: str,
        user_content: str,
        schema_name: str,
        schema: dict[str, object],
        images: list[tuple[str, bytes]] | None = None,
    ) -> str:
        # OpenAI-compatible vision: the user turn becomes a content array with
        # the text first and one image_url part per attachment.
        user_message: object = user_content
        if images:
            user_message = [
                {"type": "text", "text": user_content},
                *[
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": (
                                f"data:{content_type};base64,{base64.b64encode(payload).decode()}"
                            )
                        },
                    }
                    for content_type, payload in images
                ],
            ]
        request_body: dict[str, object] = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.2,
            "max_tokens": self.settings.ai_provider_max_tokens,
        }
        request_body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        }
        try:
            payload = await self._request(
                method="POST",
                url=f"{base_url.rstrip('/')}/chat/completions",
                headers={
                    **self.headers(api_key, custom_headers),
                    "Content-Type": "application/json",
                },
                timeout_seconds=timeout_seconds,
                json=request_body,
            )
        except ProviderRequestError as exc:
            # Some OpenAI-compatible gateways support JSON mode but not JSON Schema.
            if exc.status_code not in {400, 422}:
                raise
            request_body["response_format"] = {"type": "json_object"}
            payload = await self._request(
                method="POST",
                url=f"{base_url.rstrip('/')}/chat/completions",
                headers={
                    **self.headers(api_key, custom_headers),
                    "Content-Type": "application/json",
                },
                timeout_seconds=timeout_seconds,
                json=request_body,
            )
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderRequestError(
                code="AI_PROVIDER_INVALID_RESPONSE",
                message="The AI provider returned no completion.",
                retryable=False,
            )
        message = choices[0].get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ProviderRequestError(
                code="AI_PROVIDER_INVALID_RESPONSE",
                message="The AI provider returned no message content.",
                retryable=False,
            )
        return message["content"]
