import logging
from typing import Any

from minio import Minio
from minio.commonconfig import Tags
from minio.error import S3Error

from common.kafka_messages import StageName
from pipeline_settings import settings

logger = logging.getLogger(__name__)


class MinioService:
    """MinIO operations for pipeline orchestration (object tagging)."""

    def __init__(self) -> None:
        endpoint = settings.minio_endpoint.replace("http://", "").replace("https://", "")
        self.client = Minio(
            endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self.default_bucket = settings.minio_bucket
        logger.info("MinIO service initialized: %s/%s", endpoint, self.default_bucket)

    def tag_video_with_stage_result(
        self,
        video_path: str,
        stage_name: StageName,
        stage_result: dict[str, Any],
        bucket_name: str | None = None,
    ) -> bool:
        event_type = stage_result.get("event_type")
        if not event_type:
            logger.warning(
                "%s result missing event_type; skip tagging %s",
                stage_name,
                video_path,
            )
            return False

        bucket = bucket_name or self.default_bucket
        tags = self._stage_tags(stage_name, stage_result)
        logger.info(
            "Tagging %s/%s stage=%s event_type=%s tags=%s",
            bucket,
            video_path,
            stage_name,
            event_type,
            tags,
        )
        return self._merge_and_set_tags(bucket, video_path, tags, stage_name)

    def _merge_and_set_tags(
        self,
        bucket: str,
        video_path: str,
        tags: dict[str, str],
        stage_name: StageName,
    ) -> bool:
        try:
            existing = self._load_existing_tags(bucket, video_path)
            merged = Tags.new_object_tags()
            for key, value in existing.items():
                merged[key] = value
            for key, value in tags.items():
                merged[key] = value

            logger.debug(
                "Setting object tags on %s/%s (existing=%s, new=%s, merged=%s)",
                bucket,
                video_path,
                dict(existing),
                tags,
                dict(merged),
            )
            self.client.set_object_tags(bucket, video_path, merged)
            logger.info(
                "Tagged video %s/%s stage=%s merged_tags=%s",
                bucket,
                video_path,
                stage_name,
                dict(merged),
            )
            return True
        except S3Error as e:
            logger.error("MinIO error tagging %s/%s stage=%s: %s", bucket, video_path, stage_name, e)
            return False
        except Exception as e:
            logger.error(
                "Error tagging %s/%s stage=%s: %s",
                bucket,
                video_path,
                stage_name,
                e,
                exc_info=True,
            )
            return False

    def _load_existing_tags(self, bucket: str, video_path: str) -> Tags:
        try:
            existing = self.client.get_object_tags(bucket, video_path)
        except S3Error as e:
            logger.debug("No existing tags on %s/%s (%s); starting fresh", bucket, video_path, e)
            return Tags.new_object_tags()

        if existing is None:
            logger.debug("get_object_tags returned None for %s/%s; starting fresh", bucket, video_path)
            return Tags.new_object_tags()

        if not isinstance(existing, Tags):
            logger.debug(
                "Unexpected tags type %s for %s/%s; copying into object tags",
                type(existing).__name__,
                bucket,
                video_path,
            )
            merged = Tags.new_object_tags()
            for key, value in dict(existing).items():
                merged[key] = value
            return merged

        logger.debug("Loaded existing tags on %s/%s: %s", bucket, video_path, dict(existing))
        return existing

    @staticmethod
    def _stage_tags(stage_name: StageName, stage_result: dict[str, Any]) -> dict[str, str]:
        if stage_name == StageName.CLASSIFICATION:
            return MinioService._classification_tags(stage_result)
        if stage_name == StageName.VLM:
            return MinioService._vlm_tags(stage_result)
        return MinioService._tracking_tags(stage_result)

    @staticmethod
    def _classification_tags(classification_result: dict[str, Any]) -> dict[str, str]:
        tags = {StageName.CLASSIFICATION: str(classification_result["event_type"])}
        confidence = classification_result.get("confidence")
        if confidence is not None:
            tags["classification_confidence"] = str(confidence)
        predicted_class = classification_result.get("predicted_class")
        if predicted_class is not None:
            tags["classification_predicted_class"] = str(predicted_class)
        return tags

    @staticmethod
    def _tracking_tags(tracking_result: dict[str, Any]) -> dict[str, str]:
        tags = {StageName.TRACKING: str(tracking_result["event_type"])}
        final_status = tracking_result.get("final_status")
        if final_status is not None:
            tags["tracking_final_status"] = str(final_status)
        alerts = tracking_result.get("alerts")
        if alerts is not None:
            tags["tracking_alerts"] = str(alerts)
        oks = tracking_result.get("oks")
        if oks is not None:
            tags["tracking_oks"] = str(oks)
        return tags

    @staticmethod
    def _vlm_tags(vlm_result: dict[str, Any]) -> dict[str, str]:
        return {StageName.VLM: str(vlm_result["event_type"])}
