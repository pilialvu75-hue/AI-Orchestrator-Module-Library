"""Conservative source-level guard for the unprivileged review handoff.

Not a full YAML parser or a substitute for branch protection. Reject any
unrecognized permission entries or job-level permission overrides.
"""
import re
from pathlib import Path


def check_review_workflow(text):
    failures = []
    forbidden = (r"(?m)^\s*pull_request_target\s*:",
                 r"(?m)^\s*workflow_call\s*:",
                 r"(?m)^\s*permissions\s*:\s*(?:write-all|read-all)\s*$",
                 r"(?m)^\s*id-token\s*:\s*write\s*$",
                 r"(?m)^\s*contents\s*:\s*write\s*$",
                 r"(?:\$\{\{\s*)?secrets\.", r"\bself-hosted\b",
                 r"(?m)^\s*persist-credentials\s*:\s*true\s*$")
    for pattern in forbidden:
        if re.search(pattern, text, re.IGNORECASE):
            failures.append("forbidden: " + pattern)
    # Only the exact top-level permissions block is accepted. No job-level
    # override may silently widen privileges.
    permission_blocks = list(re.finditer(r"(?m)^([ \t]*)permissions\s*:\s*(.*)$", text))
    if len(permission_blocks) != 1 or permission_blocks[0].group(1):
        failures.append("exactly one top-level permissions block required")
    elif permission_blocks[0].group(2).strip():
        failures.append("permissions must be a mapping")
    else:
        remainder = text[permission_blocks[0].end():]
        block = []
        for line in remainder.splitlines():
            if line.strip() and not line.startswith((" ", "\t")):
                break
            if line.strip() and not line.lstrip().startswith("#"):
                block.append(line.strip())
        if block != ["contents: read"]:
            failures.append("only contents: read is allowed")
    required = (r"(?m)^\s*runs-on:\s*ubuntu-24\.04\s*$",
                r"(?m)^\s*persist-credentials:\s*false\s*$",
                r"(?m)^\s*submodules:\s*false\s*$",
                r"(?m)^\s*ref:\s*main\s*$",
                r"certification_authorized")
    failures += ["missing: " + p for p in required if not re.search(p, text)]
    return failures


def main():
    path = Path(__file__).resolve().parents[1] / ".github/workflows/review-autonomous-public-dart.yml"
    problems = check_review_workflow(path.read_text(encoding="utf-8"))
    if problems:
        raise SystemExit("\n".join(problems))
    print("Independent review handoff passed conservative source policy check")


if __name__ == "__main__":
    main()
