# AI Orchestrator Lego Connector Standard

The library exists to make reusable software interchangeable by capability, not by file layout.

## Core rule

Every reusable asset declares a stable `connector` contract. The Cantiere must select assets by capability + contract compatibility, never by guessing filenames or project-specific internals.

Example mental model:

`voice.stt -> voice.stt.v1`

Any certified STT asset that implements `voice.stt.v1` can be considered for the same logical slot. The concrete implementation may differ internally.

## Connector fields

- `standard`: always `ai-orchestrator-lego`
- `standard_version`: version of this interchange standard
- `provides`: capabilities and stable contract ids implemented by the asset
- `requires`: dependencies expressed as capabilities/contracts, not hidden assumptions
- `integration_mode`: package, adapter, source bundle, recipe or policy
- `adapters`: target/framework entry points used by the Cantiere to connect the asset
- `configuration_schema`: optional declarative configuration contract
- `healthcheck`: optional reproducible test/probe used after integration

## Swappability rule

Two assets are swappable only when all of the following hold:

1. they provide the same capability id;
2. their contract ids are equal or explicitly compatible;
3. the target platform/framework is supported;
4. required dependencies can be satisfied;
5. license and security policies allow use;
6. integration cost remains lower than fresh implementation;
7. the replacement passes its healthcheck and project tests.

## No arbitrary install scripts

A library manifest must not require the Cantiere to execute unreviewed arbitrary shell commands from a candidate. Integration should be declarative or handled by trusted Cantiere adapters.

## Candidate vs certified

Researcher submissions may use the same connector standard while still being `discovered`, `quarantined` or `normalized`. This makes later comparison easy, but only `certified` assets are eligible for automatic reuse.

## Versioning

Breaking connector-contract changes require a new contract id or major contract version. Internal implementation changes that preserve the contract may create a new asset semantic version.
