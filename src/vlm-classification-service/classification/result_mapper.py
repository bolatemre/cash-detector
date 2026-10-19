import json
import logging
import re
from typing import Any

from common.kafka_messages import VlmStageResult
from config.mapping import MappingSettings

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class VlmInvalidJsonError(ValueError):
    """VLM returned text that could not be parsed as a JSON object."""

    retryable = False


def parse_vlm_output(text: str) -> dict[str, Any]:
    """Extract a JSON object from model output, including markdown fences."""
    preview = (text or "")[:500]
    if not text or not text.strip():
        raise VlmInvalidJsonError("VLM output is empty")

    candidates = [text.strip()]
    fenced = _JSON_FENCE_RE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.insert(0, text[start : end + 1])

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise VlmInvalidJsonError(f"VLM output is not valid JSON: {preview}")


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "1"):
            return True
        if lowered in ("false", "no", "0"):
            return False
    return None


class ResultMapper:
    """Map raw VLM text to a typed stage result."""

    def __init__(self, settings: MappingSettings):
        self._settings = settings

    def map(self, raw_text: str) -> VlmStageResult:
        parsed = parse_vlm_output(raw_text)

        suspicious = _as_bool(parsed.get("suspicious_action_detected"))
        description = str(parsed.get("description") or "")

        if suspicious is True:
            return VlmStageResult(
                event_type=self._settings.suspicious_event_type,
                description=description,
            )
        if suspicious is False:
            return VlmStageResult(
                event_type=self._settings.normal_event_type,
                description=description,
            )

        logger.warning("VLM JSON missing suspicious_action_detected: %s", parsed)
        return VlmStageResult(
            event_type=self._settings.unknown_event_type,
            description=description,
        )
