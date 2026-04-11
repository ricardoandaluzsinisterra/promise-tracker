'''
AI Prompt:
I need Event types to be uniform across all services and files, so instead of hardcoding them 
I want them to be centralized in a file.
'''

import json
from datetime import datetime, timezone

# These string constants travel on Kafka topics.
# Every service in the system shares knowledge of these names, so they should be reused correctly
PROMISE_CREATED    = "PromiseCreated"
PROMISE_UPDATED    = "PromiseUpdated"
PROMISE_RETRACTED  = "PromiseRetracted"
PROMISE_FAILED     = "PromiseFailed"     # emitted when compensation fires

# Consumed from downstream services
POLITICIAN_TAGGED        = "PoliticianTagged"
POLITICIAN_TAGGING_FAILED = "PoliticianTaggingFailed"
TRACKING_ARCHIVED        = "TrackingArchived"
TRACKING_ARCHIVE_FAILED  = "TrackingArchiveFailed"
TRACKING_CREATION_FAILED = "TrackingCreationFailed"

KAFKA_TOPIC = "promise.events"

def build_promise_created_payload(promise_id: str, title: str, politician_id: str) -> str:
    return json.dumps({
        "event_type": PROMISE_CREATED,
        "saga_id": promise_id,   # promise_id IS the saga correlation ID
        "promise_id": promise_id,
        "title": title,
        "politician_id": politician_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

def build_promise_retracted_payload(promise_id: str) -> str:
    return json.dumps({
        "event_type": PROMISE_RETRACTED,
        "saga_id": promise_id,
        "promise_id": promise_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })