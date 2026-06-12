# devtools-qa-runner Separation Implementation Plan

> **REQUIRED SUB-SKILL:** Use the executing-plans skill to implement this plan task-by-task.

**Goal:** Make `devtools-qa-runner` a standalone local package/repo and consume it from `lms-chatbot` without keeping `qa/devtools-qa-runner` as a submodule.

**Architecture:** Keep the reusable runner in `/Users/amazon/lunch.cancelled/devtools-qa-runner`, connected to `https://github.com/team-poem/devtools-qa-runner.git`. Move LMS-specific profiles into `lms-chatbot/qa/devtools-profiles/`, install the runner through `file:../devtools-qa-runner`, and update `lms-chatbot` scripts to call package binaries instead of submodule paths. Do not remove the submodule until standalone changes are committed and verified.

**Tech Stack:** Node.js ESM, npm package `bin` entries, npm `file:` dependency, Git submodules, Node test runner.

---

## Current Known State

- Standalone checkout exists: `/Users/amazon/lunch.cancelled/devtools-qa-runner`
- Existing submodule copy remains: `/Users/amazon/lunch.cancelled/lms-chatbot/qa/devtools-qa-runner`
- GitHub remote: `https://github.com/team-poem/devtools-qa-runner.git`
- Standalone branch: `feat/adversarial-qa`
- `origin/main` is reachable, but the local branch has commits not on `origin/main` plus uncommitted changes.
- Baseline verification already observed before this plan: `npm run check` and `npm test` pass in the standalone checkout.

---

### Task 1: Commit and push the current standalone runner state

**TDD scenario:** Modifying tested code — run existing tests first. Existing uncommitted changes predate this plan, so this task verifies and checkpoints them before further edits.

**Files:**
- Verify/commit in repo: `/Users/amazon/lunch.cancelled/devtools-qa-runner`
- No source edits in this task.

**Step 1: Confirm standalone worktree contains copied submodule changes**

Run:

```bash
cd /Users/amazon/lunch.cancelled/devtools-qa-runner
git status --short
git remote -v
git branch --show-current
```

Expected:

```txt
origin https://github.com/team-poem/devtools-qa-runner.git ...
feat/adversarial-qa
```

There should be modified files such as `README.md`, `package.json`, `src/core/*.mjs`, plus untracked `src/engines/`, `src/index.mjs`, `src/scenarios/registry.mjs`, and `test/registry.test.mjs`.

**Step 2: Run baseline checks**

Run:

```bash
npm run check
npm test
```

Expected:

```txt
check exits 0
node --test exits 0, all tests pass
```

**Step 3: Commit the verified standalone state**

Run:

```bash
git add README.md docs package.json package-lock.json src test
git commit -m "refactor(qa): prepare runner as standalone package"
```

Expected: commit succeeds. If there is nothing to commit, record that the current branch was already checkpointed and continue.

**Step 4: Push the feature branch to GitHub**

Run:

```bash
git push -u origin feat/adversarial-qa
```

Expected: remote branch `origin/feat/adversarial-qa` exists. If push is rejected because the remote branch exists with different history, stop and ask before force-pushing.

---

### Task 2: Expose package binaries and packaged files for external consumers

**TDD scenario:** New feature — full TDD cycle. The package currently exposes only `devtools-qa-runner`; LMS also needs judge and human-report CLIs after submodule removal.

**Files:**
- Create: `/Users/amazon/lunch.cancelled/devtools-qa-runner/test/package-manifest.test.mjs`
- Modify: `/Users/amazon/lunch.cancelled/devtools-qa-runner/package.json`

**Step 1: Write the failing test**

Create `test/package-manifest.test.mjs`:

```js
import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const pkg = JSON.parse(fs.readFileSync(new URL('../package.json', import.meta.url), 'utf8'));

test('package exposes all command-line entrypoints used by consumers', () => {
  assert.equal(pkg.bin['devtools-qa-runner'], 'src/cli.mjs');
  assert.equal(pkg.bin['devtools-qa-runner-judge'], 'judge/cli.mjs');
  assert.equal(pkg.bin['devtools-qa-runner-human-report'], 'report/human-report.mjs');
  assert.equal(pkg.bin['devtools-qa-runner-human-report-html'], 'report/human-report-html.mjs');
});

test('package files include runtime CLI directories', () => {
  assert.ok(pkg.files.includes('src'));
  assert.ok(pkg.files.includes('judge'));
  assert.ok(pkg.files.includes('report'));
  assert.ok(pkg.files.includes('profiles'));
  assert.ok(pkg.files.includes('examples'));
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/amazon/lunch.cancelled/devtools-qa-runner
node --test test/package-manifest.test.mjs
```

Expected: FAIL because `devtools-qa-runner-judge`, `devtools-qa-runner-human-report`, `devtools-qa-runner-human-report-html`, `judge`, and `report` are not yet in `package.json`.

