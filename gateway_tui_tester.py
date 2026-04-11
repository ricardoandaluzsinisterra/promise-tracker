#!/usr/bin/env python3
"""
AI Prompt: 
I need you to create a simple python file that will allow me to test the all of 
the endpoints using the api gateway, it can have a little TUI that lets you select what you want to test

Simple interactive tester for API Gateway endpoints.

The TUI is intentionally beginner-friendly:
- guided prompts for each body field
- path parameters with defaults
- no raw JSON editing required
- no query-string input in normal flow

Usage:
  python gateway_tui_tester.py
  python gateway_tui_tester.py --all
    python gateway_tui_tester.py --saga-rollback-test
    python gateway_tui_tester.py --acceptance-suite
  python gateway_tui_tester.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from urllib import error, request


@dataclass(frozen=True)
class BodyField:
    key: str
    label: str
    kind: str = "str"  # supported: str, int
    required: bool = True
    default: str | int | None = None
    default_from_value: str | None = None


@dataclass(frozen=True)
class Endpoint:
    name: str
    method: str
    path_template: str
    body_fields: tuple[BodyField, ...] = ()
    sample_body: dict[str, Any] | None = None


@dataclass
class PollResult:
    matched: bool
    attempts: int
    status: int | None
    headers: dict[str, str]
    payload: Any | None
    text: str


@dataclass
class EvidenceStep:
    order: int
    title: str
    method: str
    path: str
    url: str
    expected: str
    passed: bool
    status: int | None
    request_body: Any | None
    response_body: Any | None
    response_text: str
    notes: str
    timestamp_utc: str


ENDPOINTS: list[Endpoint] = [
    Endpoint("Health", "GET", "/health"),
    Endpoint(
        "Create promise",
        "POST",
        "/promises",
        body_fields=(
            BodyField("title", "Title", default="Build 100 schools"),
            BodyField("description", "Description", required=False, default=""),
            BodyField("politician_id", "Politician ID", default_from_value="politician_id"),
        ),
        sample_body={
            "title": "Build 100 schools",
            "description": "National education plan",
            "politician_id": "pol-001",
        },
    ),
    Endpoint("Get promise", "GET", "/promises/{promise_id}"),
    Endpoint(
        "Patch promise",
        "PATCH",
        "/promises/{promise_id}",
        body_fields=(
            BodyField("title", "Title", required=False, default=""),
            BodyField("description", "Description", required=False, default=""),
        ),
        sample_body={"title": "Updated promise title"},
    ),
    Endpoint(
        "Retract promise status",
        "PATCH",
        "/promises/{promise_id}/status",
        body_fields=(BodyField("status", "Status", default="retracted"),),
        sample_body={"status": "retracted"},
    ),
    Endpoint(
        "Create politician",
        "POST",
        "/politicians",
        body_fields=(
            BodyField("name", "Name", default="Jane Doe"),
            BodyField("role", "Role", default="Senator"),
        ),
        sample_body={"name": "Jane Doe", "role": "Senator"},
    ),
    Endpoint("Get politician", "GET", "/politicians/{politician_id}"),
    Endpoint("Get tracking", "GET", "/tracking/{promise_id}"),
    Endpoint(
        "Patch tracking",
        "PATCH",
        "/tracking/{promise_id}",
        body_fields=(BodyField("progress", "Progress", kind="int", default=50),),
        sample_body={"progress": 50},
    ),
    Endpoint(
        "Create source",
        "POST",
        "/sources",
        body_fields=(
            BodyField("name", "Source name", default="Official Report"),
            BodyField("url", "Source URL", default="https://example.com/report"),
        ),
        sample_body={"name": "Official Report", "url": "https://example.com/report"},
    ),
    Endpoint(
        "Link source",
        "POST",
        "/sources/link",
        body_fields=(
            BodyField("promise_id", "Promise ID", default_from_value="promise_id"),
            BodyField("source_id", "Source ID", default_from_value="source_id"),
        ),
        sample_body={"promise_id": "1", "source_id": "source-001"},
    ),
    Endpoint("Get sources by promise", "GET", "/sources/promise/{promise_id}"),
    Endpoint("Query promises", "GET", "/query/promises"),
    Endpoint("Query promise by id", "GET", "/query/promises/{promise_id}"),
]

PATH_PARAM_PATTERN = re.compile(r"{([^{}]+)}")


CREATION_LOG_SEQUENCE_TEMPLATE = [
    "Outbox poller in Promises Service: Published PromiseCreated for {promise_id}",
    "Politicians Service consumer: Handled PromiseCreated for {promise_id}",
    "Outbox poller in Politicians Service: Published PoliticianTagged for {promise_id}",
    "Trackers Service consumer: Handled PoliticianTagged for {promise_id}",
    "Outbox poller in Trackers Service: Published TrackingCreated for {promise_id}",
    "Projection Service consumer: updating summary, status = ACTIVE, promise_id={promise_id}",
]

FAILURE_LOG_SEQUENCE_TEMPLATE = [
    "Trackers Service: TrackingCreationFailed emitted for {promise_id}",
    "Politicians Service consumer: Handled TrackingCreationFailed for {promise_id}, compensating",
    "Promises Service consumer: Promise {promise_id} marked FAILED after TrackingCreationFailed",
    "Projection Service consumer: status = FAILED, promise_id={promise_id}",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive API Gateway endpoint tester")
    parser.add_argument(
        "--base-url",
        default=os.getenv("GATEWAY_BASE_URL", "http://localhost:8000"),
        help="Gateway base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("GATEWAY_TEST_TIMEOUT", "10")),
        help="Request timeout in seconds (default: %(default)s)",
    )
    parser.add_argument("--promise-id", default="1", help="Default promise_id for path params")
    parser.add_argument("--politician-id", default="1", help="Default politician_id for path params")
    parser.add_argument("--source-id", default="source-001", help="Default source_id for linking sources")
    parser.add_argument("--all", action="store_true", help="Run all endpoint tests once and exit")
    parser.add_argument(
        "--saga-rollback-test",
        action="store_true",
        help="Run automated saga rollback test that simulates TrackingCreationFailed",
    )
    parser.add_argument(
        "--log-file",
        default="gateway_saga_logs.txt",
        help="Log file path for saga rollback test output (default: %(default)s)",
    )
    parser.add_argument(
        "--acceptance-suite",
        action="store_true",
        help="Run ordered acceptance suite with artifacts and log verification",
    )
    parser.add_argument(
        "--artifacts-dir",
        default="gateway_acceptance_artifacts",
        help="Directory for acceptance artifacts (default: %(default)s)",
    )
    parser.add_argument(
        "--evidence-json",
        default="acceptance_collection.json",
        help="Acceptance evidence JSON filename or absolute path (default: %(default)s)",
    )
    return parser.parse_args()


def build_url(base_url: str, endpoint: Endpoint, values: dict[str, str]) -> str:
    path = endpoint.path_template.format(**values)
    return base_url.rstrip("/") + path


def send_request(
    method: str,
    url: str,
    timeout: float,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "gateway-tui-tester/1.0",
    }

    payload_bytes = None
    if body is not None:
        payload_bytes = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url=url, method=method, data=payload_bytes, headers=headers)

    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers.items()), resp.read()
    except error.HTTPError as exc:
        response_headers = dict(exc.headers.items()) if exc.headers else {}
        return exc.code, response_headers, exc.read()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_directory(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def normalize_status(status_value: Any) -> str:
    if status_value is None:
        return ""
    return str(status_value).strip().upper()


def has_non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def normalize_json(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(k): normalize_json(v) for k, v in value.items()}
        if isinstance(value, list):
            return [normalize_json(v) for v in value]
        return str(value)


def resolve_artifact_path(artifacts_dir: str, path_or_name: str) -> str:
    if os.path.isabs(path_or_name):
        return path_or_name
    return os.path.join(artifacts_dir, path_or_name)


def add_evidence_step(
    collection: list[EvidenceStep],
    title: str,
    method: str,
    path: str,
    url: str,
    expected: str,
    passed: bool,
    status: int | None,
    request_body: Any | None,
    response_body: Any | None,
    response_text: str,
    notes: str,
) -> None:
    order = len(collection) + 1

    step = EvidenceStep(
        order=order,
        title=title,
        method=method,
        path=path,
        url=url,
        expected=expected,
        passed=passed,
        status=status,
        request_body=normalize_json(request_body),
        response_body=normalize_json(response_body),
        response_text=response_text,
        notes=notes,
        timestamp_utc=utc_now_iso(),
    )
    collection.append(step)

    verdict = "PASS" if passed else "FAIL"
    print(f"[{verdict}] Step {order}: {title}")


def request_json(
    method: str,
    base_url: str,
    path: str,
    timeout: float,
    body: dict[str, Any] | None = None,
) -> tuple[int | None, dict[str, str], Any | None, str, str]:
    url = base_url.rstrip("/") + path
    status, headers, payload, text = send_json_request(
        method=method,
        url=url,
        timeout=timeout,
        body=body,
    )
    return status, headers, payload, text, url


def poll_json_endpoint(
    method: str,
    base_url: str,
    path: str,
    timeout: float,
    max_attempts: int,
    interval_seconds: float,
    predicate: Any,
    body: dict[str, Any] | None = None,
) -> PollResult:
    latest_status: int | None = None
    latest_headers: dict[str, str] = {}
    latest_payload: Any | None = None
    latest_text = ""

    for attempt in range(1, max_attempts + 1):
        status, headers, payload, text, _url = request_json(
            method=method,
            base_url=base_url,
            path=path,
            timeout=timeout,
            body=body,
        )
        latest_status = status
        latest_headers = headers
        latest_payload = payload
        latest_text = text

        if predicate(status, payload):
            return PollResult(
                matched=True,
                attempts=attempt,
                status=status,
                headers=headers,
                payload=payload,
                text=text,
            )

        if attempt < max_attempts:
            time.sleep(interval_seconds)

    return PollResult(
        matched=False,
        attempts=max_attempts,
        status=latest_status,
        headers=latest_headers,
        payload=latest_payload,
        text=latest_text,
    )


# AI Prompt :
# Add a option to test rollbacks and failure to write to database on the tracking service and capture all logs going back in the saga.
def send_json_request(
    method: str,
    url: str,
    timeout: float,
    body: dict[str, Any] | None = None,
) -> tuple[int | None, dict[str, str], Any | None, str]:
    try:
        status, headers, raw = send_request(method=method, url=url, timeout=timeout, body=body)
    except error.URLError as exc:
        return None, {}, None, f"Request failed: {exc.reason}"

    parsed: Any | None = None
    decoded = raw.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(decoded)
    except json.JSONDecodeError:
        parsed = None

    pretty = decode_response_body(headers, raw)
    return status, headers, parsed, pretty


def run_command(
    command: list[str],
    timeout: float,
    stdin_text: str | None = None,
) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            command,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return completed.returncode, completed.stdout, completed.stderr
    except FileNotFoundError:
        return 127, "", f"Command not found: {command[0]}"
    except subprocess.TimeoutExpired as exc:
        def _to_text(value: Any) -> str:
            if value is None:
                return ""
            if isinstance(value, str):
                return value
            if isinstance(value, memoryview):
                return value.tobytes().decode("utf-8", errors="replace")
            if isinstance(value, (bytes, bytearray)):
                return bytes(value).decode("utf-8", errors="replace")
            return str(value)

        stdout = _to_text(exc.stdout)
        stderr = _to_text(exc.stderr)
        return 124, stdout, f"{stderr}\nCommand timed out after {timeout} seconds".strip()


def break_trackers_database(timeout: float) -> tuple[bool, str]:
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "postgres-trackers",
        "psql",
        "-U",
        "postgres",
        "-d",
        "trackers_db",
        "-c",
        "DROP TABLE IF EXISTS tracking_records CASCADE;",
    ]
    return_code, stdout, stderr = run_command(command=command, timeout=timeout)
    if return_code != 0:
        return False, stderr.strip() or "Failed to drop tracking_records table"

    output = stdout.strip() or "tracking_records table dropped"
    return True, output


def restore_trackers_database(timeout: float) -> tuple[bool, str]:
    command = ["docker", "compose", "restart", "trackers-service"]
    return_code, stdout, stderr = run_command(command=command, timeout=timeout)
    if return_code != 0:
        return False, stderr.strip() or "Failed to restart trackers-service"

    # The service runs create_all on startup, so restart restores missing tables.
    time.sleep(6)
    output = stdout.strip() or "trackers-service restarted"
    return True, output


def publish_tracking_creation_failed_event(
    promise_id: str,
    politician_id: str,
    timeout: float,
) -> tuple[bool, str]:
    payload = {
        "event_type": "TrackingCreationFailed",
        "saga_id": promise_id,
        "promise_id": promise_id,
        "politician_id": politician_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "kafka",
        "kafka-console-producer",
        "--bootstrap-server",
        "kafka:9092",
        "--topic",
        "tracking.events",
    ]
    return_code, _stdout, stderr = run_command(
        command=command,
        timeout=timeout,
        stdin_text=json.dumps(payload) + "\n",
    )
    if return_code != 0:
        return False, stderr.strip() or "Failed to publish TrackingCreationFailed"
    return True, "TrackingCreationFailed published to tracking.events"


def fetch_compose_logs(timeout: float, tail: int = 1200) -> tuple[bool, str, str]:
    command = [
        "docker",
        "compose",
        "logs",
        "--no-color",
        "--tail",
        str(tail),
        "promises-service",
        "politicians-service",
        "trackers-service",
        "sources-service",
        "projection-service",
        "kafka",
    ]
    return_code, stdout, stderr = run_command(command=command, timeout=timeout)
    if return_code != 0:
        return False, stderr.strip() or "Failed to collect docker compose logs", ""
    return True, "docker compose logs captured", stdout


def capture_filtered_logs(
    file_path: str,
    timeout: float,
    keywords: list[str],
    tail: int = 1200,
) -> tuple[bool, str, list[str]]:
    logs_ok, logs_message, raw_logs = fetch_compose_logs(timeout=timeout, tail=tail)
    if not logs_ok:
        return False, logs_message, []

    filtered_lines = [
        line for line in raw_logs.splitlines() if any(keyword in line for keyword in keywords)
    ]

    with open(file_path, "w", encoding="utf-8") as log_file:
        log_file.write("=== FILTERED SAGA LINES ===\n")
        if filtered_lines:
            log_file.write("\n".join(filtered_lines))
            log_file.write("\n")
        else:
            log_file.write("<no filtered lines matched keywords>\n")
        log_file.write("\n=== RAW docker compose logs ===\n")
        log_file.write(raw_logs)

    return True, f"Logs saved to {file_path}", filtered_lines


def verify_log_sequence(
    lines: list[str],
    expected_sequence: list[str],
) -> tuple[bool, list[str], list[str]]:
    missing: list[str] = []
    matched_lines: list[str] = []
    scan_start = 0

    for expected_line in expected_sequence:
        found = False
        for idx in range(scan_start, len(lines)):
            if expected_line in lines[idx]:
                matched_lines.append(lines[idx])
                scan_start = idx + 1
                found = True
                break
        if not found:
            missing.append(expected_line)

    return len(missing) == 0, missing, matched_lines


def write_grep_log_dump(
    source_log_file: str,
    output_file: str,
    expected_lines: list[str],
    missing_lines: list[str],
    timeout: float,
) -> tuple[bool, str]:
    pattern_parts = [re.escape(line) for line in expected_lines]
    grep_pattern = "|".join(pattern_parts)

    if not grep_pattern:
        with open(output_file, "w", encoding="utf-8") as dump_file:
            dump_file.write("No expected lines provided.\n")
        return True, f"Grep log dump saved to {output_file}"

    return_code, stdout, stderr = run_command(
        command=[
            "grep",
            "-nE",
            "--color=always",
            grep_pattern,
            source_log_file,
        ],
        timeout=timeout,
    )

    if return_code not in (0, 1):
        return False, stderr.strip() or f"Failed to generate grep dump for {output_file}"

    with open(output_file, "w", encoding="utf-8") as dump_file:
        dump_file.write("=== EXPECTED LINES ===\n")
        for line in expected_lines:
            dump_file.write(f"{line}\n")

        dump_file.write("\n=== GREP OUTPUT (colorized ANSI) ===\n")
        if stdout:
            dump_file.write(stdout)
            if not stdout.endswith("\n"):
                dump_file.write("\n")
        else:
            dump_file.write("<no grep matches>\n")

        dump_file.write("\n=== MISSING LINES FROM ORDERED CHECK ===\n")
        if missing_lines:
            for line in missing_lines:
                dump_file.write(f"{line}\n")
        else:
            dump_file.write("<none>\n")

    return True, f"Grep log dump saved to {output_file}"


def capture_saga_logs(promise_id: str, file_path: str, timeout: float) -> tuple[bool, str]:
    keywords = [
        promise_id,
        "PromiseCreated",
        "PoliticianTagged",
        "TrackingCreated",
        "TrackingCreationFailed",
        "PromiseUntagged",
        "PoliticianUntaggingFailed",
        "PromiseRetracted",
        "TrackingArchiveFailed",
        "SourcesClearFailed",
    ]
    ok, message, _filtered_lines = capture_filtered_logs(
        file_path=file_path,
        timeout=timeout,
        keywords=keywords,
        tail=1200,
    )
    return ok, message


def get_header(headers: dict[str, str], name: str, default: str = "") -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return default


def decode_response_body(headers: dict[str, str], body: bytes) -> str:
    content_type = get_header(headers, "Content-Type", "")
    text = body.decode("utf-8", errors="replace")

    if "application/json" in content_type.lower():
        try:
            parsed = json.loads(text)
            return json.dumps(parsed, indent=2, ensure_ascii=True)
        except json.JSONDecodeError:
            return text

    return text


def prompt_text(label: str, required: bool, default: str | int | None = None) -> str:
    prompt = f"{label}"
    if default is not None:
        prompt += f" [{default}]"
    prompt += ": "

    while True:
        value = input(prompt).strip()
        if value:
            return value
        if default is not None:
            return str(default)
        if not required:
            return ""
        print("This field is required.")


def prompt_int(label: str, required: bool, default: int | None = None) -> int | None:
    while True:
        raw = prompt_text(label=label, required=required, default=default)
        if not raw and not required:
            return None
        try:
            return int(raw)
        except ValueError:
            print("Please enter a whole number.")


def path_param_names(endpoint: Endpoint) -> list[str]:
    return PATH_PARAM_PATTERN.findall(endpoint.path_template)


def resolve_path_values(endpoint: Endpoint, values: dict[str, str], interactive: bool) -> dict[str, str]:
    resolved = dict(values)

    for param_name in path_param_names(endpoint):
        default = resolved.get(param_name, "1")
        if interactive:
            pretty_name = param_name.replace("_", " ").title()
            chosen = prompt_text(pretty_name, required=True, default=default)
            resolved[param_name] = chosen
            # Keep these as new defaults for later menu actions.
            values[param_name] = chosen
        else:
            resolved[param_name] = default

    return resolved


def build_default_body(endpoint: Endpoint, values: dict[str, str]) -> dict[str, Any] | None:
    if not endpoint.body_fields and endpoint.sample_body is None:
        return None

    if endpoint.sample_body is not None:
        body: dict[str, Any] = dict(endpoint.sample_body)
    else:
        body = {}

    for field in endpoint.body_fields:
        if field.default_from_value:
            body[field.key] = values.get(field.default_from_value, "")

    return body


def collect_body(endpoint: Endpoint, values: dict[str, str], interactive: bool) -> dict[str, Any] | None:
    if not endpoint.body_fields and endpoint.sample_body is None:
        return None

    if not interactive:
        return build_default_body(endpoint, values)

    print("Fill in request fields (press Enter to accept defaults).")
    body: dict[str, Any] = {}

    for field in endpoint.body_fields:
        default = field.default
        if field.default_from_value:
            default = values.get(field.default_from_value, default)

        if field.kind == "int":
            int_default = int(default) if isinstance(default, int) else None
            entered = prompt_int(label=field.label, required=field.required, default=int_default)
            if entered is None and not field.required:
                continue
            if entered is not None:
                body[field.key] = entered
            continue

        entered_text = prompt_text(label=field.label, required=field.required, default=default)
        if not entered_text and not field.required:
            continue
        body[field.key] = entered_text

    return body


def export_acceptance_collection(
    file_path: str,
    base_url: str,
    duration_seconds: float,
    setup_data: dict[str, Any],
    steps: list[EvidenceStep],
    log_checks: dict[str, Any],
) -> tuple[bool, str]:
    payload = {
        "generated_at": utc_now_iso(),
        "base_url": base_url,
        "duration_seconds": round(duration_seconds, 3),
        "setup": normalize_json(setup_data),
        "steps": [normalize_json(asdict(step)) for step in steps],
        "log_checks": normalize_json(log_checks),
    }

    try:
        with open(file_path, "w", encoding="utf-8") as evidence_file:
            json.dump(payload, evidence_file, indent=2, ensure_ascii=True)
            evidence_file.write("\n")
    except OSError as exc:
        return False, f"Failed to write acceptance evidence JSON: {exc}"

    return True, f"Acceptance evidence JSON saved to {file_path}"


def run_acceptance_suite(
    base_url: str,
    timeout: float,
    values: dict[str, str],
    artifacts_dir: str,
    evidence_json_name: str,
    log_file_name: str,
) -> int:
    print("\nRunning ordered acceptance suite...")
    started = time.time()

    ensure_directory(artifacts_dir)
    evidence_json_path = resolve_artifact_path(artifacts_dir, evidence_json_name)
    log_file_path = resolve_artifact_path(artifacts_dir, log_file_name)

    setup_data: dict[str, Any] = {
        "run_suffix": uuid.uuid4().hex[:8],
        "artifacts_dir": artifacts_dir,
    }
    evidence_steps: list[EvidenceStep] = []

    success_promise_id = ""
    tracker_failure_promise_id = ""
    creation_log_checks: dict[str, Any] = {}
    failure_log_checks: dict[str, Any] = {}
    creation_expected: list[str] = []
    failure_expected: list[str] = []
    creation_missing: list[str] = ["log capture failed"]
    failure_missing: list[str] = ["log capture failed"]
    log_capture_ok = False
    log_capture_message = ""
    creation_grep_dump_path = resolve_artifact_path(
        artifacts_dir,
        "creation_sequence_grep.log",
    )
    failure_grep_dump_path = resolve_artifact_path(
        artifacts_dir,
        "failure_sequence_grep.log",
    )
    creation_grep_message = ""
    failure_grep_message = ""

    # Setup: create a valid politician for success and retraction scenarios.
    setup_politician_body = {
        "name": f"Acceptance Politician {setup_data['run_suffix']}",
        "role": "Governor",
    }
    politician_status, _ph, politician_payload, politician_text, _purl = request_json(
        method="POST",
        base_url=base_url,
        path="/politicians",
        timeout=timeout,
        body=setup_politician_body,
    )
    politician_id = ""
    if (
        politician_status in (200, 201)
        and isinstance(politician_payload, dict)
        and "id" in politician_payload
    ):
        politician_id = str(politician_payload["id"])
        values["politician_id"] = politician_id
        setup_data["valid_politician_id"] = politician_id
    else:
        setup_data["setup_error"] = {
            "message": "Failed to create setup politician",
            "status": politician_status,
            "body": normalize_json(politician_payload),
            "text": politician_text,
        }

    if not politician_id:
        duration = time.time() - started
        export_acceptance_collection(
            file_path=evidence_json_path,
            base_url=base_url,
            duration_seconds=duration,
            setup_data=setup_data,
            steps=evidence_steps,
            log_checks={"capture_ok": False, "message": "setup failed before steps"},
        )
        print("Acceptance suite failed during setup.")
        return 1

    # Step 1
    step1_title = "POST /promises with a valid politician_id, showing status PENDING"
    step1_body = {
        "title": f"Acceptance pending test {setup_data['run_suffix']}",
        "description": "Acceptance path for initial pending state",
        "politician_id": politician_id,
    }
    step1_status, _s1h, step1_payload, step1_text, step1_url = request_json(
        method="POST",
        base_url=base_url,
        path="/promises",
        timeout=timeout,
        body=step1_body,
    )
    step1_status_text = ""
    if isinstance(step1_payload, dict):
        step1_status_text = str(step1_payload.get("status", ""))
    if isinstance(step1_payload, dict) and "id" in step1_payload:
        success_promise_id = str(step1_payload["id"])
        values["promise_id"] = success_promise_id

    step1_passed = (
        step1_status in (200, 201)
        and bool(success_promise_id)
        and normalize_status(step1_status_text) == "PENDING"
    )
    add_evidence_step(
        collection=evidence_steps,
        title=step1_title,
        method="POST",
        path="/promises",
        url=step1_url,
        expected="201 response with status PENDING",
        passed=step1_passed,
        status=step1_status,
        request_body=step1_body,
        response_body=step1_payload,
        response_text=step1_text,
        notes=f"promise_id={success_promise_id or '<missing>'}",
    )

    if not success_promise_id:
        duration = time.time() - started
        export_acceptance_collection(
            file_path=evidence_json_path,
            base_url=base_url,
            duration_seconds=duration,
            setup_data=setup_data,
            steps=evidence_steps,
            log_checks={"capture_ok": False, "message": "step 1 failed; no promise_id"},
        )
        print("Acceptance suite stopped because step 1 did not produce promise_id.")
        return 1

    # Step 2
    step2_title = "GET /query/promises/{id} immediately after, showing status PENDING"
    step2_path = f"/query/promises/{success_promise_id}"
    step2_status, _s2h, step2_payload, step2_text, step2_url = request_json(
        method="GET",
        base_url=base_url,
        path=step2_path,
        timeout=timeout,
    )
    immediate_status = step2_status
    immediate_projection_status = ""
    if isinstance(step2_payload, dict):
        immediate_projection_status = str(step2_payload.get("status", ""))

    if not (
        step2_status == 200
        and isinstance(step2_payload, dict)
        and normalize_status(step2_payload.get("status")) == "PENDING"
    ):
        poll_result = poll_json_endpoint(
            method="GET",
            base_url=base_url,
            path=step2_path,
            timeout=timeout,
            max_attempts=10,
            interval_seconds=0.5,
            predicate=lambda status, payload: (
                status == 200
                and isinstance(payload, dict)
                and normalize_status(payload.get("status")) == "PENDING"
            ),
        )
        step2_status = poll_result.status
        step2_payload = poll_result.payload
        step2_text = poll_result.text
        step2_notes = (
            f"initial_status={immediate_status}, initial_projection_status="
            f"{immediate_projection_status or '<missing>'}, attempts={poll_result.attempts}"
        )
        step2_passed = poll_result.matched
    else:
        step2_notes = (
            f"initial_status={immediate_status}, initial_projection_status="
            f"{immediate_projection_status or '<missing>'}, attempts=1"
        )
        step2_passed = True

    add_evidence_step(
        collection=evidence_steps,
        title=step2_title,
        method="GET",
        path=step2_path,
        url=step2_url,
        expected="200 response with status PENDING",
        passed=step2_passed,
        status=step2_status,
        request_body=None,
        response_body=step2_payload,
        response_text=step2_text,
        notes=step2_notes,
    )

    # Step 3
    step3_title = (
        "GET /query/promises/{id} a moment later, showing status ACTIVE with politician_name"
    )
    step3_result = poll_json_endpoint(
        method="GET",
        base_url=base_url,
        path=step2_path,
        timeout=timeout,
        max_attempts=45,
        interval_seconds=1.0,
        predicate=lambda status, payload: (
            status == 200
            and isinstance(payload, dict)
            and normalize_status(payload.get("status")) == "ACTIVE"
            and has_non_empty_text(payload.get("politician_name"))
        ),
    )
    add_evidence_step(
        collection=evidence_steps,
        title=step3_title,
        method="GET",
        path=step2_path,
        url=step2_url,
        expected="200 response with status ACTIVE and politician_name populated",
        passed=step3_result.matched,
        status=step3_result.status,
        request_body=None,
        response_body=step3_result.payload,
        response_text=step3_result.text,
        notes=f"attempts={step3_result.attempts}",
    )

    # Optional setup for stronger source_count verification.
    source_setup: dict[str, Any] = {}
    source_status, _src_h, source_payload, source_text, _src_url = request_json(
        method="POST",
        base_url=base_url,
        path="/sources",
        timeout=timeout,
        body={
            "name": f"Acceptance Source {setup_data['run_suffix']}",
            "url": f"https://example.com/acceptance/{setup_data['run_suffix']}",
        },
    )
    source_id = ""
    if source_status in (200, 201) and isinstance(source_payload, dict) and "id" in source_payload:
        source_id = str(source_payload["id"])
        values["source_id"] = source_id
        link_status, _lnk_h, link_payload, link_text, _lnk_url = request_json(
            method="POST",
            base_url=base_url,
            path="/sources/link",
            timeout=timeout,
            body={"promise_id": success_promise_id, "source_id": source_id},
        )
        source_setup = {
            "create_source_status": source_status,
            "source_id": source_id,
            "link_status": link_status,
            "link_body": normalize_json(link_payload),
            "link_text": link_text,
        }
    else:
        source_setup = {
            "create_source_status": source_status,
            "create_source_body": normalize_json(source_payload),
            "create_source_text": source_text,
        }
    setup_data["source_setup"] = source_setup

    # Step 4
    step4_title = "PATCH /promises/{id}/status with status retracted, triggering retraction Saga"
    step4_path = f"/promises/{success_promise_id}/status"
    step4_body = {"status": "retracted"}
    step4_status, _s4h, step4_payload, step4_text, step4_url = request_json(
        method="PATCH",
        base_url=base_url,
        path=step4_path,
        timeout=timeout,
        body=step4_body,
    )
    step4_payload_status = ""
    if isinstance(step4_payload, dict):
        step4_payload_status = str(step4_payload.get("status", ""))
    step4_passed = step4_status in (200, 202) and (
        not step4_payload_status
        or normalize_status(step4_payload_status) in {"RETRACTING", "RETRACTED"}
    )
    add_evidence_step(
        collection=evidence_steps,
        title=step4_title,
        method="PATCH",
        path=step4_path,
        url=step4_url,
        expected="Request accepted and promise status enters retracting flow",
        passed=step4_passed,
        status=step4_status,
        request_body=step4_body,
        response_body=step4_payload,
        response_text=step4_text,
        notes="",
    )

    # Step 5
    step5_title = "GET /query/promises/{id} after retraction completes, showing ARCHIVED and source_count 0"
    step5_result = poll_json_endpoint(
        method="GET",
        base_url=base_url,
        path=step2_path,
        timeout=timeout,
        max_attempts=60,
        interval_seconds=1.0,
        predicate=lambda status, payload: (
            status == 200
            and isinstance(payload, dict)
            and normalize_status(payload.get("status")) == "ARCHIVED"
            and int(payload.get("source_count", -1)) == 0
        ),
    )
    add_evidence_step(
        collection=evidence_steps,
        title=step5_title,
        method="GET",
        path=step2_path,
        url=step2_url,
        expected="200 response with status ARCHIVED and source_count 0",
        passed=step5_result.matched,
        status=step5_result.status,
        request_body=None,
        response_body=step5_result.payload,
        response_text=step5_result.text,
        notes=f"attempts={step5_result.attempts}",
    )

    # Step 6
    step6_title = (
        "POST /promises with non-existent politician_id, then GET /query/promises/{id} shows FAILED"
    )
    invalid_politician_id = f"missing-{uuid.uuid4().hex[:10]}"
    step6_post_body = {
        "title": f"Acceptance invalid-politician {setup_data['run_suffix']}",
        "description": "Compensation path for invalid politician",
        "politician_id": invalid_politician_id,
    }
    step6_post_status, _s6h, step6_post_payload, step6_post_text, step6_post_url = request_json(
        method="POST",
        base_url=base_url,
        path="/promises",
        timeout=timeout,
        body=step6_post_body,
    )
    invalid_promise_id = ""
    if isinstance(step6_post_payload, dict) and "id" in step6_post_payload:
        invalid_promise_id = str(step6_post_payload["id"])

    step6_get_result = PollResult(
        matched=False,
        attempts=0,
        status=None,
        headers={},
        payload=None,
        text="",
    )
    if invalid_promise_id:
        step6_get_result = poll_json_endpoint(
            method="GET",
            base_url=base_url,
            path=f"/query/promises/{invalid_promise_id}",
            timeout=timeout,
            max_attempts=60,
            interval_seconds=1.0,
            predicate=lambda status, payload: (
                status == 200
                and isinstance(payload, dict)
                and normalize_status(payload.get("status")) == "FAILED"
            ),
        )

    step6_passed = (
        step6_post_status in (200, 201)
        and bool(invalid_promise_id)
        and step6_get_result.matched
    )
    step6_path = (
        f"/promises -> /query/promises/{invalid_promise_id}"
        if invalid_promise_id
        else "/promises -> /query/promises/{id}"
    )
    add_evidence_step(
        collection=evidence_steps,
        title=step6_title,
        method="POST -> GET",
        path=step6_path,
        url=step6_post_url,
        expected="Create succeeds, then projection status converges to FAILED",
        passed=step6_passed,
        status=step6_get_result.status if invalid_promise_id else step6_post_status,
        request_body=step6_post_body,
        response_body={
            "create": normalize_json(step6_post_payload),
            "query": normalize_json(step6_get_result.payload),
        },
        response_text=(
            f"create_text={step6_post_text}\nquery_text={step6_get_result.text}"
        ),
        notes=(
            f"invalid_promise_id={invalid_promise_id or '<missing>'}, "
            f"query_attempts={step6_get_result.attempts}"
        ),
    )

    # Step 7
    step7_title = (
        "POST /promises with valid politician and broken Trackers DB shows TrackingCreationFailed and FAILED"
    )
    step7_setup: dict[str, Any] = {}

    broken_path_politician_id = ""
    broken_politician_status, _bp_h, broken_politician_payload, broken_politician_text, _bp_url = request_json(
        method="POST",
        base_url=base_url,
        path="/politicians",
        timeout=timeout,
        body={"name": f"Broken DB Politician {setup_data['run_suffix']}", "role": "Mayor"},
    )
    if (
        broken_politician_status in (200, 201)
        and isinstance(broken_politician_payload, dict)
        and "id" in broken_politician_payload
    ):
        broken_path_politician_id = str(broken_politician_payload["id"])

    step7_setup["broken_politician_status"] = broken_politician_status
    step7_setup["broken_politician_body"] = normalize_json(broken_politician_payload)
    step7_setup["broken_politician_text"] = broken_politician_text

    db_broken = False
    db_restore_ok = False
    db_break_message = ""
    db_restore_message = ""

    step7_post_status: int | None = None
    step7_post_payload: Any | None = None
    step7_post_body: dict[str, Any] | None = None
    step7_post_text = ""
    step7_post_url = base_url.rstrip("/") + "/promises"
    step7_query_result = PollResult(
        matched=False,
        attempts=0,
        status=None,
        headers={},
        payload=None,
        text="",
    )

    if broken_path_politician_id:
        db_broken, db_break_message = break_trackers_database(timeout=max(timeout, 20))
        step7_setup["break_trackers_db"] = db_break_message

        try:
            if db_broken:
                step7_post_body = {
                    "title": f"Broken trackers DB {setup_data['run_suffix']}",
                    "description": "Real tracking DB failure compensation test",
                    "politician_id": broken_path_politician_id,
                }
                (
                    step7_post_status,
                    _s7h,
                    step7_post_payload,
                    step7_post_text,
                    step7_post_url,
                ) = request_json(
                    method="POST",
                    base_url=base_url,
                    path="/promises",
                    timeout=timeout,
                    body=step7_post_body,
                )

                if (
                    step7_post_status in (200, 201)
                    and isinstance(step7_post_payload, dict)
                    and "id" in step7_post_payload
                ):
                    tracker_failure_promise_id = str(step7_post_payload["id"])
                    step7_query_result = poll_json_endpoint(
                        method="GET",
                        base_url=base_url,
                        path=f"/query/promises/{tracker_failure_promise_id}",
                        timeout=timeout,
                        max_attempts=60,
                        interval_seconds=1.0,
                        predicate=lambda status, payload: (
                            status == 200
                            and isinstance(payload, dict)
                            and normalize_status(payload.get("status")) == "FAILED"
                        ),
                    )
        finally:
            db_restore_ok, db_restore_message = restore_trackers_database(timeout=max(timeout, 30))
            step7_setup["restore_trackers_db"] = db_restore_message
    else:
        step7_setup["break_trackers_db"] = "skipped: failed to create scenario politician"

    step7_passed = (
        bool(broken_path_politician_id)
        and db_broken
        and step7_post_status in (200, 201)
        and bool(tracker_failure_promise_id)
        and step7_query_result.matched
        and db_restore_ok
    )
    step7_path = (
        f"/promises -> /query/promises/{tracker_failure_promise_id}"
        if tracker_failure_promise_id
        else "/promises -> /query/promises/{id}"
    )
    add_evidence_step(
        collection=evidence_steps,
        title=step7_title,
        method="POST -> GET",
        path=step7_path,
        url=step7_post_url,
        expected="Trackers write fails, TrackingCreationFailed compensation triggers, projection shows FAILED",
        passed=step7_passed,
        status=step7_query_result.status if tracker_failure_promise_id else step7_post_status,
        request_body={
            "break_trackers_db": "DROP TABLE tracking_records",
            "promise_request": normalize_json(step7_post_body),
        },
        response_body={
            "query": normalize_json(step7_query_result.payload),
            "db": step7_setup,
        },
        response_text=(
            f"create_text={step7_post_text}\nquery_text={step7_query_result.text}\n"
            f"db_break={db_break_message}\ndb_restore={db_restore_message}"
        ),
        notes=(
            f"tracker_failure_promise_id={tracker_failure_promise_id or '<missing>'}, "
            f"query_attempts={step7_query_result.attempts}"
        ),
    )

    setup_data["step7_setup"] = step7_setup

    # Log evidence checks for creation and failure paths.
    keywords = [
        success_promise_id,
        tracker_failure_promise_id,
        "Outbox poller in Promises Service",
        "Politicians Service consumer",
        "Outbox poller in Politicians Service",
        "Trackers Service consumer",
        "Outbox poller in Trackers Service",
        "Projection Service consumer",
        "TrackingCreationFailed",
    ]
    keywords = [keyword for keyword in keywords if keyword]

    if success_promise_id and tracker_failure_promise_id:
        log_capture_ok, log_capture_message, filtered_lines = capture_filtered_logs(
            file_path=log_file_path,
            timeout=max(timeout, 90),
            keywords=keywords,
            tail=1800,
        )
    else:
        filtered_lines = []
        log_capture_ok = False
        log_capture_message = "Skipped log sequence checks because required promise IDs are missing"

    if log_capture_ok:
        creation_expected = [
            item.format(promise_id=success_promise_id) for item in CREATION_LOG_SEQUENCE_TEMPLATE
        ]
        failure_expected = [
            item.format(promise_id=tracker_failure_promise_id)
            for item in FAILURE_LOG_SEQUENCE_TEMPLATE
        ]

        creation_ok, creation_missing, creation_matched = verify_log_sequence(
            lines=filtered_lines,
            expected_sequence=creation_expected,
        )
        failure_ok, failure_missing, failure_matched = verify_log_sequence(
            lines=filtered_lines,
            expected_sequence=failure_expected,
        )

        creation_log_checks = {
            "passed": creation_ok,
            "expected": creation_expected,
            "missing": creation_missing,
            "matched_lines": creation_matched,
        }
        failure_log_checks = {
            "passed": failure_ok,
            "expected": failure_expected,
            "missing": failure_missing,
            "matched_lines": failure_matched,
        }

        _creation_dump_ok, creation_grep_message = write_grep_log_dump(
            source_log_file=log_file_path,
            output_file=creation_grep_dump_path,
            expected_lines=creation_expected,
            missing_lines=creation_missing,
            timeout=max(timeout, 20),
        )
        _failure_dump_ok, failure_grep_message = write_grep_log_dump(
            source_log_file=log_file_path,
            output_file=failure_grep_dump_path,
            expected_lines=failure_expected,
            missing_lines=failure_missing,
            timeout=max(timeout, 20),
        )
    else:
        creation_log_checks = {
            "passed": False,
            "expected": [],
            "missing": ["log capture failed"],
            "matched_lines": [],
        }
        failure_log_checks = {
            "passed": False,
            "expected": [],
            "missing": ["log capture failed"],
            "matched_lines": [],
        }
        with open(creation_grep_dump_path, "w", encoding="utf-8") as creation_dump:
            creation_dump.write("Log capture failed; creation grep dump unavailable.\n")
            creation_dump.write(f"Reason: {log_capture_message}\n")
        with open(failure_grep_dump_path, "w", encoding="utf-8") as failure_dump:
            failure_dump.write("Log capture failed; failure grep dump unavailable.\n")
            failure_dump.write(f"Reason: {log_capture_message}\n")
        creation_grep_message = f"Grep log dump saved to {creation_grep_dump_path}"
        failure_grep_message = f"Grep log dump saved to {failure_grep_dump_path}"

    log_checks = {
        "capture_ok": log_capture_ok,
        "capture_message": log_capture_message,
        "log_file": log_file_path,
        "grep_dumps": {
            "creation": {
                "file": creation_grep_dump_path,
                "message": creation_grep_message,
            },
            "failure": {
                "file": failure_grep_dump_path,
                "message": failure_grep_message,
            },
        },
        "creation_sequence": creation_log_checks,
        "failure_sequence": failure_log_checks,
    }

    duration = time.time() - started
    export_ok, export_message = export_acceptance_collection(
        file_path=evidence_json_path,
        base_url=base_url,
        duration_seconds=duration,
        setup_data=setup_data,
        steps=evidence_steps,
        log_checks=log_checks,
    )

    print(export_message)
    print(log_capture_message)
    print(creation_grep_message)
    print(failure_grep_message)

    all_steps_passed = all(step.passed for step in evidence_steps)
    sequence_passed = (
        log_checks["creation_sequence"]["passed"]
        and log_checks["failure_sequence"]["passed"]
    )

    if not export_ok:
        return 1

    if all_steps_passed and sequence_passed:
        print("Acceptance suite passed.")
        return 0

    print("Acceptance suite failed. Check evidence JSON and logs for missing assertions.")
    return 1



def run_endpoint(
    endpoint: Endpoint,
    base_url: str,
    timeout: float,
    values: dict[str, str],
    interactive: bool,
) -> tuple[bool, int | None]:
    path_values = resolve_path_values(endpoint, values, interactive)
    body = collect_body(endpoint, values, interactive)
    url = build_url(base_url, endpoint, path_values)

    if interactive and body is not None:
        print("Request body preview:")
        print(json.dumps(body, indent=2, ensure_ascii=True))
        should_send = input("Send request? [Y/n]: ").strip().lower()
        if should_send == "n":
            print("Request canceled.")
            return True, None


    print("-" * 72)
    print(f"{endpoint.method} {url}")

    try:
        status, headers, response_body = send_request(endpoint.method, url, timeout=timeout, body=body)
    except error.URLError as exc:
        print(f"Request failed: {exc.reason}")
        return False, None
    except Exception as exc:  # pragma: no cover - defensive fallback for manual usage
        print(f"Unexpected request error: {exc}")
        return False, None

    printable_body = decode_response_body(headers, response_body)
    print(f"Status: {status}")
    print(f"Content-Type: {get_header(headers, 'Content-Type', '<missing>')}")
    print("Body:")
    print(printable_body if printable_body else "<empty>")

    return True, status


def print_menu(base_url: str, timeout: float, values: dict[str, str]) -> None:
    print("\n" + "=" * 72)
    print("API Gateway Endpoint Tester")
    print("=" * 72)
    print(f"Gateway base URL : {base_url}")
    print(f"Timeout (seconds): {timeout}")
    print(f"promise_id       : {values['promise_id']}")
    print(f"politician_id    : {values['politician_id']}")
    print(f"source_id        : {values['source_id']}")
    print("-" * 72)

    for idx, endpoint in enumerate(ENDPOINTS, start=1):
        print(f"{idx:2}. {endpoint.method:5} {endpoint.path_template:30} {endpoint.name}")

    print("-" * 72)
    print("a. Run all endpoint tests")
    print("r. Run saga rollback test (simulate TrackingCreationFailed)")
    print("x. Run acceptance suite (ordered artifacts + log checks)")
    print("s. Settings")
    print("q. Quit")


def settings_menu(base_url: str, timeout: float, values: dict[str, str]) -> tuple[str, float, dict[str, str]]:
    while True:
        print("\nSettings")
        print("1. Change gateway base URL")
        print("2. Change timeout")
        print("3. Change default promise_id")
        print("4. Change default politician_id")
        print("5. Change default source_id")
        print("b. Back")

        choice = input("Select option: ").strip().lower()

        if choice == "1":
            new_url = input("New base URL: ").strip()
            if new_url:
                base_url = new_url
        elif choice == "2":
            new_timeout = input("New timeout (seconds): ").strip()
            if new_timeout:
                try:
                    parsed = float(new_timeout)
                    if parsed <= 0:
                        print("Timeout must be > 0.")
                    else:
                        timeout = parsed
                except ValueError:
                    print("Invalid timeout value.")
        elif choice == "3":
            new_promise_id = input("New default promise_id: ").strip()
            if new_promise_id:
                values["promise_id"] = new_promise_id
        elif choice == "4":
            new_politician_id = input("New default politician_id: ").strip()
            if new_politician_id:
                values["politician_id"] = new_politician_id
        elif choice == "5":
            new_source_id = input("New default source_id: ").strip()
            if new_source_id:
                values["source_id"] = new_source_id
        elif choice == "b":
            return base_url, timeout, values
        else:
            print("Unknown option.")


def run_all(base_url: str, timeout: float, values: dict[str, str]) -> int:
    print("\nRunning all endpoint tests...\n")
    results: list[tuple[str, int | None, bool]] = []

    for endpoint in ENDPOINTS:
        ok, status = run_endpoint(
            endpoint=endpoint,
            base_url=base_url,
            timeout=timeout,
            values=values,
            interactive=False,
        )
        results.append((f"{endpoint.method} {endpoint.path_template}", status, ok))

    print("\nSummary")
    print("-" * 72)
    failures = 0
    for label, status, ok in results:
        marker = "SENT" if ok else "FAIL"
        code = str(status) if status is not None else "ERR"
        print(f"{marker:4} {code:>4}  {label}")
        if not ok:
            failures += 1

    if failures:
        print(f"\nCompleted with {failures} request failure(s).")
        return 1

    print("\nCompleted. Review status codes and response bodies above.")
    return 0


def run_saga_rollback_test(
    base_url: str,
    timeout: float,
    values: dict[str, str],
    default_log_file: str,
    interactive: bool,
) -> int:
    print("\nRunning saga rollback + tracking failure simulation...")
    print("This flow creates data, then publishes TrackingCreationFailed to trigger compensation.")

    if interactive:
        proceed = input("Continue? [Y/n]: ").strip().lower()
        if proceed == "n":
            print("Canceled.")
            return 0

    log_file = default_log_file
    if interactive:
        log_file = prompt_text("Log file path", required=True, default=default_log_file)

    run_suffix = uuid.uuid4().hex[:8]
    health_url = base_url.rstrip("/") + "/health"
    health_status, _headers, _payload, health_text = send_json_request(
        method="GET",
        url=health_url,
        timeout=timeout,
    )
    if health_status != 200:
        print(f"Health check failed: {health_status}\n{health_text}")
        return 1

    politician_body = {
        "name": f"Saga Tester {run_suffix}",
        "role": "Governor",
    }
    politician_url = base_url.rstrip("/") + "/politicians"
    p_status, _p_headers, p_payload, p_text = send_json_request(
        method="POST",
        url=politician_url,
        timeout=timeout,
        body=politician_body,
    )
    if p_status not in (200, 201) or not isinstance(p_payload, dict) or "id" not in p_payload:
        print(f"Failed to create politician: {p_status}\n{p_text}")
        return 1
    politician_id = str(p_payload["id"])
    values["politician_id"] = politician_id
    print(f"Created politician: {politician_id}")

    promise_body = {
        "title": f"Saga rollback test {run_suffix}",
        "description": "TUI rollback simulation for tracking DB write failure handling",
        "politician_id": politician_id,
    }
    promise_url = base_url.rstrip("/") + "/promises"
    promise_status, _promise_headers, promise_payload, promise_text = send_json_request(
        method="POST",
        url=promise_url,
        timeout=timeout,
        body=promise_body,
    )
    if (
        promise_status not in (200, 201)
        or not isinstance(promise_payload, dict)
        or "id" not in promise_payload
    ):
        print(f"Failed to create promise: {promise_status}\n{promise_text}")
        return 1
    promise_id = str(promise_payload["id"])
    values["promise_id"] = promise_id
    print(f"Created promise: {promise_id}")

    print("Waiting for normal creation saga completion (ACTIVE + tracking created)...")
    creation_ready = False
    for attempt in range(1, 31):
        promise_get_url = base_url.rstrip("/") + f"/promises/{promise_id}"
        tracking_get_url = base_url.rstrip("/") + f"/tracking/{promise_id}"
        projection_get_url = base_url.rstrip("/") + f"/query/promises/{promise_id}"

        _ps, _ph, promise_get_payload, _pt = send_json_request(
            method="GET", url=promise_get_url, timeout=timeout
        )
        _ts, _th, tracking_get_payload, _tt = send_json_request(
            method="GET", url=tracking_get_url, timeout=timeout
        )
        _qs, _qh, projection_get_payload, _qt = send_json_request(
            method="GET", url=projection_get_url, timeout=timeout
        )

        promise_state = ""
        if isinstance(promise_get_payload, dict):
            promise_state = str(promise_get_payload.get("status", "")).lower()

        projection_state = ""
        if isinstance(projection_get_payload, dict):
            projection_state = str(projection_get_payload.get("status", ""))

        tracking_exists = isinstance(tracking_get_payload, dict) and bool(
            tracking_get_payload.get("promise_id")
        )

        print(
            f"attempt {attempt}: promise={promise_state or '<missing>'}, "
            f"tracking_exists={tracking_exists}, projection={projection_state or '<missing>'}"
        )

        if promise_state == "active" and tracking_exists and projection_state == "ACTIVE":
            creation_ready = True
            break

        time.sleep(1)

    if not creation_ready:
        print("Creation saga did not converge to ACTIVE in time.")
        print("Proceeding anyway to test rollback/failure branch.")

    published, publish_message = publish_tracking_creation_failed_event(
        promise_id=promise_id,
        politician_id=politician_id,
        timeout=max(timeout, 20),
    )
    if not published:
        print(f"Could not publish TrackingCreationFailed: {publish_message}")
        return 1
    print(publish_message)

    print("Waiting for compensation cascade (promise FAILED + projection FAILED)...")
    rollback_done = False
    promise_state = ""
    projection_state = ""
    for attempt in range(1, 31):
        promise_get_url = base_url.rstrip("/") + f"/promises/{promise_id}"
        projection_get_url = base_url.rstrip("/") + f"/query/promises/{promise_id}"

        _ps, _ph, promise_get_payload, _pt = send_json_request(
            method="GET", url=promise_get_url, timeout=timeout
        )
        _qs, _qh, projection_get_payload, _qt = send_json_request(
            method="GET", url=projection_get_url, timeout=timeout
        )

        promise_state = ""
        if isinstance(promise_get_payload, dict):
            promise_state = str(promise_get_payload.get("status", "")).lower()

        projection_state = ""
        if isinstance(projection_get_payload, dict):
            projection_state = str(projection_get_payload.get("status", ""))

        print(
            f"attempt {attempt}: promise={promise_state or '<missing>'}, "
            f"projection={projection_state or '<missing>'}"
        )

        if promise_state == "failed" and projection_state == "FAILED":
            rollback_done = True
            break

        time.sleep(1)

    logs_ok, logs_message = capture_saga_logs(
        promise_id=promise_id,
        file_path=log_file,
        timeout=max(timeout, 45),
    )
    print(logs_message)

    if not rollback_done:
        print("Rollback/failure branch did not converge to FAILED in time.")
        return 1

    if not logs_ok:
        return 1

    print("Saga rollback test passed.")
    return 0


def main() -> int:
    args = parse_args()

    values = {
        "promise_id": str(args.promise_id),
        "politician_id": str(args.politician_id),
        "source_id": str(args.source_id),
    }
    base_url = args.base_url
    timeout = args.timeout

    if args.all:
        return run_all(base_url, timeout, values)

    if args.saga_rollback_test:
        return run_saga_rollback_test(
            base_url=base_url,
            timeout=timeout,
            values=values,
            default_log_file=args.log_file,
            interactive=False,
        )

    if args.acceptance_suite:
        return run_acceptance_suite(
            base_url=base_url,
            timeout=timeout,
            values=values,
            artifacts_dir=args.artifacts_dir,
            evidence_json_name=args.evidence_json,
            log_file_name=args.log_file,
        )

    while True:
        print_menu(base_url, timeout, values)
        choice = input("Select option: ").strip().lower()

        if choice == "q":
            return 0

        if choice == "a":
            run_all(base_url, timeout, values)
            continue

        if choice == "r":
            run_saga_rollback_test(
                base_url=base_url,
                timeout=timeout,
                values=values,
                default_log_file=args.log_file,
                interactive=True,
            )
            continue

        if choice == "x":
            run_acceptance_suite(
                base_url=base_url,
                timeout=timeout,
                values=values,
                artifacts_dir=args.artifacts_dir,
                evidence_json_name=args.evidence_json,
                log_file_name=args.log_file,
            )
            continue

        if choice == "s":
            base_url, timeout, values = settings_menu(base_url, timeout, values)
            continue

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(ENDPOINTS):
                run_endpoint(
                    endpoint=ENDPOINTS[idx - 1],
                    base_url=base_url,
                    timeout=timeout,
                    values=values,
                    interactive=True,
                )
            else:
                print("Option out of range.")
            continue

        print("Unknown option.")


if __name__ == "__main__":
    sys.exit(main())
