# AIVEXUS Universal Updater — core v0.1.0 (development only)

Tracking: Library issue #377. This package is **not production-certified**,
not installed in VoiceBridge, and does **not** alter AI Orchestrator's updater.

## Implemented in this PR

- App / platform / channel-specific manifests, strict semantic version comparison,
  no downgrade.
- Ed25519 detached signature over the **exact raw decoded manifest payload**,
  checked against a 32-byte public key pinned in the consuming app. A SHA-256
  digest alone does not authenticate a remote manifest.
- HTTPS + artifact-host allowlist. Redirects are refused by default to prevent
  accidentally sending private authorization headers to another host.
- Streamed size-bounded download, SHA-256 integrity check, abort of staging
  on errors, explicit consent before passing a verified artifact to an installer.
- Caller-driven checks, default minimum 2 minutes while app is active, bounded
  retry backoff; no background process, timers, CLI, or token storage.
- Platform interfaces only. **No live installer adapter yet**.

The real installer adapter must perform publisher/OS-signature validation and
post-installation version checks, protect the user data directory, and only
promote staged artifacts atomically. Windows 7/8.1/11, Android, macOS, Linux,
and Web each require separate capability checks and QA.

## Signed manifest format

The GET endpoint returns the following JSON wrapper (example structure):

~~~json
{
  "schema": "aivexus.signed-update.v1",
  "payload": "<base64 of UTF-8 JSON bytes>",
  "signature": "<base64 of Ed25519 signature on those exact bytes>"
}
~~~

The decoded payload contains app_id, platform, channel, version, url,
size_bytes, sha256, artifact_id, release_id and optional notes. The release
builder signs payload bytes with an **offline/private release-signing key**;
only its public key is shipped in the app. Keep the private key in GitHub
Actions or another secure signing environment, never in source code.

The release authenticity mechanism is separate from OS installer signing.
For private GitHub assets use an authenticated first-party gateway or a
platform adapter that exchanges credentials safely. Ordinary GitHub browser
login is NOT an API credential.

## Next milestones, before calling it finished

1. Add a release-manifest signing/verification fixture and CI for this package.
2. Add a **Windows 11 adapter** into VoiceBridge using its existing private
   GitHub transport, staging and installer checks, without breaking current OTA.
3. Run two *real* VoiceBridge update cycles N→N+1→N+2, verify settings,
   models and audio unchanged, and record success + failure recovery.
4. Only then evaluate Cantiere auto-installation into new app templates and
   cross-platform adapters. Windows rollback is deferred until safe restore
   is demonstrated.

Run: cd packages/universal_updater && dart pub get && dart test && dart analyze
