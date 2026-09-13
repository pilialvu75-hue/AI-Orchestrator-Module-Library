#!/usr/bin/env python3
"""Filtered diagnostics publisher for AI-Orchestrator Module Library.

This producer writes only to the Library-owned Diagnostics release namespace:
`diagnostics-library-v1-<instance-id>`.

Credentials are read from AI_ORCHESTRATOR_DIAGNOSTICS_TOKEN and are never
serialized into events, files, release bodies, or console output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DIAGNOSTICS_REPOSITORY = "pilialvu75-hue/Ai-orchestrator-diagnostics"
API_ROOT = f"https://api.github.com/repos/{DIAGNOSTICS_REPOSITORY}"
UPLOAD_ROOT = f"https://uploads.github.com/repos/{DIAGNOSTICS_REPOSITORY}"
SCHEMA = "ai-orchestrator.diagnostics.event.v2"
PRODUCER = "library"
MAX_ARCHIVE_BYTES = 1024 * 1024
MAX_RELEASE_BYTES = 20 * 1024 * 1024
LATEST_BYTES = 250 * 1024
SENSITIVE_KEYS = {
    "token", "secret", "password", "authorization", "cookie", "prompt",
    "conversation", "raw_payload", "api_key", "private_key",
}
SAFE_FIELD_KEY = re.compile(r"^[a-z0-9._-]{1,64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
SAFE_INSTANCE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_event(*, producer_version: str, platform: str, instance: str,
                event: str, severity: str, session: str | None = None,
                run: str | None = None, correlation_id: str | None = None,
                fields: dict[str, Any] | None = None,
                timestamp: str | None = None) -> dict[str, Any]:
    if not producer_version or len(producer_version) > 128:
        raise ValueError("invalid producer_version")
    if not SAFE_INSTANCE.fullmatch(instance):
        raise ValueError("invalid instance")
    if session is None and run is None:
        raise ValueError("session or run is required")
    for label, value in (("session", session), ("run", run),
                         ("correlation_id", correlation_id)):
        if value is not None and not SAFE_ID.fullmatch(value):
            raise ValueError(f"invalid {label}")
    if severity not in {"debug", "info", "warning", "error", "critical"}:
        raise ValueError("invalid severity")
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9_.-]{0,127}", event):
        raise ValueError("invalid event")
    filtered_fields: dict[str, Any] = {}
    for key, value in (fields or {}).items():
        if key in SENSITIVE_KEYS or not SAFE_FIELD_KEY.fullmatch(key):
            raise ValueError(f"unsafe diagnostic field: {key}")
        if isinstance(value, (dict, list, tuple, set)):
            raise ValueError(f"non-scalar diagnostic field: {key}")
        if isinstance(value, str) and len(value) > 512:
            raise ValueError(f"diagnostic field too long: {key}")
        filtered_fields[key] = value
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "producer": PRODUCER,
        "producer_version": producer_version,
        "platform": platform,
        "instance": instance,
        "timestamp": timestamp or _utc_now(),
        "event": event,
        "severity": severity,
    }
    if session is not None:
        result["session"] = session
    if run is not None:
        result["run"] = run
    if correlation_id is not None:
        result["correlation_id"] = correlation_id
    if filtered_fields:
        result["fields"] = filtered_fields
    return result


def encode_jsonl(events: Iterable[dict[str, Any]]) -> bytes:
    lines = [json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
             for event in events]
    if not lines:
        raise ValueError("at least one event is required")
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise ValueError("diagnostic archive exceeds 1 MiB")
    return payload


class GitHubDiagnosticsPublisher:
    def __init__(self, *, token: str, instance: str, attempts: int = 4) -> None:
        if not token:
            raise ValueError("diagnostics token is required")
        if not SAFE_INSTANCE.fullmatch(instance):
            raise ValueError("invalid instance")
        self._token = token
        self.instance = instance
        self.attempts = max(1, min(attempts, 6))
        self.tag = f"diagnostics-library-v1-{instance}"

    def _request(self, method: str, url: str, *, body: bytes | None = None,
                 json_body: Any | None = None, missing_ok: bool = False,
                 content_type: str = "application/json") -> Any:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": content_type,
            "User-Agent": "ai-orchestrator-module-library-diagnostics/1",
        }
        data = body
        if json_body is not None:
            data = json.dumps(json_body, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                with urllib.request.urlopen(request, timeout=25) as response:
                    raw = response.read()
                    return json.loads(raw.decode("utf-8")) if raw else None
            except urllib.error.HTTPError as exc:
                if exc.code == 404 and missing_ok:
                    return None
                if exc.code < 500 and exc.code not in {408, 429}:
                    raise RuntimeError(f"GitHub HTTP {exc.code}") from None
                last_error = RuntimeError(f"GitHub HTTP {exc.code}")
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = RuntimeError("GitHub request failed")
            if attempt + 1 < self.attempts:
                time.sleep(min(2 ** attempt, 8))
        raise last_error or RuntimeError("GitHub request failed")

    def _release(self) -> dict[str, Any]:
        tag = urllib.parse.quote(self.tag, safe="")
        release = self._request("GET", f"{API_ROOT}/releases/tags/{tag}", missing_ok=True)
        if release is not None:
            return release
        return self._request("POST", f"{API_ROOT}/releases", json_body={
            "tag_name": self.tag,
            "name": f"Diagnostics Module Library {self.instance}",
            "body": "Filtered AI Orchestrator Module Library diagnostics. JSONL archives use diagnostic-event-v2.",
        })

    def _assets(self, release_id: int) -> list[dict[str, Any]]:
        assets: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = self._request(
                "GET", f"{API_ROOT}/releases/{release_id}/assets?per_page=100&page={page}"
            ) or []
            assets.extend(batch)
            if len(batch) < 100:
                return assets
            page += 1

    def publish(self, payload: bytes) -> str:
        if len(payload) > MAX_ARCHIVE_BYTES:
            raise ValueError("diagnostic archive exceeds 1 MiB")
        digest = hashlib.sha256(payload).hexdigest()
        archive_name = f"library-diag-{digest}.jsonl"
        latest_name = "library-latest.jsonl"
        release = self._release()
        release_id = int(release["id"])
        assets = self._assets(release_id)
        matching = [a for a in assets if a.get("name") == archive_name]
        archive_ok = any(a.get("state") == "uploaded" and int(a.get("size", -1)) == len(payload)
                         for a in matching)
        if not archive_ok:
            for asset in matching:
                self._request("DELETE", f"{API_ROOT}/releases/assets/{int(asset['id'])}")
                assets.remove(asset)
            self._rotate(assets, incoming=len(payload))
            upload_url = (
                f"{UPLOAD_ROOT}/releases/{release_id}/assets?"
                + urllib.parse.urlencode({"name": archive_name})
            )
            uploaded = self._request(
                "POST", upload_url, body=payload, content_type="application/x-ndjson; charset=utf-8"
            )
            if uploaded.get("state") != "uploaded" or int(uploaded.get("size", -1)) != len(payload):
                raise RuntimeError("archive upload could not be verified")
        for asset in [a for a in assets if a.get("name") == latest_name]:
            self._request("DELETE", f"{API_ROOT}/releases/assets/{int(asset['id'])}")
        latest = payload[-LATEST_BYTES:]
        newline = latest.find(b"\n")
        if len(payload) > LATEST_BYTES and newline >= 0:
            latest = latest[newline + 1:]
        latest_url = (
            f"{UPLOAD_ROOT}/releases/{release_id}/assets?"
            + urllib.parse.urlencode({"name": latest_name})
        )
        latest_uploaded = self._request(
            "POST", latest_url, body=latest, content_type="application/x-ndjson; charset=utf-8"
        )
        if latest_uploaded.get("state") != "uploaded" or int(latest_uploaded.get("size", -1)) != len(latest):
            raise RuntimeError("latest upload could not be verified")
        return str(release.get("html_url") or f"https://github.com/{DIAGNOSTICS_REPOSITORY}/releases/tag/{self.tag}")

    def _rotate(self, assets: list[dict[str, Any]], *, incoming: int) -> None:
        owned = [a for a in assets if re.fullmatch(r"library-diag-[a-f0-9]{64}\.jsonl", str(a.get("name", "")))]
        owned.sort(key=lambda a: str(a.get("created_at", "")))
        total = sum(int(a.get("size", 0)) for a in owned)
        count = len(owned)
        for asset in owned:
            if total + incoming <= MAX_RELEASE_BYTES and count < 99:
                break
            self._request("DELETE", f"{API_ROOT}/releases/assets/{int(asset['id'])}")
            total -= int(asset.get("size", 0))
            count -= 1


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", required=True)
    parser.add_argument("--producer-version", required=True)
    parser.add_argument("--platform", default="github-actions")
    parser.add_argument("--run", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--severity", choices=["debug", "info", "warning", "error", "critical"], required=True)
    parser.add_argument("--field", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    fields: dict[str, str] = {}
    for pair in args.field:
        if "=" not in pair:
            raise SystemExit("--field must be KEY=VALUE")
        key, value = pair.split("=", 1)
        fields[key] = value
    event = build_event(
        producer_version=args.producer_version,
        platform=args.platform,
        instance=args.instance,
        run=args.run,
        event=args.event,
        severity=args.severity,
        fields=fields,
    )
    payload = encode_jsonl([event])
    if args.dry_run:
        sys.stdout.buffer.write(payload)
        return 0
    token = os.environ.get("AI_ORCHESTRATOR_DIAGNOSTICS_TOKEN", "")
    if not token:
        raise SystemExit("AI_ORCHESTRATOR_DIAGNOSTICS_TOKEN is not configured")
    publisher = GitHubDiagnosticsPublisher(token=token, instance=args.instance)
    print(publisher.publish(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
