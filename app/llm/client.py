"""LLM provider abstraction layer with Gemini, Groq, OpenAI, and Fake clients."""

from abc import ABC, abstractmethod
import asyncio
import json
import logging
from typing import Any, Optional
import httpx

from app.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    """Base exception for LLM provider errors."""

    pass


class LLMRateLimitError(LLMClientError):
    """Raised when provider returns HTTP 429 rate limit."""

    pass


class LLMAuthError(LLMClientError):
    """Raised when provider rejects authentication credentials (HTTP 401/403)."""

    pass


class LLMClient(ABC):
    """Abstract provider interface for LLM text inference."""

    @abstractmethod
    async def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        """Generate text completion from system and user prompts."""
        pass


class FakeLLMClient(LLMClient):
    """Deterministic, configurable fake LLM client for unit and integration testing."""

    def __init__(self, responses: Optional[list[str]] = None) -> None:
        self.responses = list(responses) if responses else []
        self.call_history: list[dict[str, str]] = []

    def set_responses(self, responses: list[str]) -> None:
        """Set a queue of mocked response strings."""
        self.responses = list(responses)

    async def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        self.call_history.append({"system": system_prompt, "user": user_prompt})

        if self.responses:
            return self.responses.pop(0)

        # Smart fallback heuristic for default testing
        if "NO EVIDENCE SIGNALS AVAILABLE" in user_prompt or "error" in user_prompt.lower():
            return json.dumps({
                "fit": "UNCERTAIN",
                "confidence": 0.2,
                "confidence_rationale": "No factual evidence signals were available for analysis.",
                "reasoning": ["No verified signals exist in PostgreSQL database for this company."],
                "follow_up_question": "Can you provide a functional website URL?",
                "key_signals_used": [],
            })

        if "disqualif" in user_prompt.lower() or "fashion" in user_prompt.lower() or "clothing" in user_prompt.lower():
            return json.dumps({
                "fit": "NO",
                "confidence": 0.9,
                "confidence_rationale": "Company explicitly falls under disqualifying criteria.",
                "reasoning": [
                    "Website copy indicates consumer retail and eCommerce operations.",
                    "No B2B enterprise software or robotics technology detected in signals."
                ],
                "follow_up_question": None,
                "key_signals_used": ["HTTP_WEBSITE"],
            })

        return json.dumps({
            "fit": "YES",
            "confidence": 0.88,
            "confidence_rationale": "Strong positive concordance across HTTP and browser careers signals.",
            "reasoning": [
                "HTTP signal demonstrates an autonomous robotics fleet platform targeting enterprise warehouse hubs.",
                "Browser careers signal confirms 3 active engineering roles (Python, C++, ROS2)."
            ],
            "follow_up_question": None,
            "key_signals_used": ["HTTP_WEBSITE", "BROWSER_CAREERS"],
        })


class GeminiLLMClient(LLMClient):
    """Google Gemini provider client via direct REST API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.1-flash-lite",
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        clean_model = model.replace("models/", "").strip()
        self.base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent"

    async def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
            },
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

        return await _execute_with_retry(
            url=self.base_url,
            headers=headers,
            params=None,
            json_body=payload,
            timeout=self.timeout_seconds,
            max_retries=self.max_retries,
            response_extractor=lambda data: data["candidates"][0]["content"]["parts"][0]["text"],
            provider_name="Gemini",
        )


class GroqLLMClient(LLMClient):
    """Groq Cloud provider client using OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"

    async def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        return await _execute_with_retry(
            url=self.base_url,
            headers=headers,
            params=None,
            json_body=payload,
            timeout=self.timeout_seconds,
            max_retries=self.max_retries,
            response_extractor=lambda data: data["choices"][0]["message"]["content"],
            provider_name="Groq",
        )


