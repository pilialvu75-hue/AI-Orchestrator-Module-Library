"""Generate an isolated consumer, using the exact checked-out Diagnostics package."""
from pathlib import Path
import argparse
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
ROOT = PACKAGE.parent.parent
OUT = ROOT / "diagnostics-smoke"

def replace_once(path, anchor, replacement):
    text = path.read_text(encoding="utf-8")
    if text.count(anchor) != 1:
        raise RuntimeError(f"Unexpected scaffold anchor in {path.name}")
    path.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")

def main(platform):
    if OUT.exists():
        raise FileExistsError("Refusing to overwrite existing consumer")
    flutter = shutil.which("flutter")
    if flutter is None:
        raise RuntimeError("Flutter unavailable")
    subprocess.run([flutter, "create", "--no-pub", "--platforms=" + platform,
                    "--org", "com.aivexus.qa", "--project-name", "diagnostics_smoke",
                    str(OUT)], check=True)
    replace_once(OUT / "pubspec.yaml", "\ndev_dependencies:",
                 "\n  aivexus_original_diagnostics:\n    path: ../packages/aivexus_original_diagnostics\ndev_dependencies:")
    shutil.copyfile(HERE / "main.dart", OUT / "lib/main.dart")
    (OUT / "test/widget_test.dart").unlink(missing_ok=True)
    if platform == "android":
        namespace = "com.aivexus.qa.diagnostics_smoke"
        kotlin = OUT / "android/app/src/main/kotlin" / Path(*namespace.split("."))
        for name in ("ResourceTelemetry", "ProcessExitDiagnostics"):
            source = PACKAGE / "host-adapters/android" / f"{name}.kt.template"
            (kotlin / f"{name}.kt").write_text(source.read_text(encoding="utf-8").replace("__ANDROID_NAMESPACE__", namespace), encoding="utf-8")
        (kotlin / "MainActivity.kt").write_text(f"""package {namespace}

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine

class MainActivity : FlutterActivity() {{
    private var resources: ResourceTelemetry? = null
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {{
        super.configureFlutterEngine(flutterEngine)
        resources?.close()
        resources = ResourceTelemetry(applicationContext, flutterEngine)
        ProcessExitDiagnostics.register(applicationContext, flutterEngine)
    }}
    override fun cleanUpFlutterEngine(flutterEngine: FlutterEngine) {{
        resources?.close()
        resources = null
        super.cleanUpFlutterEngine(flutterEngine)
    }}
}}
""", encoding="utf-8")
    elif platform == "windows":
        runner = OUT / "windows/runner"
        shutil.copyfile(PACKAGE / "host-adapters/windows/resource_telemetry.h", runner / "resource_telemetry.h")
        replace_once(runner / "flutter_window.cpp", '#include "flutter_window.h"',
            '#include "flutter_window.h"\n#include "resource_telemetry.h"')
        replace_once(runner / "flutter_window.cpp", "RegisterPlugins(flutter_controller_->engine());",
            "RegisterPlugins(flutter_controller_->engine());\n  RegisterAivexusResourceTelemetry(flutter_controller_->engine()->messenger());")
    print(OUT)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("platform", choices=["android", "windows"])
    main(parser.parse_args().platform)
