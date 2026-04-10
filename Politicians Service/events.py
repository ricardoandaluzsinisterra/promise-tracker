import json
from datetime import datetime, timezone

PROMISE_CREATED = "PromiseCreated"
PROMISE_RETRACTED = "PromiseRetracted"

POLITICIAN_TAGGED = "PoliticianTagged"
POLITICIAN_TAGGING_FAILED = "PoliticianTaggingFailed"
PROMISE_UNTAGGED = "PromiseUntagged"

KAFKA_TOPIC = "politician.events"
CONSUMED_TOPIC = "promise.events"


def _utc_timestamp() -> str:
	return datetime.now(timezone.utc).isoformat()


def build_politician_tagged_payload(promise_id: str, politician_id: str) -> str:
	return json.dumps(
		{
			"event_type": POLITICIAN_TAGGED,
			"saga_id": promise_id,
			"promise_id": promise_id,
			"politician_id": politician_id,
			"timestamp": _utc_timestamp(),
		}
	)


def build_politician_tagging_failed_payload(promise_id: str, politician_id: str) -> str:
	return json.dumps(
		{
			"event_type": POLITICIAN_TAGGING_FAILED,
			"saga_id": promise_id,
			"promise_id": promise_id,
			"politician_id": politician_id,
			"timestamp": _utc_timestamp(),
		}
	)


def build_promise_untagged_payload(promise_id: str, politician_id: str) -> str:
	return json.dumps(
		{
			"event_type": PROMISE_UNTAGGED,
			"saga_id": promise_id,
			"promise_id": promise_id,
			"politician_id": politician_id,
			"timestamp": _utc_timestamp(),
		}
	)
