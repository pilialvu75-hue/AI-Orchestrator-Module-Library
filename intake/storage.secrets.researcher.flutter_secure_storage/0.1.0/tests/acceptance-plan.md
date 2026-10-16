# Storage secrets — pinned upstream intake proposal

**State: `discovered`; do not use in Cantiere or a release.**

- Library issue: https://github.com/pilialvu75-hue/AI-Orchestrator-Module-Library/issues/127
- Library capability and draft contract: `storage.secrets` / `storage.secrets.v1` (v1.0, status `draft`)
- Pinned upstream package: `flutter_secure_storage` 11.2.0
- Upstream repository: https://github.com/juliansteenbakker/flutter_secure_storage
- Immutable upstream commit: `e8eeb449cd512b26153f0a3376dfe374dd39a999`
- Source entry: `flutter_secure_storage/lib/flutter_secure_storage.dart`
- Upstream manifest: `flutter_secure_storage/pubspec.yaml` at the exact commit, SDK >=3.8, Flutter >=3.19
- Android package requirement: Android API 23+ documented upstream. The AI Orchestrator target baseline must be checked, not inferred.
- License: BSD-3-Clause; unmodified upstream LICENSE at `provenance/LICENSE`

## Available source-only evidence

Researcher discovery and static upstream preflight have been run on GitHub Actions:

- https://github.com/pilialvu75-hue/AI-Orchestrator-Module-Researcher/actions/runs/38982409403
- https://github.com/pilialvu75-hue/AI-Orchestrator-Module-Researcher/actions/runs/38982734188

At the pinned commit the read-only Researcher preflight reported static security `CLEAR`, vulnerability `CLEAR`, vulnerability admission `true`, and 0 unresolved SBOM entries. This is not the Library's independent security review, and does not validate execution, runtime behavior or integration. No untrusted upstream source was executed by the Researcher.

## Minimum adapter contract to implement and test

Do not copy upstream code into the Library/Cantiere without an independent supply-chain decision. Prefer a pinned package dependency when justified by target toolchains.

- Define and test an abstract `SecretsStore` API for `read(key)`, `write(key,value)`, `delete(key)`, and key enumeration/availability only if the Library contract explicitly permits it.
- Specify null/missing key semantics, key scope/namespace, secret redaction in logs, and error normalization.
- Verify whether Android keystore/biometric mode, backed-up restored data, namespace switches, device reboot and cipher migration preserve confidentiality and recoverability.
- Reject any unapproved plaintext fallback. Explicitly handle locked/unavailable keystore, auth cancellation and failed writes, with no secret leakage.
- Validate Linux secret service, Windows and macOS keychain implementations independently; the upstream plugin manifest advertises these platforms, but this branch contains no physical/desktop proof.
- Re-evaluate Flutter/Dart toolchain compatibility in the actual Aivexus application, and ensure platform code does not fork shared orchestration contracts.
- Create adapter source, contract tests, end-to-end/negative tests and device/desktop receipts before changing `validation.tests_passed` or `security.reviewed`.

## Next authorized gates

1. Acquire a non-overlapping canonical Library intake claim for issue #127. The existing `library-researcher` claim on Researcher PR #98 cannot be silently repurposed.
2. Transition `discovered -> quarantined -> normalized -> tested` only through `tools/library_pipeline.py`, with all stage evidence.
3. Independently verify the source version, BSD redistribution notice, license obligations, SBOM, vulnerability scan and contract/target fit. The known vulnerabilities count here reflects the source preflight only.
4. After real validations, attach Library-owned test-report and security-review artifacts, preserving hash binding to the pinned SHA.
5. Run certification dry-run and independent promotion. Until then **the catalog remains unchanged**; Researcher must not dispatch upstream source straight to Cantiere.

The manifest `platforms` names candidate targets for future verification, **not validated support**. `validated_on` remains empty and the asset is not certified.
