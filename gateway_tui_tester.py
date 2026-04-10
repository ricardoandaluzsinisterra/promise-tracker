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
  python gateway_tui_tester.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
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

    while True:
        print_menu(base_url, timeout, values)
        choice = input("Select option: ").strip().lower()

        if choice == "q":
            return 0

        if choice == "a":
            run_all(base_url, timeout, values)
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
