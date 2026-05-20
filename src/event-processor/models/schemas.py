"""Application schemas; Kafka security-event payload is shared with ``common.kafka_messages``."""

from common.kafka_messages import SecurityEventMessage

# Backward-compatible name used across event-processor
EventMessage = SecurityEventMessage