class OpenAILLMClient(LLMClient):
    """OpenAI provider client using Chat Completions API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.base_url = "https://api.openai.com/v1/chat/completions"

    async def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        return await _execute_with_retry(
            url=self.base_url,
            headers=headers,
            params=None,
            json_body=payload,
            timeout=self.timeout_seconds,
            max_retries=self.max_retries,
            response_extractor=lambda data: data["choices"][0]["message"]["content"],
            provider_name="OpenAI",
        )


async def _execute_with_retry(
    url: str,
    headers: dict[str, str],
    params: Optional[dict[str, str]],
    json_body: dict[str, Any],
    timeout: float,
    max_retries: int,
    response_extractor: Any,
    provider_name: str,
) -> str:
    """Execute HTTP POST request with structured error handling and bounded backoff."""
    attempt = 0
    base_delay = 1.0

    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            try:
                response = await client.post(url, headers=headers, params=params, json=json_body)

                if response.status_code >= 400:
                    error_details: list[str] = []
                    try:
                        err_json = response.json()
                        err_obj = err_json.get("error", {})
                        if isinstance(err_obj, dict):
                            if "code" in err_obj:
                                error_details.append(f"code: {err_obj['code']}")
                            if "status" in err_obj:
                                error_details.append(f"status: {err_obj['status']}")
                            if "message" in err_obj:
                                error_details.append(f"message: {err_obj['message']}")
                        elif isinstance(err_obj, str):
                            error_details.append(f"message: {err_obj}")
                    except Exception:
                        error_details.append(response.text[:200].strip())

                    details_str = " | ".join(error_details) if error_details else "No error details returned"
                    clean_err_msg = f"{provider_name} request failed (HTTP {response.status_code}): {details_str}"

                    if response.status_code in (401, 403):
                        raise LLMAuthError(f"{provider_name} authentication failed (HTTP {response.status_code}): {details_str}")

                    if response.status_code == 429:
                        attempt += 1
                        if attempt > max_retries:
                            raise LLMRateLimitError(f"{provider_name} rate limited after {max_retries} retries: {details_str}")
                        delay = base_delay * (2 ** (attempt - 1))
                        logger.warning(
                            "%s 429 rate limit. Backing off for %.1fs (attempt %d/%d)",
                            provider_name,
                            delay,
                            attempt,
                            max_retries,
                        )
                        await asyncio.sleep(delay)
                        continue

                    if response.status_code in (500, 502, 503, 504):
                        attempt += 1
                        if attempt > max_retries:
                            raise LLMClientError(f"{provider_name} server error {response.status_code} after {max_retries} retries: {details_str}")
                        delay = base_delay * (2 ** (attempt - 1))
                        logger.warning(
                            "%s server error %d. Retrying in %.1fs...",
                            provider_name,
                            response.status_code,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue

                    raise LLMClientError(clean_err_msg)

                data = response.json()
                return str(response_extractor(data))

            except (LLMAuthError, LLMRateLimitError, LLMClientError):
                raise
            except httpx.TimeoutException as exc:
                attempt += 1
                if attempt > max_retries:
                    raise LLMClientError(f"{provider_name} timeout after {max_retries} retries.") from exc
                await asyncio.sleep(base_delay)
            except Exception as exc:
                if attempt >= max_retries:
                    raise LLMClientError(f"{provider_name} request failed: {type(exc).__name__}: {exc!s}") from exc
                attempt += 1
                await asyncio.sleep(base_delay)


def get_llm_client(settings: Optional[Settings] = None) -> LLMClient:
    """Factory creating configured LLM client instance."""
    cfg = settings or get_settings()
    provider = cfg.llm_provider.lower()

    if provider == "fake":
        return FakeLLMClient()
    elif provider == "groq":
        if not cfg.groq_api_key:
            logger.warning("GROQ_API_KEY is not set. Falling back to FakeLLMClient.")
            return FakeLLMClient()
        return GroqLLMClient(
            api_key=cfg.groq_api_key,
            model=cfg.llm_model if "llama" in cfg.llm_model else "llama-3.3-70b-versatile",
            timeout_seconds=cfg.llm_timeout_seconds,
            max_retries=cfg.llm_max_retries,
        )
    elif provider == "openai":
        if not cfg.openai_api_key:
            logger.warning("OPENAI_API_KEY is not set. Falling back to FakeLLMClient.")
            return FakeLLMClient()
        return OpenAILLMClient(
            api_key=cfg.openai_api_key,
            model=cfg.llm_model if "gpt" in cfg.llm_model else "gpt-4o-mini",
            timeout_seconds=cfg.llm_timeout_seconds,
            max_retries=cfg.llm_max_retries,
        )
    else:  # default to gemini
        if not cfg.gemini_api_key:
            logger.warning("GEMINI_API_KEY is not set. Falling back to FakeLLMClient.")
            return FakeLLMClient()
        return GeminiLLMClient(
            api_key=cfg.gemini_api_key,
            model=cfg.llm_model,
            timeout_seconds=cfg.llm_timeout_seconds,
            max_retries=cfg.llm_max_retries,
        )
