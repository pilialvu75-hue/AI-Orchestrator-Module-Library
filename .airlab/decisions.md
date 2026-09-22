# Private architecture decisions

Updated: 2026-09-22

- Library is the mandatory trust boundary for reusable code.
- Researcher and Cantiere may exchange structured control-plane messages in the future, but executable/source payloads from Researcher must pass through Library first.
- A capability created by Cantiere is captured on its first validated reusable implementation; repetition is not required before capture.
- Missing capability detection updates Library needs immediately.
- Library must know which maintained applications depend on which capability/module versions.
- Capability improvements may create application upgrade candidates, but never bypass build, regression, security and physical-device validation.
- CI success alone is not release authority.
- Roadmap/state files are stored only in private repositories for now.