**Step 3: Update `package.json` minimally**

Change the relevant sections to:

```json
{
  "exports": {
    ".": "./src/index.mjs"
  },
  "bin": {
    "devtools-qa-runner": "src/cli.mjs",
    "devtools-qa-runner-judge": "judge/cli.mjs",
    "devtools-qa-runner-human-report": "report/human-report.mjs",
    "devtools-qa-runner-human-report-html": "report/human-report-html.mjs"
  },
  "files": [
    "src",
    "judge",
    "report",
    "profiles",
    "examples",
    "docs",
    "README.md",
    "LICENSE"
  ]
}
```

Keep all other existing package fields unchanged.

**Step 4: Run the package-manifest test to verify it passes**

Run:

```bash
node --test test/package-manifest.test.mjs
```

Expected: PASS.

**Step 5: Run full standalone verification**

Run:

```bash
npm run check
npm test
npm run pack:dry
```

Expected:

```txt
check exits 0
tests pass
npm pack --dry-run lists judge/cli.mjs, report/human-report.mjs, and report/human-report-html.mjs
```

**Step 6: Commit and push**

Run:

```bash
git add package.json test/package-manifest.test.mjs
git commit -m "feat(package): expose runner judge and report CLIs"
git push
```

---

### Task 3: Verify the standalone package installs in a clean consumer project

**TDD scenario:** Modifying tested code — integration verification only. No production code changes unless this task reveals a failure.

**Files:**
- Verify repo: `/Users/amazon/lunch.cancelled/devtools-qa-runner`
- Temporary files only under `mktemp -d`.

**Step 1: Build an actual npm tarball**

Run:

```bash
cd /Users/amazon/lunch.cancelled/devtools-qa-runner
PACK_JSON=$(npm pack --json)
TARBALL=$(node -e "const p=JSON.parse(process.env.PACK_JSON); console.log(p[0].filename)" )
echo "$TARBALL"
```

Expected: prints a tarball such as `devtools-qa-runner-0.1.0.tgz`.

**Step 2: Install into a temporary consumer**

Run:

```bash
TMP=$(mktemp -d)
cd "$TMP"
npm init -y
npm install /Users/amazon/lunch.cancelled/devtools-qa-runner/$TARBALL
```

Expected: install exits 0. Peer dependency warnings are acceptable only if they mention `chrome-devtools-mcp`; install failure is not acceptable.

**Step 3: Verify binaries and runtime files exist**

Run:

```bash
test -x node_modules/.bin/devtools-qa-runner
test -x node_modules/.bin/devtools-qa-runner-judge
test -x node_modules/.bin/devtools-qa-runner-human-report
test -x node_modules/.bin/devtools-qa-runner-human-report-html
test -f node_modules/devtools-qa-runner/judge/cli.mjs
test -f node_modules/devtools-qa-runner/report/human-report.mjs
test -f node_modules/devtools-qa-runner/profiles/lms-chatbot.json
node --check node_modules/devtools-qa-runner/judge/cli.mjs
node --check node_modules/devtools-qa-runner/report/human-report.mjs
node --check node_modules/devtools-qa-runner/report/human-report-html.mjs
```

Expected: all commands exit 0.

**Step 4: Clean generated tarball**

Run:

```bash
cd /Users/amazon/lunch.cancelled/devtools-qa-runner
rm -f "$TARBALL"
git status --short
```

Expected: no tarball remains. Only intentional source changes from earlier tasks should be present; ideally status is clean.

---

### Task 4: Move LMS-specific profiles into `lms-chatbot`

**TDD scenario:** Trivial change — moving static JSON profiles. Verify by JSON parsing and file comparison.

**Files:**
- Create directory: `/Users/amazon/lunch.cancelled/lms-chatbot/qa/devtools-profiles/`
- Create files copied from: `/Users/amazon/lunch.cancelled/lms-chatbot/qa/devtools-qa-runner/profiles/*.json`
- Optional create: `/Users/amazon/lunch.cancelled/lms-chatbot/qa/devtools-profiles/README.md`

**Step 1: Copy profiles before removing the submodule**

Run:

```bash
cd /Users/amazon/lunch.cancelled/lms-chatbot
mkdir -p qa/devtools-profiles
rsync -a qa/devtools-qa-runner/profiles/ qa/devtools-profiles/
```

Expected: these files exist:

```txt
qa/devtools-profiles/lms-chatbot.json
qa/devtools-profiles/lms-conversation.json
qa/devtools-profiles/lms-faq-adversarial.json
qa/devtools-profiles/lms-faq-paraphrase.json
qa/devtools-profiles/lms-faq-smoke.json
qa/devtools-profiles/lms-faq-verification.json
```

**Step 2: Add a short README**

