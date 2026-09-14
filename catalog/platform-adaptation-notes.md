# AI Orchestrator platform adaptation needs

This list complements `catalog/needs.json` with reusable capabilities needed to carry the Android-first AI Orchestrator architecture to Windows, Linux, macOS, iOS, Web and Raspberry Pi without duplicating the common core.

Principles:
- the common orchestrator/core stays platform-neutral;
- platform branches provide adapters for OS/runtime-specific capabilities;
- certification stays capability- and target-specific;
- a module certified on one target must never be advertised on another target without explicit validation evidence;
- headless Raspberry Pi use is treated as a first-class target, including voice-only operation.

Initial cross-platform adaptation capabilities added to the needs catalog:
- `platform.filesystem` — sandboxed/native filesystem abstraction;
- `platform.process` — local process/shell execution where the OS permits it;
- `platform.permissions` — runtime permission/capability broker;
- `platform.audio_io` — microphone/speaker/device routing abstraction;
- `platform.background_execution` — background tasks/service lifecycle;
- `platform.notifications` — native notification surface;
- `platform.desktop_shell` — window/tray/desktop integration;
- `release.packaging` — platform packaging/signing/distribution pipeline;
- `ai.acceleration_backend` — target-specific local-inference acceleration (Vulkan/CUDA/DirectML/Metal/WebGPU/CPU depending on target).

The existing functional capabilities (`auth.session`, `storage.*`, `network.http`, `diagnostics.logging`, `release.update_manager`, `ai.local_inference`, `voice.stt`, `voice.tts`) remain authoritative. These new items describe the platform adapters needed underneath or beside them, rather than duplicating business logic.
