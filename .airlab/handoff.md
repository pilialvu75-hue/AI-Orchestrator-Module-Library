# Handoff

This directory is the private continuity contract for Module Library.

Read in this order before starting work:

1. `.airlab/control-plane/README.md`
2. `.airlab/control-plane/canonical-state.json`
3. `.airlab/control-plane/gates.json`
4. `.airlab/control-plane/chat-registry.json`
5. the relevant `.airlab/control-plane/workstreams/<lane>.json`
6. `.airlab/roadmap.yaml` and/or the relevant private public-repository roadmap
7. `.airlab/state.json`
8. `.airlab/decisions.md`
9. Current repository CI/workflows, open work and Diagnostics evidence relevant to the selected roadmap item.

The main/reviewer lane is the only lane that may promote worker results to VERIFIED/DONE. Worker lanes stop at REVIEW_REQUIRED.

Use `tools/chat_lane_bootstrap.py --lane <lane-id>` to generate the current relay for a chat. Worker completion must be submitted as a structured `review_packet` and stop at REVIEW_REQUIRED.

Before implementation, a worker lane must hold a non-expired canonical claim lease. Use `tools/control_plane_manager.py` or an equivalent atomic update through the same schema. Heartbeat long-running work; never bypass a BLOCKED stale-claim reconciliation.

Current direction:

- Library is the security, certification, reuse and dependency hub between Researcher and Cantiere.
- A missing capability must be registered at first detection.
- Cantiere-created reusable code must be captured on the first validated implementation.
- Researcher may search in parallel, but its code never executes directly in Cantiere.
- Library must build an application dependency graph so capability improvements can create durable application-upgrade candidates.
- No evolved app version is stable until it has passed a real physical-device validation gate.

Do not reactivate retired direct Researcher -> Cantiere code paths.

When a roadmap item changes state, update `roadmap.yaml`, `state.json` and any new architectural decision in `decisions.md` in the same PR.


Public repository roadmaps live under `.airlab/public-repositories/`.

Future Researcher first-party mining sources are declared in `.airlab/first-party-sources.yaml`. Treat that manifest as an allowlist, not as a trust waiver: all extracted candidates still require Library intake and certification.
