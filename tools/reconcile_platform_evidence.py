"""Reconcile desktop consumer receipts with immutable development packages."""
import argparse
import json
from pathlib import Path
from library_development_promotion import verify_source_and_package, lookup, require

TARGETS = ("linux", "windows", "macos")

def reconcile(root, receipts, run_id, jobs):
    require(type(run_id) is int and run_id > 0, "invalid run")
    require(set(receipts) == set(jobs) == set(TARGETS), "missing platform")
    require(all(type(j) is int and j > 0 for j in jobs.values())
            and len(set(jobs.values())) == 3, "invalid jobs")
    index = json.loads((root / "packages/development-index.json").read_text())
    current = {r["pin"]: r for r in index["packages"]
               if r.get("development_qualified") is True
               and r.get("independent_export_consumer") == "PASS"}
    available = lookup(root)
    path = root / "packages/development-platform-evidence.json"
    prior = json.loads(path.read_text())
    require(prior["schema"] == "aivexus.development-platform-evidence.v1", "invalid ledger")
    rows = {}
    expected = None
    for target in TARGETS:
        report = receipts[target]
        require(report.get("schema") == "aivexus.llm-published-consumer.v1"
                and report.get("complete") is True
                and report.get("certified") is False
                and not report.get("blocked_reason"), "incomplete receipt")
        seen = set()
        for item in report["items"]:
            pin, digest = item["pin"], item["package_sha256"]
            require(pin not in seen and item.get("independent_dart_consumer") == "PASS"
                    and item.get("source") == "published Library experimental export"
                    and item.get("production_approved") is False
                    and item.get("certified") is False, "invalid consumer result")
            seen.add(pin)
            require(pin in available, "unknown package")
            verify_source_and_package(root, available[pin], pin, digest)
            if pin in current:
                require(current[pin]["package_sha256"] == digest, "stale receipt")
                rows[(pin, target)] = dict(pin=pin, package_sha256=digest,
                                           target=target, run_id=run_id, job_id=jobs[target])
        require(seen, "empty receipt")
        require(expected is None or seen == expected, "platform coverage mismatch")
        expected = seen
    require(set(current) <= expected, "qualified package missing from regression")
    # Preserve existing proof when identical immutable bytes pass again.
    for old in prior["records"]:
        key = (old["pin"], old["target"])
        if key in rows and rows[key]["package_sha256"] == old["package_sha256"]:
            rows[key] = old
    return dict(schema=prior["schema"], scope=prior["scope"],
                records=[rows[k] for k in sorted(rows, key=lambda k: (TARGETS.index(k[1]), k[0]))])

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--receipts", type=Path, required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--jobs", type=Path, required=True)
    a = p.parse_args()
    receipts = {t: json.loads((a.receipts / t / "consumer-report.json").read_text()) for t in TARGETS}
    result = reconcile(a.root, receipts, a.run_id, json.loads(a.jobs.read_text()))
    (a.root / "packages/development-platform-evidence.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
