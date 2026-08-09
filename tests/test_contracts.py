"""Dependency-free contract tests for the documented pipeline boundary."""

from __future__ import annotations

import json
import math
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "tests" / "schemas"


class SchemaViolation(AssertionError):
    """Raised when a fixture does not satisfy a local JSON Schema subset."""


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    return False


def validate_schema(value: Any, schema: dict[str, Any], path: str = "$", *, root: dict[str, Any] | None = None) -> None:
    """Validate the small JSON Schema subset used by the checked-in contracts."""

    root = root or schema
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/"):
            raise SchemaViolation(f"{path}: external refs are not supported")
        target: Any = root
        for part in ref[2:].split("/"):
            target = target[part]
        validate_schema(value, target, path, root=root)
        return

    if "const" in schema and value != schema["const"]:
        raise SchemaViolation(f"{path}: expected {schema['const']!r}, got {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaViolation(f"{path}: {value!r} is not in {schema['enum']!r}")

    expected = schema.get("type")
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        if not any(_type_matches(value, candidate) for candidate in types):
            raise SchemaViolation(f"{path}: expected {types}, got {type(value).__name__}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            raise SchemaViolation(f"{path}: number must be finite")
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaViolation(f"{path}: {value} is below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaViolation(f"{path}: {value} is above maximum {schema['maximum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise SchemaViolation(f"{path}: {value} is not above exclusive minimum {schema['exclusiveMinimum']}")

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise SchemaViolation(f"{path}: string is shorter than minLength")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise SchemaViolation(f"{path}: string does not match pattern")

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise SchemaViolation(f"{path}: array is shorter than minItems")
        if "items" in schema:
            for index, item in enumerate(value):
                validate_schema(item, schema["items"], f"{path}[{index}]", root=root)

    if isinstance(value, dict):
        missing = [key for key in schema.get("required", []) if key not in value]
        if missing:
            raise SchemaViolation(f"{path}: missing required keys {missing!r}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise SchemaViolation(f"{path}: unexpected keys {unknown!r}")
        for key, child_schema in properties.items():
            if key in value:
                validate_schema(value[key], child_schema, f"{path}.{key}", root=root)
        additional_schema = schema.get("additionalProperties")
        if isinstance(additional_schema, dict):
            for key, child in value.items():
                if key not in properties:
                    validate_schema(child, additional_schema, f"{path}.{key}", root=root)


def read_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def read_json_fence(relative_path: str) -> Any:
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    match = re.search(r"```json\s*\n(.*?)\n```", text, flags=re.DOTALL)
    if match is None:
        raise AssertionError(f"No JSON fenced example found in {relative_path}")
    return json.loads(match.group(1))


class DocumentedPipelineContractsTest(unittest.TestCase):
    def test_words_example_from_docs(self) -> None:
        value = read_json_fence("docs/03-alignment-whisperx.md")
        validate_schema(value, read_schema("words.schema.json"))
        for index, word in enumerate(value):
            self.assertLess(word["start"], word["end"], f"word {index} has no positive duration")

    def test_placements_example_from_docs(self) -> None:
        value = read_json_fence("docs/05-overlay-placement.md")
        validate_schema(value, read_schema("placements.schema.json"))
        for placement in value["placements"]:
            self.assertIn("/", placement["asset_id"], "asset ids are registry paths")

    def test_timeline_example_from_docs(self) -> None:
        value = read_json_fence("docs/07-timeline-edl.md")
        validate_schema(value, read_schema("timeline.schema.json"))
        overlays = value["tracks"]["overlays"]
        self.assertTrue(all(item["t"] + item["duration_s"] > item["t"] for item in overlays))


class ApiContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads((SCHEMAS / "api-contract.json").read_text(encoding="utf-8"))

    def test_routes_and_dev_origins_are_explicit(self) -> None:
        self.assertEqual(self.contract["base_path"], "/api/v1")
        self.assertEqual(
            self.contract["dev_origins"],
            ["http://127.0.0.1:5173", "http://localhost:5173"],
        )
        self.assertEqual(self.contract["frontend_env"], "VITE_API_BASE_URL")

        route_keys = {
            (route["method"].upper(), route["path"].split("?", 1)[0])
            for route in self.contract["routes"]
        }
        self.assertEqual(len(route_keys), len(self.contract["routes"]))
        for smoke_read in self.contract["smoke_reads"]:
            self.assertIn(
                (smoke_read["method"].upper(), smoke_read["path"].split("?", 1)[0]),
                route_keys,
            )
        cors_preflight = self.contract["cors_preflight"]
        self.assertIn(
            (cors_preflight["method"].upper(), cors_preflight["path"]),
            route_keys,
        )

        frontend_api = (ROOT / "frontend/src/lib/api.ts").read_text(encoding="utf-8")
        self.assertIn("VITE_API_BASE_URL", frontend_api)
        self.assertIn("'/api/v1/jobs'", frontend_api)
        self.assertIn("'/api/v1/settings'", frontend_api)
        self.assertIn("'/api/v1/health'", frontend_api)
        self.assertIn("'/api/v1/intake/normalize'", frontend_api)
        self.assertIn("/api/v1/jobs/${encodeURIComponent(jobId)}", frontend_api)
        self.assertIn("'operator-dashboard'", frontend_api)

    def test_health_examples_validate(self) -> None:
        schema = read_schema("health-response.schema.json")
        value = {
            "status": "degraded",
            "service": "slopshots-backend",
            "version": "1.0.0",
            "data_directory": "/tmp/slopshots-data",
            "data_directory_writable": True,
            "job_count": 0,
            "integrations": {
                "ffmpeg": {
                    "available": False,
                    "dependency": "ffmpeg",
                    "required": True,
                    "executable": "ffmpeg",
                    "detail": "install FFmpeg for rendering",
                },
                "ffprobe": {
                    "available": False,
                    "dependency": "ffprobe",
                    "required": True,
                    "executable": "ffprobe",
                    "detail": "install FFmpeg for media inspection",
                },
                "kokoro": {
                    "available": True,
                    "dependency": "kokoro",
                    "required": True,
                    "executable": None,
                    "detail": None,
                },
                "whisperx": {
                    "available": True,
                    "dependency": "whisperx",
                    "required": True,
                },
                "openai_placement": {
                    "available": False,
                    "dependency": "openai-compatible-placement",
                    "required": False,
                    "detail": "SLOPSHOTS_OPENCODE_ZEN_API_KEY is not configured",
                },
            },
        }
        validate_schema(value, schema)

    def test_base_install_covers_multipart_upload_routes(self) -> None:
        requirements = (ROOT / "backend/requirements.txt").read_text(encoding="utf-8")
        self.assertRegex(requirements, r"(?m)^python-multipart>=0\.0\.9,<1$")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("python-multipart", readme)
        self.assertIn("File", readme)
        self.assertIn("Form", readme)
        self.assertIn("UploadFile", readme)

    def test_health_contract_rejects_missing_runtime_fields(self) -> None:
        with self.assertRaises(SchemaViolation):
            validate_schema(
                {
                    "status": "degraded",
                    "service": "slopshots-backend",
                    "version": "1.0.0",
                    "integrations": {},
                },
                read_schema("health-response.schema.json"),
            )

    def test_invalid_contract_payloads_are_rejected(self) -> None:
        with self.assertRaises(SchemaViolation):
            validate_schema(
                {"placements": [{"asset_id": "meme/cat", "anchor_text": "cat"}]},
                read_schema("placements.schema.json"),
            )

    def test_invalid_api_payloads_are_rejected(self) -> None:
        with self.assertRaises(SchemaViolation):
            validate_schema(
                {"status": "starting"},
                read_schema("health-response.schema.json"),
            )


if __name__ == "__main__":
    unittest.main()
