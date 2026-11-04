import hashlib
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from library_consumer_execution import consume, canonical


def envelope(files):
    package = {
        "schema": "ai-orchestrator.library-module-package.v1",
        "asset_id": "demo.external", "version": "0.1.0",
        "pin": "demo.external@0.1.0", "availability": "active",
        "files": [{"target_path": name, "content": content} for name, content in files],
    }
    return {"schema": "ai-orchestrator.library-module-package-envelope.v1",
            "package": package,
            "package_sha256": hashlib.sha256(canonical(package).encode()).hexdigest()}


FILES = [("pubspec.yaml", "name: demo_external\\nenvironment:\\n  sdk: '^3.0.0'\\ndev_dependencies:\\n  test: ^1.25.0\\n"),
         ("test/behavior_test.dart", "void main() {}\\n")]


class ConsumerExecutionTests(unittest.TestCase):
    def test_real_runner_required_for_proof(self):
        commands = []
        def runner(command, root):
            commands.append(command)
            self.assertTrue((root / "test/behavior_test.dart").is_file())
            return SimpleNamespace(returncode=0)
        report = consume(envelope(FILES), runner=runner)
        self.assertEqual([["dart", "pub", "get"], ["dart", "test"]], commands)
        self.assertTrue(report["consumer_executed"])
        self.assertTrue(report["passed"])

    def test_researcher_self_test_is_real_behavioral_execution(self):
        commands = []
        files = [FILES[0], ("tool/self_test.dart", "void main() {}")]
        def runner(command, root):
            commands.append(command)
            self.assertTrue((root / "tool/self_test.dart").is_file())
            return SimpleNamespace(returncode=0)
        report = consume(envelope(files), runner=runner)
        self.assertEqual(commands, [["dart", "pub", "get"], ["dart", "run", "tool/self_test.dart"]])
        self.assertEqual(report["behavioral_test_command"], "dart run tool/self_test.dart")

    def test_failing_researcher_self_test_never_passes(self):
        files = [FILES[0], ("tool/self_test.dart", "void main() {}")]
        def runner(command, root):
            return SimpleNamespace(returncode=1 if command[-1] == "tool/self_test.dart" else 0)
        with self.assertRaisesRegex(ValueError, "behavioral tests failed"):
            consume(envelope(files), runner=runner)

    def test_no_tests_cannot_be_consumer_proof(self):
        with self.assertRaisesRegex(ValueError, "no executable"):
            consume(envelope(FILES[:1]), runner=lambda *_: self.fail("must not execute"))

    def test_rehashed_but_wrong_identity_pin_rejected(self):
        value = envelope(FILES)
        value["package"]["pin"] = "different.external@0.1.0"
        value["package_sha256"] = hashlib.sha256(
            canonical(value["package"]).encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, "identity pin mismatch"):
            consume(value, runner=lambda *_: self.fail("must not execute"))

    def test_source_only_upstream_is_not_aivexus_consumer_proof(self):
        value = envelope(FILES)
        value["package"]["source"] = {
            "payload_type": "upstream_reference",
            "adapter_included": False,
        }
        value["package_sha256"] = hashlib.sha256(
            canonical(value["package"]).encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, "source-only upstream export"):
            consume(value, runner=lambda *_: self.fail("must not execute"))

    def test_tampered_package_rejected(self):
        value = envelope(FILES)
        value["package"]["files"][1]["content"] = "changed"
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            consume(value, runner=lambda *_: self.fail("must not execute"))

    def test_path_traversal_and_duplicate_blocked(self):
        for files in [
            [("pubspec.yaml", "x"), ("../outside", "x"), FILES[1]],
            [FILES[0], FILES[1], FILES[1]],
        ]:
            with self.subTest(files=files), self.assertRaisesRegex(ValueError, "unsafe|duplicate"):
                consume(envelope(files), runner=lambda *_: self.fail("must not execute"))

    def test_failing_behavioral_test_never_passes(self):
        def runner(command, root):
            return SimpleNamespace(returncode=1 if command == ["dart", "test"] else 0)
        with self.assertRaisesRegex(ValueError, "behavioral tests failed"):
            consume(envelope(FILES), runner=runner)


if __name__ == "__main__":
    unittest.main()
