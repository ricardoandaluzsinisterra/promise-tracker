import json
from datetime import datetime, timezone

TRACKING_CREATED = "TrackingCreated"
TRACKING_ARCHIVED = "TrackingArchived"

SOURCE_LINKED = "SourceLinked"
SOURCES_CLEARED = "SourcesCleared"

KAFKA_TOPIC = "source.events"
CONSUMED_TOPIC = "tracking.events"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_source_linked_payload(promise_id: str, source_id: str) -> str:
    return json.dumps(
        {
            "event_type": SOURCE_LINKED,
            "saga_id": promise_id,
            "promise_id": promise_id,
            "source_id": source_id,
            "timestamp": _utc_timestamp(),
        }
    )


def build_sources_cleared_payload(promise_id: str) -> str:
    return json.dumps(
        {
            "event_type": SOURCES_CLEARED,
            "saga_id": promise_id,
            "promise_id": promise_id,
            "timestamp": _utc_timestamp(),
        }
    )