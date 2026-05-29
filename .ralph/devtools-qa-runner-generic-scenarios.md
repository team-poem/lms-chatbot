# devtools-qa-runner generic scenarios

Extend `qa/devtools-qa-runner` beyond chatbot-only profiles by adding generic scenario primitives that can be reused in other web apps.

## Goals
- Add generic scenario types for common browser QA flows.
- Keep existing chatbot profile and smoke behavior working.
- Document new scenario types in profile schema and examples.
- Add unit coverage where possible.

## Checklist
- [x] Add generic scenario module with `click`, `fill`, `press-key`, `wait-for-text`, and `screenshot` scenario types.
- [x] Route scenario execution based on type while preserving existing `consent`, `question`, `empty-input` chatbot scenarios.
- [x] Update profile validation to accept generic scenario types and require relevant fields.
- [x] Add a generic example profile using new primitives.
- [x] Update `docs/profile-schema.md` with new scenario types.
- [x] Add tests for validation of generic scenario types.
- [x] Run checks/tests.
- [x] Run a local syntax/package verification; skip deployed smoke if server remains 502.

## Verification
- `npm run qa:devtools-runner:check` — passed.
- `npm run qa:devtools-runner:test` — 10 passed / 0 failed.
- `npm --prefix qa/devtools-qa-runner run pack:dry` — passed; package now includes 20 files including `src/scenarios/generic.mjs` and `examples/generic-page.profile.json`.
- Deployed smoke not rerun in this iteration because user indicated the deployed server is currently off/502.

## Notes
- Keep primitives snapshot-driven and DevTools-only.
- Avoid adding external dependencies.
- New generic scenario file: `qa/devtools-qa-runner/src/scenarios/generic.mjs`.
