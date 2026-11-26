# Isolated device QA

This is a test-only Android/Windows consumer. It does not configure a network receiver, the updater, Beta Access, or a release key. Android ID: com.aivexus.qa.diagnostics_smoke. It is not an update to any existing product.

Physical acceptance: install/launch; press Record synthetic test failure; tap QA 0.1.0 seven times within five seconds; verify runtime console, history and resources. Close and reopen and verify previous event survives. Compare hardware readings with OS tools, distinguish Android process-core CPU from Windows system CPU. For Android 11+, inspect historical exits (user-requested stop is not a crash). Confirm no recipient configured and no upload. A synthetic event is NOT a native crash test. Validate real controlled process exit and restart separately, and do not use personal data. Windows 7/8.1 compatibility not established by this build.

CI compiles the original native adapters; actual device evidence remains required. Artifacts are temporary QA builds, not signed permanent OTA releases.
