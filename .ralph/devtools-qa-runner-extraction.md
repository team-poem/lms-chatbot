# devtools-qa-runner extraction polish

Prepare `qa/devtools-qa-runner` for future extraction into a standalone GitHub repository.

## Goals
- Add standalone repo boilerplate files.
- Add packaged ignore/license metadata.
- Add real GitHub workflow examples inside the package directory.
- Add pack/dry-run verification.
- Keep existing root scripts working.

## Checklist
- [x] Add `LICENSE` for the future standalone package.
- [x] Add standalone `.gitignore` under `qa/devtools-qa-runner`.
- [x] Add `.github/workflows/ci.yml` example under package dir.
- [x] Add `.github/workflows/smoke.yml` example under package dir.
- [x] Update package metadata/files/scripts for extraction.
- [x] Run package checks/tests.
- [x] Run `npm pack --dry-run` in package dir.
- [x] Run deployed URL smoke verification or record target outage.
- [x] Update verification evidence.

## Verification
- `npm --prefix qa/devtools-qa-runner install --package-lock-only`
- `npm run qa:devtools-runner:check` — passed.
- `npm run qa:devtools-runner:test` — 8 passed / 0 failed.
- `npm --prefix qa/devtools-qa-runner run pack:dry` — passed; tarball dry-run contained 18 files, package size ~8.9 kB.
- `npm --prefix qa/devtools-qa-runner run smoke:lms` — failed because target deployment returned HTTP 502. Evidence: `qa/devtools-qa-runner/reports/devtools-qa-runner/lms-chatbot/latest/qa-report.md` shows `GET https://<배포 호스트> -> 502`. This is a target outage, not a runner packaging failure.

## Notes
- Keep package private for now to avoid accidental publish.
- Workflows are extraction templates until folder becomes its own repo.
- Added future standalone files:
  - `qa/devtools-qa-runner/LICENSE`
  - `qa/devtools-qa-runner/.gitignore`
  - `qa/devtools-qa-runner/.github/workflows/ci.yml`
  - `qa/devtools-qa-runner/.github/workflows/smoke.yml`
  - `qa/devtools-qa-runner/package-lock.json`
- Updated `qa/devtools-qa-runner/package.json` with license, keywords, files, engines, devDependency, and `pack:dry`/`smoke:lms` scripts.
