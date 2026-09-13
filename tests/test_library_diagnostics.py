import importlib.util
import json
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "library_diagnostics.py"
spec = importlib.util.spec_from_file_location("library_diagnostics", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class LibraryDiagnosticsTests(unittest.TestCase):
    def test_event_contains_shared_v2_identity(self):
        event = module.build_event(
            producer_version="abc123",
            platform="github-actions",
            instance="module-library-main",
            run="run-42",
            event="LIBRARY_VALIDATION_PASSED",
            severity="info",
            timestamp="2026-09-13T17:00:00+02:00",
            fields={"asset_count": 12, "validator": "validate_library"},
        )
        self.assertEqual(event["schema"], "ai-orchestrator.diagnostics.event.v2")
        self.assertEqual(event["producer"], "library")
        self.assertEqual(event["instance"], "module-library-main")
        self.assertEqual(event["run"], "run-42")
        self.assertEqual(event["severity"], "info")

    def test_payload_is_deterministic_jsonl(self):
        event = module.build_event(
            producer_version="abc123",
            platform="linux",
            instance="library-1",
            session="session-1",
            event="INTAKE_ACCEPTED",
            severity="info",
            timestamp="2026-09-13T15:00:00Z",
            fields={"b": 2, "a": 1},
        )
        first = module.encode_jsonl([event])
        second = module.encode_jsonl([event])
        self.assertEqual(first, second)
        decoded = json.loads(first.decode().strip())
        self.assertEqual(decoded["fields"], {"a": 1, "b": 2})

    def test_sensitive_fields_are_rejected(self):
        for key in ("token", "authorization", "prompt", "conversation", "raw_payload", "api_key"):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    module.build_event(
                        producer_version="abc123",
                        platform="linux",
                        instance="library-1",
                        run="run-1",
                        event="TEST_EVENT",
                        severity="info",
                        fields={key: "forbidden"},
                    )

    def test_nested_or_large_values_are_rejected(self):
        with self.assertRaises(ValueError):
            module.build_event(
                producer_version="abc123",
                platform="linux",
                instance="library-1",
                run="run-1",
                event="TEST_EVENT",
                severity="info",
                fields={"details": {"nested": True}},
            )
        with self.assertRaises(ValueError):
            module.build_event(
                producer_version="abc123",
                platform="linux",
                instance="library-1",
                run="run-1",
                event="TEST_EVENT",
                severity="info",
                fields={"details": "x" * 513},
            )

    def test_namespace_and_owned_rotation_pattern_are_library_only(self):
        publisher = module.GitHubDiagnosticsPublisher(token="not-used-in-unit-test", instance="library-main")
        self.assertEqual(publisher.tag, "diagnostics-library-v1-library-main")
        self.assertNotEqual(publisher.tag, "diagnostics-v1-library-main")
        self.assertEqual(module.MAX_ARCHIVE_BYTES, 1024 * 1024)
        self.assertEqual(module.MAX_RELEASE_BYTES, 20 * 1024 * 1024)

    def test_payload_over_one_mib_is_rejected(self):
        event = {
            "schema": "ai-orchestrator.diagnostics.event.v2",
            "producer": "library",
            "producer_version": "v",
            "platform": "linux",
            "instance": "library",
            "run": "run",
            "timestamp": "2026-09-13T15:00:00Z",
            "event": "E",
            "severity": "info",
            "fields": {"message": "x" * (1024 * 1024)},
        }
        with self.assertRaises(ValueError):
            module.encode_jsonl([event])


if __name__ == "__main__":
    unittest.main()
