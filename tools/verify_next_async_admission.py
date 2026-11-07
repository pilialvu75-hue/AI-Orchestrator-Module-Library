"""Fail closed unless three independent CI receipts authorize a TESTED-only candidate.

This validates evidence, not security certification or admission itself.
"""
import argparse
import json
from pathlib import Path


def verify(upstream, consumer, adapter):
    if upstream.get("package") != "async" or consumer.get("package") != "async" or adapter.get("package") != "async":
        raise ValueError("package mismatch")
    commits = {upstream.get("source_commit"), consumer.get("source_commit"), adapter.get("source_commit")}
    if len(commits) != 1 or not next(iter(commits)):
        raise ValueError("upstream revision mismatch")
    for key in ("upstream_pub_get", "upstream_analyze", "upstream_test"):
        if upstream.get(key) != "PASS":
            raise ValueError(f"missing upstream proof: {key}")
    if consumer.get("independent_consumer") != "BEHAVIOR_PASS" or consumer.get("behavior_tested") is not True:
        raise ValueError("independent behavioral consumer not proven")
    if adapter.get("status") != "PACKAGED_CONSUMER_PASS":
        raise ValueError("packaged adapter consumer not proven")
    if any(x.get("certification_authorized") is not False for x in (upstream, consumer, adapter)):
        raise ValueError("certification flags must remain false")
    if any(x.get("admission_authorized") is not False for x in (upstream, consumer, adapter)):
        raise ValueError("unreviewed admission authorization")
    return {"package": "async", "source_commit": upstream["source_commit"],
            "evidence": "THREE_STAGE_FUNCTIONAL_PASS",
            "eligible_for_tested_intake_review": True,
            "admission_authorized": False, "certification_authorized": False}


def main():
    p = argparse.ArgumentParser()
    for name in ("upstream", "consumer", "adapter", "output"):
        p.add_argument("--" + name, required=True, type=Path)
    args = p.parse_args()
    result = verify(*(json.loads(getattr(args, name).read_text())
                      for name in ("upstream", "consumer", "adapter")))
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
