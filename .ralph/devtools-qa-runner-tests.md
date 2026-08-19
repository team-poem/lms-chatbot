# devtools-qa-runner tests and CI docs

Harden `qa/devtools-qa-runner` with basic tests and extraction-ready CI/docs.

## Goals
- Add lightweight unit tests for profile validation and snapshot matching.
- Add package test scripts.
- Add CI example documentation for future standalone repo.
- Verify existing runner still works.

## Checklist
- [x] Add node:test unit tests for profile validation.
- [x] Add node:test unit tests for snapshot matching helpers.
- [x] Add package/root npm scripts for runner tests.
- [x] Add standalone GitHub Actions example doc.
- [x] Run tests and syntax checks.
- [x] Run deployed URL smoke verification or record reason if skipped.

## Verification
- `npm run qa:devtools-runner:check`
- `npm run qa:devtools-runner:test`
- Test result: 8 passed / 0 failed.
- `npm run qa:devtools-runner -- --url https://<배포 호스트> --profile qa/devtools-qa-runner/profiles/lms-chatbot.json --timeout 120000`
- Smoke report: `reports/devtools-qa-runner/lms-chatbot/latest/qa-report.md`
- Smoke result: PASS, 4 passed / 0 failed / 4 total, quality warning due to favicon console noise.

## Notes
- Keep tests dependency-free using built-in `node:test` and `node:assert`.
- Added `qa/devtools-qa-runner/test/profile.test.mjs`.
- Added `qa/devtools-qa-runner/test/snapshot.test.mjs`.
- Added `qa/devtools-qa-runner/docs/github-actions.md`.
