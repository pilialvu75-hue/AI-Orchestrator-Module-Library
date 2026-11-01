"""Cross-check unsigned OSV evidence against exact source-bound review requests."""
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify(requests, evidence):
    items, reports = requests.get("requests"), evidence.get("reports")
    if not isinstance(items, list) or not items or not isinstance(reports, list):
        raise ValueError("missing review requests or evidence")
    if len(items) != len(reports) or requests.get("count") != len(items) or evidence.get("count") != len(reports):
        raise ValueError("review evidence count mismatch")
    if requests.get("certification_authorized") is not False or evidence.get("certification_authorized") is not False:
        raise ValueError("unsigned packet cannot authorize certification")
    seen = set()
    for item, report in zip(items, reports):
        asset = item.get("asset_id")
        if not isinstance(asset, str) or not asset or asset in seen:
            raise ValueError("duplicate or missing asset")
        seen.add(asset)
        if item.get("status") != "INDEPENDENT_REVIEW_REQUIRED" or item.get("security_reviewed") is not False:
            raise ValueError("review request is not pending")
        if report.get("asset_id") != asset or report.get("security_reviewed") is not False or report.get("certification_authorized") is not False:
            raise ValueError("OSV evidence identity or authorization mismatch")
        if report.get("review_request_sha256") != digest(item):
            raise ValueError("OSV request digest mismatch")
        if report.get("sbom_sha256") != digest(item["dependency_inventory"]["cyclonedx_sbom"]):
            raise ValueError("OSV SBOM digest mismatch")
        if report.get("source_payload_sha256") != item["source"]["payload_tree_sha256"]:
            raise ValueError("OSV source digest mismatch")
        if report.get("advisory_scan_completed") is not True or report.get("provider") != "OSV":
            raise ValueError("OSV scan incomplete")
        expected = sorted(c["purl"] for c in item["dependency_inventory"]["cyclonedx_sbom"]["components"] if isinstance(c.get("purl"), str) and c["purl"].startswith("pkg:pub/"))
        packages = report.get("packages")
        if not isinstance(packages, list) or not expected or expected != sorted(p.get("purl") for p in packages):
            raise ValueError("OSV package coverage mismatch")
        count = report.get("vulnerabilities_found")
        if type(count) is not int or count != sum(len(p["vulnerability_ids"]) for p in packages):
            raise ValueError("OSV vulnerability count mismatch")
    return len(items)
