# devtools-qa-runner extraction

Refactor the project-local QA prototype toward a reusable `devtools-qa-runner` package that can later be split into its own GitHub repository.

## Goals
- Keep existing `lms-chatbot` QA commands working.
- Create a reusable package shape under `qa/devtools-qa-runner`.
- Move hardcoded selectors/scenarios into a profile file.
- Support Chrome DevTools-only mode as the primary reusable path.
- Preserve hybrid Playwright+DevTools runner as project-local or compatibility path.
- Generate Markdown evidence reports for any profile.

## Checklist
- [x] Scaffold `qa/devtools-qa-runner` package layout.
- [x] Add profile schema/example for `lms-chatbot`.
- [x] Refactor DevTools-only runner to load selectors/scenarios from profile.
- [x] Add npm scripts for reusable runner and legacy aliases.
- [x] Verify runner against deployed URL.
- [x] Document repository extraction plan.

## Verification
- `node --check qa/devtools-qa-runner/src/cli.mjs`
- `npm run qa:devtools-runner -- --url https://121.145.133.68.sslip.io --profile qa/devtools-qa-runner/profiles/lms-chatbot.json --timeout 120000`
- Report generated: `reports/devtools-qa-runner/lms-chatbot/latest/qa-report.md`
- Result: PASS, 4 passed / 0 failed / 4 total, quality warning due to favicon console noise.

## Notes
- Target future repo name: `devtools-qa-runner`.
- Start with DevTools-only runner because it aligns with the intended positioning.
- Avoid overgeneralizing too early; profile-based chatbot QA is enough for first extraction.
- Added reusable package docs: `qa/devtools-qa-runner/README.md`.
- Existing project-local commands remain: `qa:chatbot`, `qa:chatbot:devtools`.
