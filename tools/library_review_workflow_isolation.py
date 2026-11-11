"""Fail-closed static guard for the unprivileged independent-review handoff."""
from pathlib import Path


def check_review_workflow(text):
    forbidden = ("pull_request_target:", "permissions: write-all",
                 "contents: write", "id-token: write", "secrets.",
                 "self-hosted", "persist-credentials: true")
    failures = [f"forbidden: {word}" for word in forbidden if word in text]
    required = ("permissions:\n  contents: read", "runs-on: ubuntu-24.04",
                "persist-credentials: false", "submodules: false",
                "ref: main", "certification_authorized")
    failures += [f"missing: {word}" for word in required if word not in text]
    return failures


def main():
    path = Path(__file__).resolve().parents[1] / ".github/workflows/review-autonomous-public-dart.yml"
    problems = check_review_workflow(path.read_text(encoding="utf-8"))
    if problems:
        raise SystemExit("\n".join(problems))
    print("Independent review handoff remains unprivileged (static policy check)")


if __name__ == "__main__":
    main()