Create `qa/devtools-profiles/README.md`:

```md
# LMS DevTools QA profiles

These profiles are LMS-chatbot-specific inputs for the standalone `devtools-qa-runner` package.

The reusable runner lives outside this repository at:

```txt
/Users/amazon/lunch.cancelled/devtools-qa-runner
```

Do not put runner implementation code in this directory. Put only consumer-owned profiles and fixtures here.
```

**Step 3: Verify profiles parse as JSON**

Run:

```bash
node -e "const fs=require('fs'); for (const f of fs.readdirSync('qa/devtools-profiles').filter(f=>f.endsWith('.json'))) JSON.parse(fs.readFileSync('qa/devtools-profiles/'+f,'utf8')); console.log('profiles ok')"
```

Expected: `profiles ok`.

**Step 4: Commit profile migration**

Run:

```bash
git add qa/devtools-profiles
git commit -m "chore(qa): move LMS devtools profiles into app repo"
```

---

### Task 5: Install standalone runner in `lms-chatbot` and update npm scripts

**TDD scenario:** Modifying tested code — script/config change. Verify through npm install, binary resolution, and existing runner tests.

**Files:**
- Modify: `/Users/amazon/lunch.cancelled/lms-chatbot/package.json`
- Modify: `/Users/amazon/lunch.cancelled/lms-chatbot/package-lock.json`

**Step 1: Update `package.json` scripts and dependency**

In `/Users/amazon/lunch.cancelled/lms-chatbot/package.json`, change scripts to use package binaries and profiles under `qa/devtools-profiles`:

```json
{
  "scripts": {
    "qa:chatbot": "node qa/lms-chatbot-qa/cli.mjs",
    "qa:chatbot:devtools": "node qa/lms-chatbot-devtools-qa/cli.mjs",
    "qa:devtools-runner": "devtools-qa-runner",
    "qa:chatbot:devtools-profile": "devtools-qa-runner --profile qa/devtools-profiles/lms-chatbot.json",
    "qa:devtools-runner:test": "npm --prefix ../devtools-qa-runner test",
    "qa:devtools-runner:check": "npm --prefix ../devtools-qa-runner run check",
    "qa:adversarial": "devtools-qa-runner --profile qa/devtools-profiles/lms-faq-adversarial.json --out reports/faq-adversarial --timeout 180000",
    "qa:adversarial:judge": "devtools-qa-runner-judge --report reports/faq-adversarial",
    "qa:paraphrase": "devtools-qa-runner --profile qa/devtools-profiles/lms-faq-paraphrase.json --out reports/faq-paraphrase --timeout 180000",
    "qa:paraphrase:judge": "devtools-qa-runner-judge --report reports/faq-paraphrase --profile lms-faq-paraphrase --llm",
    "qa:conversation": "devtools-qa-runner --profile qa/devtools-profiles/lms-conversation.json --out reports/conversation --timeout 200000",
    "qa:human-report": "devtools-qa-runner-human-report --report reports/conversation",
    "qa:human-report:html": "devtools-qa-runner-human-report-html --report reports/conversation"
  },
  "devDependencies": {
    "chrome-devtools-mcp": "^1.1.0",
    "devtools-qa-runner": "file:../devtools-qa-runner",
    "playwright": "^1.52.0"
  }
}
```

Preserve any other fields if `package.json` gains them before execution.

**Step 2: Regenerate npm lockfile**

Run:

```bash
cd /Users/amazon/lunch.cancelled/lms-chatbot
npm install
```

Expected: install exits 0 and `package-lock.json` now includes `node_modules/devtools-qa-runner` with a `file:../devtools-qa-runner` resolution.

**Step 3: Verify binary resolution and profiles**

Run:

```bash
test -x node_modules/.bin/devtools-qa-runner
test -x node_modules/.bin/devtools-qa-runner-judge
test -x node_modules/.bin/devtools-qa-runner-human-report
test -x node_modules/.bin/devtools-qa-runner-human-report-html
node -e "const fs=require('fs'); const required=['lms-chatbot','lms-faq-adversarial','lms-faq-paraphrase','lms-conversation']; for (const n of required) { const p='qa/devtools-profiles/'+n+'.json'; if (!fs.existsSync(p)) throw new Error('missing '+p); JSON.parse(fs.readFileSync(p,'utf8')); } console.log('lms profiles ok')"
```

Expected: all commands exit 0 and print `lms profiles ok`.

**Step 4: Run runner package checks through LMS scripts**

Run:

```bash
npm run qa:devtools-runner:check
npm run qa:devtools-runner:test
```

Expected: both exit 0.

**Step 5: Commit LMS package changes**

Run:

```bash
git add package.json package-lock.json
git commit -m "chore(qa): consume standalone devtools qa runner"
```

---

### Task 6: Remove the `qa/devtools-qa-runner` submodule from `lms-chatbot`

