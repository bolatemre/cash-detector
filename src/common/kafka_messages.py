"""Pydantic models for Kafka payloads shared across pipeline, workers, and event-processor."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Optional, Self

from pydantic import BaseModel, ConfigDict, Field


class StageName(StrEnum):
    CLASSIFICATION = "classification"
    TRACKING = "tracking"
    VLM = "vlm"


StageResultPayload = dict[str, Any]


class SecurityEventMessage(BaseModel):
    """Published to the security-events topic (consumed by event-processor as EventMessage)."""

    model_config = ConfigDict(extra="forbid")

    event_type: str
    camera_id: str
    detected_at: datetime
    video_url: Optional[str] = None


class VideoUploadedMessage(BaseModel):
    """Consumed from uploaded-videos (produced by celery-worker)."""

    model_config = ConfigDict(extra="ignore")

    camera_id: str
    video_path: str
    bucket_name: Optional[str] = None
    event_type: Literal["video_uploaded"] = "video_uploaded"
    recording_started_at: Optional[str] = None


class ClassificationStageResult(BaseModel):
    """Output of the classification stage."""

    model_config = ConfigDict(extra="allow")

    event_type: str
    confidence: float = 0.0
    predicted_class: int = -1
    features_collected: int = 0


class TrackingStageResult(BaseModel):
    """Output of the tracking stage (see script_tracking_no_vis.object_by_zones)."""

    model_config = ConfigDict(extra="allow")

    event_type: str
    final_status: str
    alerts: int = 0
    oks: int = 0


class VlmStageResult(BaseModel):
    """Output of the VLM classification stage."""

    model_config = ConfigDict(extra="allow")

    event_type: str
    description: str = ""


class PipelineStageEnvelope(BaseModel):
    """
    Flat JSON message for pipeline orchestration on Kafka.

    Two shapes on the wire:

    1. **Stage request** (pipeline -> worker): video fields + progress; `stage_name` /
       `stage_result` are omitted (or cleared when forwarding to the next stage).
    2. **Stage completion** (worker -> pipeline): same fields plus `stage_name` and
       `stage_result` for the stage that just finished.

    `stage_results` holds outputs from earlier stages only; the latest completion lives
    in `stage_name` / `stage_result` until the pipeline merges it.
    """

    model_config = ConfigDict(extra="allow")

    # --- Correlation ---
    correlation_id: str = Field(description="Unique id for one video across all stages.")

    # --- Video (input for stage workers) ---
    camera_id: Optional[str] = Field(default=None, description="Source camera identifier.")
    video_path: Optional[str] = Field(default=None, description="Object key inside bucket_name.")
    bucket_name: Optional[str] = Field(default=None, description="MinIO bucket; service default if omitted.")
    recording_started_at: str = Field(description="ISO-8601 timestamp when recording started.")

    # --- Pipeline progress ---
    stage_order: list[StageName] = Field(
        description="Ordered stage names, e.g. ['classification', 'tracking']."
    )
    current_stage_index: int = Field(
        default=0,
        ge=0,
        description="Index into stage_order for the stage being executed or just completed.",
    )
    stage_results: dict[StageName, StageResultPayload] = Field(
        default_factory=dict,
        description="Outputs from finished stages (excludes the in-flight completion).",
    )

    # --- Worker completion (set when publishing to stage-results) ---
    stage_name: Optional[StageName] = Field(
        default=None,
        description="Stage that produced stage_result.",
    )
    stage_result: Optional[StageResultPayload] = Field(
        default=None,
        description="Raw output from stage_name (must include event_type).",
    )

    @classmethod
    def start(
        cls,
        *,
        correlation_id: str,
        camera_id: str,
        video_path: str,
        bucket_name: Optional[str],
        recording_started_at: str,
        stage_order: list[StageName],
    ) -> Self:
        """Create an envelope for the first stage (no completion fields)."""
        return cls(
            correlation_id=correlation_id,
            camera_id=camera_id,
            video_path=video_path,
            bucket_name=bucket_name,
            recording_started_at=recording_started_at,
            stage_order=stage_order,
            current_stage_index=0,
            stage_results={},
        )

    @property
    def current_stage(self) -> StageName:
        return self.stage_order[self.current_stage_index]

    def has_next_stage(self) -> bool:
        return self.current_stage_index + 1 < len(self.stage_order)

    def next_stage(self) -> StageName | None:
        if not self.has_next_stage():
            return None
        return self.stage_order[self.current_stage_index + 1]

    def require_completion(self) -> tuple[StageName, StageResultPayload]:
        if self.stage_name is None:
            raise ValueError("stage_name is required on a completion message")
        if self.stage_result is None:
            raise ValueError("stage_result is required on a completion message")
        event_type = self.stage_result.get("event_type")
        if not event_type:
            raise ValueError("stage_result must include event_type")
        return self.stage_name, self.stage_result

    def completion_event_type(self) -> str:
        _, result = self.require_completion()
        return result["event_type"]

    def merged_stage_results(self) -> dict[StageName, StageResultPayload]:
        stage_name, stage_result = self.require_completion()
        return {**self.stage_results, stage_name: stage_result}

    def with_completion(self, stage_name: StageName, stage_result: StageResultPayload) -> Self:
        """Attach a worker completion before publishing to stage-results."""
        return self.model_copy(update={"stage_name": stage_name, "stage_result": stage_result})

    def for_next_stage(self, stage_results: dict[StageName, StageResultPayload]) -> Self:
        """Advance to the next stage and clear completion fields for the outbound request."""
        return self.model_copy(
            update={
                "current_stage_index": self.current_stage_index + 1,
                "stage_results": stage_results,
                "stage_name": None,
                "stage_result": None,
            }
        )
