# Handoff

This directory is the private continuity contract for Module Library.

Read in this order before starting work:

1. `.airlab/roadmap.yaml`
2. `.airlab/state.json`
3. `.airlab/decisions.md`
4. Current repository CI/workflows and the files relevant to the selected roadmap item.

Current direction:

- Library is the security, certification, reuse and dependency hub between Researcher and Cantiere.
- A missing capability must be registered at first detection.
- Cantiere-created reusable code must be captured on the first validated implementation.
- Researcher may search in parallel, but its code never executes directly in Cantiere.
- Library must build an application dependency graph so capability improvements can create durable application-upgrade candidates.
- No evolved app version is stable until it has passed a real physical-device validation gate.

Do not reactivate retired direct Researcher -> Cantiere code paths.

When a roadmap item changes state, update `roadmap.yaml`, `state.json` and any new architectural decision in `decisions.md` in the same PR.
