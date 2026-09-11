# Module Research Backlog

This backlog drives discovery of reusable capabilities. For each high-value capability, the researcher should normally identify at least two independent candidates before recommendation, unless only one credible implementation exists.

## Priority A — common and high leverage

- Authentication/session management
- Secure local storage / secrets abstraction
- HTTP/API client with retries, timeout and cancellation
- Local database / persistence
- Structured logging and diagnostics
- Crash/error reporting abstraction
- Update/download manager
- Background task execution
- Permissions handling
- File import/export
- Configuration/environment management
- Input validation and sanitization
- Encryption / key management patterns
- Network/offline detection and retry policy
- Testing harness / fixtures

## Priority B — AI application capabilities

- Local LLM runtime integration bundle
- Cloud LLM provider adapter contract
- Model download/verification manager
- Prompt/context management patterns
- Streaming inference UI contract
- Tool/function calling abstraction
- Retrieval/RAG indexing
- Speech-to-text integration bundle
- Text-to-speech integration bundle
- Voice turn-taking / interruption controller
- AI usage/cost accounting
- Provider fallback/routing policy

## Priority C — reusable product/UI capabilities

- Login/onboarding flow
- Settings/preferences
- Navigation shell
- Responsive dashboard
- Search/filter/list patterns
- Notifications
- Theming/dark mode
- Accessibility baseline
- Internationalization/localization
- Forms and validation
- Media/file picker
- Export/share flow

## Priority D — security and release engineering

- Secure-by-default network policy
- Dependency/SBOM generation
- Secret scanning
- Static analysis baseline
- Release/update verification
- Signed artifact verification patterns
- Backup/restore
- Audit trail
- Privacy/data-retention controls

## Candidate dossier minimum

Every candidate must record: upstream URL, immutable commit/tag, license, maintenance/activity evidence, supported platforms, dependencies, security notes, integration surface, test plan, benchmark plan, estimated adaptation cost and reason for recommendation/rejection.
