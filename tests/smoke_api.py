#!/usr/bin/env python3
"""Read-only smoke check for a running FastAPI development server.

The check exercises only model-free API surfaces: OpenAPI, health, settings,
the job list, and a CORS preflight. It never creates a job or runs a stage.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NoReturn
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_contracts import SchemaViolation, read_schema, validate_schema  # noqa: E402


HTTP_METHODS = frozenset({"delete", "get", "head", "options", "patch", "post", "put", "trace"})


def normalize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return response headers with case-insensitive, stable lookup keys."""

    return {name.lower(): value for name, value in headers.items()}


def fetch(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    timeout_s: float = 5.0,
) -> tuple[int, dict[str, str], bytes]:
    request = Request(
        base_url.rstrip("/") + path,
        method=method,
        headers=dict(headers or {}),
    )
    with urlopen(request, timeout=timeout_s) as response:
        return response.status, normalize_headers(response.headers), response.read()


def canonical_path(path: str, base_path: str = "/api/v1") -> str:
    """Prefix a manifest-relative route exactly once, preserving its query."""

    base = base_path.rstrip("/")
    if path == base or path.startswith(f"{base}/") or path.startswith(f"{base}?"):
        return path
    return f"{base}/{path.lstrip('/')}"


def normalize_route_path(path: str) -> str:
    """Normalize FastAPI's ``{name:path}`` notation to OpenAPI notation."""

    return re.sub(r"\{([^}:]+):[^}]+\}", r"{\1}", path)


def openapi_routes(openapi: Mapping[str, Any]) -> set[tuple[str, str]]:
    paths = openapi.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("OpenAPI response has no paths object")
    return {
        (method.upper(), normalize_route_path(path))
        for path, operations in paths.items()
        if isinstance(operations, dict)
        for method in operations
        if method.lower() in HTTP_METHODS
    }


def contract_routes(contract: Mapping[str, Any]) -> set[tuple[str, str]]:
    base_path = str(contract["base_path"])
    routes = contract["routes"]
    if not isinstance(routes, list):
        raise ValueError("API contract routes must be a list")
    return {
        (
            str(route["method"]).upper(),
            normalize_route_path(canonical_path(str(route["path"]), base_path)),
        )
        for route in routes
    }


def read_api_contract() -> dict[str, Any]:
    return json.loads((ROOT / "tests/schemas/api-contract.json").read_text(encoding="utf-8"))


def fail(message: str) -> NoReturn:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def _json_body(body: bytes, path: str) -> Any:
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} did not return JSON: {exc}") from exc


def _contains_token(value: str | None, expected: str) -> bool:
    if value is None:
        return False
    return value.strip() == "*" or expected.lower() in {
        token.strip().lower() for token in value.split(",")
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=5.0, help="per-request timeout in seconds")
    args = parser.parse_args()

    try:
        contract = read_api_contract()
        base_path = str(contract["base_path"])

        openapi_status, _, openapi_body = fetch(args.base_url, "/openapi.json", timeout_s=args.timeout)
        if openapi_status != 200:
            fail(f"/openapi.json returned HTTP {openapi_status}")
        openapi = _json_body(openapi_body, "/openapi.json")
        if not isinstance(openapi, dict):
            fail("/openapi.json returned a non-object JSON value")
        actual = openapi_routes(openapi)
        missing = sorted(contract_routes(contract) - actual)
        if missing:
            formatted = ", ".join(f"{method} {path}" for method, path in missing)
            fail(f"OpenAPI is missing canonical route(s): {formatted}")

        health_checked = False
        for read in contract["smoke_reads"]:
            relative_path = str(read["path"])
            path = canonical_path(relative_path, base_path)
            status, _, body = fetch(args.base_url, path, timeout_s=args.timeout)
            if status != 200:
                fail(f"{path} returned HTTP {status}")
            payload = _json_body(body, path)
            response_schema = read.get("response_schema")
            if response_schema:
                validate_schema(payload, read_schema(str(response_schema)))
                if response_schema == "health-response.schema.json":
                    health_checked = True
            elif relative_path.split("?", 1)[0] == "/jobs":
                if not isinstance(payload, list):
                    fail(f"{path} returned a non-array job list")
            elif not isinstance(payload, dict):
                fail(f"{path} returned a non-object JSON value")
        if not health_checked:
            fail("API contract does not declare a health response schema for smoke testing")

        preflight = contract["cors_preflight"]
        preflight_path = canonical_path(str(preflight["path"]), base_path)
        preflight_status, preflight_headers, _ = fetch(
            args.base_url,
            preflight_path,
            method="OPTIONS",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": str(preflight["method"]),
                "Access-Control-Request-Headers": "content-type",
            },
            timeout_s=args.timeout,
        )
        if preflight_status not in (200, 204):
            fail(f"CORS preflight for {preflight_path} returned HTTP {preflight_status}")
        allow_origin = preflight_headers.get("access-control-allow-origin")
        if allow_origin not in ("http://127.0.0.1:5173", "*"):
            fail("CORS preflight did not allow http://127.0.0.1:5173")
        if not _contains_token(preflight_headers.get("access-control-allow-methods"), str(preflight["method"])):
            fail(f"CORS preflight did not allow {preflight['method']} requests")
        if not _contains_token(preflight_headers.get("access-control-allow-headers"), "content-type"):
            fail("CORS preflight did not allow the content-type request header")
    except HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:240]
        except OSError:
            detail = ""
        suffix = f": {detail}" if detail else ""
        fail(f"HTTP {exc.code} while checking the API{suffix}")
    except (URLError, TimeoutError, OSError) as exc:
        fail(f"could not reach {args.base_url}: {exc}")
    except (SchemaViolation, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        fail(f"invalid JSON/API contract response: {exc}")

    print("PASS: canonical OpenAPI routes, model-free reads, and browser CORS preflight")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
