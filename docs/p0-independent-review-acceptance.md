# P0 independent reviewer acceptance gates

Related issue: #219.

The existing review workflow emits unsigned requests and OSV advisory evidence. These outputs are not security approval and must not authorize certification.

A future independent reviewer must verify exact immutable source and CI identities, original license bytes, dependency inventory and real advisory responses. Scanner failures must fail closed. It must inspect privacy, source boundaries and static security risks, record reproducible evidence and only then consider a signed decision.

The review job must not run untrusted candidate code with signing credentials. The builder must never possess the reviewer private key. The protected certification workflow must validate signed statements against its repository-controlled public key and canonical source, SBOM and license digests.

Acceptance requires a new external candidate, different from the manually selected logging demo, to complete unattended discovery, acquisition, isolated testing, independent review, certification and a separate consumer integration test. Each stage must provide correlated GitHub run IDs and immutable hashes. Until then the candidate remains TESTED or BLOCKED, never CERTIFIED.