**TDD scenario:** Trivial change — repository wiring cleanup. Verify through git submodule status and package scripts.

**Files:**
- Remove gitlink: `/Users/amazon/lunch.cancelled/lms-chatbot/qa/devtools-qa-runner`
- Modify/remove: `/Users/amazon/lunch.cancelled/lms-chatbot/.gitmodules`

**Step 1: Confirm standalone copy is safe before destructive cleanup**

Run:

```bash
test -d /Users/amazon/lunch.cancelled/devtools-qa-runner/.git
test -f /Users/amazon/lunch.cancelled/devtools-qa-runner/package.json
git -C /Users/amazon/lunch.cancelled/devtools-qa-runner status --short
```

Expected: standalone repo exists. If it has uncommitted changes, confirm they are intentional before continuing.

**Step 2: Deinitialize and remove the submodule**

Run:

```bash
cd /Users/amazon/lunch.cancelled/lms-chatbot
git submodule deinit -f qa/devtools-qa-runner
git rm -f qa/devtools-qa-runner
```

Expected: `qa/devtools-qa-runner` is staged for removal as a gitlink, not as thousands of normal files.

**Step 3: Remove `.gitmodules` if it is now empty**

Run:

```bash
if ! git config -f .gitmodules --get-regexp '^submodule\.' >/dev/null 2>&1; then
  rm -f .gitmodules
  git add -u .gitmodules
else
  git add .gitmodules
fi
```

Expected: because this repo currently has only the `qa/devtools-qa-runner` submodule, `.gitmodules` should be removed.

**Step 4: Verify no scripts reference the old submodule path**

Run:

```bash
rg -n "qa/devtools-qa-runner|devtools-qa-runner/src|devtools-qa-runner/judge|devtools-qa-runner/report" package.json AGENT.md docs qa --glob '!qa/devtools-profiles/README.md'
```

Expected: no required runtime script references `qa/devtools-qa-runner`. Historical docs may still mention it; if matches are only archived plans/specs, leave them unless the current `AGENT.md` or README is misleading.

**Step 5: Commit submodule removal**

Run:

```bash
git add -u .gitmodules qa/devtools-qa-runner
git commit -m "chore(qa): remove embedded devtools runner submodule"
```

---

### Task 7: Final integration verification across both repos

**TDD scenario:** Modifying tested code — final verification only.

**Files:**
- Verify standalone repo: `/Users/amazon/lunch.cancelled/devtools-qa-runner`
- Verify consumer repo: `/Users/amazon/lunch.cancelled/lms-chatbot`

**Step 1: Verify standalone runner**

Run:

```bash
cd /Users/amazon/lunch.cancelled/devtools-qa-runner
npm run check
npm test
npm run pack:dry
```

Expected: all commands exit 0; pack dry-run includes `src`, `judge`, `report`, profiles/examples/docs, README, and LICENSE.

**Step 2: Verify LMS dependency and scripts**

Run:

```bash
cd /Users/amazon/lunch.cancelled/lms-chatbot
npm install
npm run qa:devtools-runner:check
npm run qa:devtools-runner:test
```

Expected: all commands exit 0.

**Step 3: Verify non-browser CLIs on existing report artifacts**

Run:

```bash
npm run qa:adversarial:judge
node_modules/.bin/devtools-qa-runner-judge --report reports/faq-paraphrase --profile lms-faq-paraphrase
npm run qa:human-report
npm run qa:human-report:html
```

Expected: commands exit 0. If judge exits 1 because existing reports contain rule failures, inspect output: CLI wiring is still validated if it reads `answers.jsonl` and writes judge artifacts; do not hide real QA failures.

**Step 4: Optional browser smoke test if the LMS app is running**

If the app is available at `http://localhost:8080`, run:

```bash
npm run qa:chatbot:devtools-profile -- --url http://localhost:8080 --timeout 120000
```

Expected: runner starts through the installed package and writes a report under `reports/devtools-qa-runner/...`.

**Step 5: Verify git state in both repos**

Run:

```bash
git -C /Users/amazon/lunch.cancelled/devtools-qa-runner status --short --branch
git -C /Users/amazon/lunch.cancelled/lms-chatbot status --short --branch
git -C /Users/amazon/lunch.cancelled/lms-chatbot submodule status
```

Expected:

```txt
devtools-qa-runner: clean or only intentional generated files ignored
lms-chatbot: clean or only intentional untracked work docs already known
submodule status: no qa/devtools-qa-runner entry
```

**Step 6: Push branches after confirmation**

Run only after the user confirms push target branches:

```bash
git -C /Users/amazon/lunch.cancelled/devtools-qa-runner push
git -C /Users/amazon/lunch.cancelled/lms-chatbot push
```

Expected: both branches are on GitHub. Do not force-push without explicit approval.
