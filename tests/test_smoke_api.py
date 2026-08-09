from __future__ import annotations

import unittest

from tests.smoke_api import canonical_path, normalize_headers, normalize_route_path, openapi_routes


class SmokeApiHelpersTest(unittest.TestCase):
    def test_response_header_lookup_is_case_insensitive(self) -> None:
        headers = normalize_headers(
            {
                "Access-Control-Allow-Origin": "http://127.0.0.1:5173",
                "ACCESS-CONTROL-ALLOW-METHODS": "GET, POST",
            }
        )
        self.assertEqual(headers["access-control-allow-origin"], "http://127.0.0.1:5173")
        self.assertEqual(headers["access-control-allow-methods"], "GET, POST")

    def test_manifest_routes_are_prefixed_once(self) -> None:
        self.assertEqual(canonical_path("/health"), "/api/v1/health")
        self.assertEqual(canonical_path("/jobs?limit=1"), "/api/v1/jobs?limit=1")
        self.assertEqual(canonical_path("/api/v1/settings"), "/api/v1/settings")

    def test_openapi_route_extraction_ignores_non_operations(self) -> None:
        routes = openapi_routes(
            {
                "paths": {
                    "/api/v1/health": {"get": {}, "parameters": []},
                    "/api/v1/jobs": {"post": {}},
                }
            }
        )
        self.assertEqual(routes, {("GET", "/api/v1/health"), ("POST", "/api/v1/jobs")})

    def test_path_converter_is_normalized_for_openapi_comparison(self) -> None:
        self.assertEqual(
            normalize_route_path("/api/v1/jobs/{job_id}/artifacts/{artifact_path:path}"),
            "/api/v1/jobs/{job_id}/artifacts/{artifact_path}",
        )


if __name__ == "__main__":
    unittest.main()
