# devtools-qa-runner

Reusable Chrome DevTools for Agents based QA runner prototype.

This package shape is intended to be extracted into a standalone GitHub repository named `devtools-qa-runner` after it stabilizes inside this project.

## What it does

- Drives Chrome through `chrome-devtools` CLI from `chrome-devtools-mcp`.
- Uses accessibility snapshots to find elements by role/name.
- Runs profile-defined QA scenarios.
- Collects screenshots, snapshots, console messages, network requests, and Lighthouse snapshot audit.
- Emits a Markdown report.

## Run

```bash
npm run qa:devtools-runner -- \
  --url https://121.145.133.68.sslip.io \
  --profile qa/devtools-qa-runner/profiles/lms-chatbot.json \
  --timeout 120000
```

## Profile

Profiles define selectors, quality rules, and scenarios. See:

```txt
qa/devtools-qa-runner/profiles/lms-chatbot.json
```

Supported scenario types in this prototype:

- `consent`
- `question`
- `empty-input`

## Output

```txt
reports/devtools-qa-runner/<profile-name>/latest/
├── qa-report.md
├── devtools-qa-runner.json
├── screenshots/
├── snapshots/
└── lighthouse/
```

## Extraction plan

1. Keep this package under `qa/devtools-qa-runner` until stable.
2. Add more profile examples.
3. Split runner/reporter/devtools client into modules.
4. Add npm `bin` entry.
5. Move to standalone repo `devtools-qa-runner`.
