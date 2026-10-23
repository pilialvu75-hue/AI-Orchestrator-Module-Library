import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from research_proposal_transfer import transfer


class TransferTests(unittest.TestCase):
    def test_local_transfer_to_pending_queue(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            researcher = root / "researcher"
            (researcher / "src/researcher").mkdir(parents=True)
            (researcher / "src/researcher/cli.py").write_text("")
            data = root / "data"
            data.mkdir()
            with sqlite3.connect(data / "researcher.db") as conn:
                conn.execute("CREATE TABLE improvement_proposals (proposal_id TEXT)")
            library = root / "library"
            payload = {
                "schema_version": 1,
                "kind": "research_improvement_proposals",
                "proposals": [{
                    "proposal_id": "a" * 64,
                    "capability_id": "ai.local_inference",
                    "novelty": ["topic:quantization"],
                    "acceptance_gates": ["security_gates_pass"],
                    "status": "PROPOSED",
                }],
            }
            with patch("research_proposal_transfer.subprocess.run") as run:
                run.return_value.stdout = json.dumps(payload)
                result = transfer(researcher, library, data, limit=10)
            self.assertEqual(result["created"], 1)
            self.assertTrue(
                (library / ".airlab/research-improvements/pending" / ("a" * 64 + ".json")).is_file()
            )
            self.assertEqual(run.call_args.kwargs["env"]["DATA_DIR"], str(data))
            self.assertEqual(run.call_args.kwargs["timeout"], 60)

    def test_paginated_transfer_imports_later_pages(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            researcher = root / "researcher"
            (researcher / "src/researcher").mkdir(parents=True)
            (researcher / "src/researcher/cli.py").write_text("")
            data = root / "data"
            data.mkdir()
            with sqlite3.connect(data / "researcher.db") as conn:
                conn.execute("CREATE TABLE improvement_proposals (proposal_id TEXT)")
            library = root / "library"
            def proposal(identifier):
                return {"proposal_id": identifier * 64,
                        "capability_id": "ai.local_inference",
                        "novelty": ["topic:quantization"],
                        "acceptance_gates": ["security_gates_pass"],
                        "status": "PROPOSED"}
            def page(items):
                return json.dumps({"schema_version": 1,
                                   "kind": "research_improvement_proposals",
                                   "proposals": items})
            with patch("research_proposal_transfer.subprocess.run") as run:
                run.side_effect = [
                    type("Result", (), {"stdout": page([proposal("a"), proposal("b")])})(),
                    type("Result", (), {"stdout": page([proposal("c")])})(),
                ]
                result = transfer(researcher, library, data, limit=2)
            self.assertEqual(result["created"], 3)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args_list[1].args[0][-2:], ["--offset", "2"])

    def test_oversized_page_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            researcher = root / "researcher"
            (researcher / "src/researcher").mkdir(parents=True)
            (researcher / "src/researcher/cli.py").write_text("")
            data = root / "data"
            data.mkdir()
            with sqlite3.connect(data / "researcher.db") as conn:
                conn.execute("CREATE TABLE improvement_proposals (proposal_id TEXT)")
            item = {"proposal_id": "a" * 64, "capability_id": "ai.local_inference",
                    "novelty": ["topic:quantization"],
                    "acceptance_gates": ["security_gates_pass"], "status": "PROPOSED"}
            payload = {"schema_version": 1, "kind": "research_improvement_proposals",
                       "proposals": [item, {**item, "proposal_id": "b" * 64}]}
            with patch("research_proposal_transfer.subprocess.run") as run:
                run.return_value.stdout = json.dumps(payload)
                with self.assertRaises(ValueError):
                    transfer(researcher, root / "library", data, limit=1)
            self.assertFalse((root / "library/.airlab").exists())

    def test_invalid_database_schema_fails_before_export(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            researcher = root / "researcher"
            (researcher / "src/researcher").mkdir(parents=True)
            (researcher / "src/researcher/cli.py").write_text("")
            data = root / "data"
            data.mkdir()
            with sqlite3.connect(data / "researcher.db") as conn:
                conn.execute("CREATE TABLE unrelated (id INTEGER)")
            with patch("research_proposal_transfer.subprocess.run") as run:
                with self.assertRaises(ValueError):
                    transfer(researcher, root / "library", data)
                run.assert_not_called()

    def test_missing_researcher_checkout_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaises(ValueError):
                transfer(root, root, root)


if __name__ == "__main__":
    unittest.main()
