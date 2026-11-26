"""Install the exact pinned original updater and owner-approved RV host adaptation."""
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / "profiles/android-updater"
ENGINE_PIN = "5f0b3093c15177dff850a914fcfe52ac7e2fc70a"
NS = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", NS)
q = lambda key: f"{{{NS}}}{key}"


def validate_profile(enabled, owner, repo, tester):
    if not enabled:
        if owner or repo or tester:
            raise ValueError("Select --android-updater to configure OTA")
        return
    if not owner or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", owner):
        raise ValueError("Explicit GitHub owner required")
    if not repo or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", repo) or repo in (".", ".."):
        raise ValueError("Explicit GitHub repository required")


def install_android_updater(output, name, display, owner, repo, tester):
    # Export only the pinned package. Generated projects have no git dependency on Library.
    blob = subprocess.check_output(["git", "-C", str(ROOT), "archive", "--format=zip",
                                    ENGINE_PIN + ":packages/aivexus_original_updater"])
    vendor = output / "vendor/aivexus_original_updater"
    vendor.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        archive.extractall(vendor)  # trusted pinned Git tree
    (vendor / "LIBRARY_COMMIT.txt").write_text(ENGINE_PIN + "\n")
    substitutions = {"__PROJECT_SLUG__": name,
                     "__DISPLAY_NAME_DART__": json.dumps(display, ensure_ascii=False).replace("$", r"\$"),
                     "__DISPLAY_NAME_KOTLIN__": json.dumps(display, ensure_ascii=False)[1:-1].replace("$", r"\$"),
                     "__GITHUB_OWNER__": owner, "__GITHUB_REPO__": repo,
                     "__TESTER__": "true" if tester else "false"}
    def render(src, dest):
        text = src.read_text(encoding="utf-8")
        # Single-pass replacement avoids reprocessing user-provided display names.
        text = re.sub("|".join(map(re.escape, substitutions)), lambda m: substitutions[m.group()], text)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    for subdir in ("lib", "test"):
        for src in (PROFILE / subdir).glob("*.dart"):
            render(src, output / subdir / src.name)
    (output / "test/widget_test.dart").unlink(missing_ok=True)
    pubspec = output / "pubspec.yaml"
    text = pubspec.read_text(encoding="utf-8")
    text = text.replace("\ndev_dependencies:", "\n  aivexus_original_updater:\n    path: vendor/aivexus_original_updater\n  http: ^1.2.1\n  shared_preferences: ^2.3.2\n  package_info_plus: ^8.0.0\ndev_dependencies:")
    pubspec.write_text(text, encoding="utf-8")
    android = output / "android/app"
    render(PROFILE / "android/MainActivity.kt.template",
           android / "src/main/kotlin/com/aivexus" / name / "MainActivity.kt")
    render(PROFILE / "android/ota_paths.xml", android / "src/main/res/xml/ota_paths.xml")
    manifest = android / "src/main/AndroidManifest.xml"
    doc = ET.parse(manifest)
    root = doc.getroot()
    for permission in ("android.permission.INTERNET", "android.permission.REQUEST_INSTALL_PACKAGES"):
        if not any(e.get(q("name")) == permission for e in root.findall("uses-permission")):
            ET.SubElement(root, "uses-permission", {q("name"): permission})
    app = root.find("application")
    app.set(q("label"), display)
    app.set(q("usesCleartextTraffic"), "false")
    provider = ET.SubElement(app, "provider", {q("name"): "androidx.core.content.FileProvider",
        q("authorities"): "${applicationId}.fileprovider", q("exported"): "false", q("grantUriPermissions"): "true"})
    ET.SubElement(provider, "meta-data", {q("name"): "android.support.FILE_PROVIDER_PATHS", q("resource"): "@xml/ota_paths"})
    doc.write(manifest, encoding="utf-8", xml_declaration=True)
    gradle = android / "build.gradle.kts"
    with gradle.open("a", encoding="utf-8") as f:
        f.write('\ndependencies { implementation("androidx.core:core-ktx:1.13.1") }\n')
    shutil.copytree(ROOT / "signing", output / "signing", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(PROFILE / "provenance.json", output / "UPDATER-PROVENANCE.json")
