"""Generate a clean AIVEXUS Flutter application. No reusable modules are installed."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
SLUG = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


def dart_string(value):
    return json.dumps(value, ensure_ascii=False).replace("$", r"\$")


def generate(name, display, output):
    if not SLUG.fullmatch(name):
        raise ValueError("Use a lowercase Dart project slug, e.g. my_app")
    if not display.strip() or len(display) > 100 or any(ord(c) < 32 for c in display):
        raise ValueError("Display name must be 1–100 printable characters")
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError("Destination must not exist; refusing to overwrite")
    flutter = shutil.which("flutter")
    if flutter is None:
        raise RuntimeError("Install Flutter stable and add it to PATH")
    subprocess.run([flutter, "create", "--no-pub", "--platforms=android,windows,linux,macos",
                    "--org", "com.aivexus", "--project-name", name, str(output)], check=True)
    for src in (ROOT / "template").rglob("*"):
        if src.is_file():
            target = output / src.relative_to(ROOT / "template")
            target.parent.mkdir(parents=True, exist_ok=True)
            content = src.read_text(encoding="utf-8")
            content = content.replace("__PROJECT_SLUG__", name)
            content = content.replace("__DISPLAY_NAME_DART__", dart_string(display))
            target.write_text(content, encoding="utf-8")
    return output


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--name", required=True)
    p.add_argument("--display-name", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    print(generate(args.name, args.display_name, args.out))
