import json
from datetime import datetime, timezone

POLITICIAN_TAGGED = "PoliticianTagged"
PROMISE_RETRACTED = "PromiseRetracted"

TRACKING_CREATED = "TrackingCreated"
TRACKING_CREATION_FAILED = "TrackingCreationFailed"
TRACKING_UPDATED = "TrackingUpdated"
TRACKING_ARCHIVED = "TrackingArchived"
TRACKING_ARCHIVE_FAILED = "TrackingArchiveFailed"

KAFKA_TOPIC = "tracking.events"
CONSUMED_TOPIC = "politician.events"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_tracking_created_payload(promise_id: str, politician_id: str, progress: int) -> str:
    return json.dumps(
        {
            "event_type": TRACKING_CREATED,
            "saga_id": promise_id,
            "promise_id": promise_id,
            "politician_id": politician_id,
            "progress": progress,
            "timestamp": _utc_timestamp(),
        }
    )


def build_tracking_creation_failed_payload(promise_id: str, politician_id: str) -> str:
    return json.dumps(
        {
            "event_type": TRACKING_CREATION_FAILED,
            "saga_id": promise_id,
            "promise_id": promise_id,
            "politician_id": politician_id,
            "timestamp": _utc_timestamp(),
        }
    )


def build_tracking_updated_payload(promise_id: str, politician_id: str, progress: int) -> str:
    return json.dumps(
        {
            "event_type": TRACKING_UPDATED,
            "saga_id": promise_id,
            "promise_id": promise_id,
            "politician_id": politician_id,
            "progress": progress,
            "timestamp": _utc_timestamp(),
        }
    )


def build_tracking_archived_payload(promise_id: str, politician_id: str, progress: int) -> str:
    return json.dumps(
        {
            "event_type": TRACKING_ARCHIVED,
            "saga_id": promise_id,
            "promise_id": promise_id,
            "politician_id": politician_id,
            "progress": progress,
            "timestamp": _utc_timestamp(),
        }
    )


def build_tracking_archive_failed_payload(promise_id: str, politician_id: str) -> str:
    return json.dumps(
        {
            "event_type": TRACKING_ARCHIVE_FAILED,
            "saga_id": promise_id,
            "promise_id": promise_id,
            "politician_id": politician_id,
            "timestamp": _utc_timestamp(),
        }
    )