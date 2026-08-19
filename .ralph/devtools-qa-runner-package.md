# devtools-qa-runner package hardening

Continue from the prototype package under `qa/devtools-qa-runner` and make it closer to a standalone GitHub repository.

## Goals
- Split the single-file runner into maintainable modules.
- Add local package metadata suitable for future extraction.
- Document profile schema and examples.
- Keep current npm scripts working.
- Verify the runner still passes against the deployed LMS chatbot.

## Checklist
- [x] Split `src/cli.mjs` into modules: args/profile/devtools/snapshot/scenarios/quality/reporter.
- [x] Add `qa/devtools-qa-runner/package.json` with bin metadata for future repo extraction.
- [x] Add profile schema documentation.
- [x] Add at least one minimal generic example profile.
- [x] Update README with standalone repo usage.
- [x] Run syntax checks.
- [x] Run deployed URL verification.
- [x] Update verification evidence.

## Verification
- `find qa/devtools-qa-runner/src -name '*.mjs' -print0 | xargs -0 -n1 node --check`
- `node --check qa/devtools-qa-runner/src/cli.mjs`
- `npm run qa:devtools-runner -- --url https://<배포 호스트> --profile qa/devtools-qa-runner/profiles/lms-chatbot.json --timeout 120000`
- Report: `reports/devtools-qa-runner/lms-chatbot/latest/qa-report.md`
- Result: PASS, 4 passed / 0 failed / 4 total, quality warning due to favicon console noise.

## Notes
- Continue preserving project-local scripts in root `package.json`.
- Keep dependencies minimal: Node.js + chrome-devtools-mcp CLI via root dev dependency for now.
- New module layout:
  - `src/core/args.mjs`
  - `src/core/profile.mjs`
  - `src/core/devtools-client.mjs`
  - `src/core/artifacts.mjs`
  - `src/core/snapshot.mjs`
  - `src/core/quality.mjs`
  - `src/core/reporter.mjs`
  - `src/core/runner.mjs`
  - `src/scenarios/chatbot.mjs`
- Added docs: `docs/profile-schema.md`.
- Added example: `examples/simple-chat.profile.json`.
