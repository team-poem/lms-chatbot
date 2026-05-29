# devtools-qa-runner

Profile-driven QA runner powered by Chrome DevTools for Agents CLI.

This directory is structured so it can later be extracted into a standalone GitHub repository named `devtools-qa-runner`.

## What it does

- Drives Chrome through `chrome-devtools` CLI from `chrome-devtools-mcp`.
- Uses accessibility snapshots to find elements by role/name.
- Runs profile-defined QA scenarios.
- Collects screenshots, snapshots, console messages, network requests, and Lighthouse snapshot audit.
- Emits a Markdown report and a JSON evidence bundle.

## Run inside this repository

```bash
npm run qa:devtools-runner -- \
  --url https://121.145.133.68.sslip.io \
  --profile qa/devtools-qa-runner/profiles/lms-chatbot.json \
  --timeout 120000
```

Convenience alias for the bundled LMS chatbot profile:

```bash
npm run qa:chatbot:devtools-profile -- \
  --url https://121.145.133.68.sslip.io \
  --timeout 120000
```

## Future standalone usage

After extraction to its own repo/package:

```bash
npm install
npm run check
npm test
node src/cli.mjs \
  --url https://example.com \
  --profile examples/simple-chat.profile.json \
  --timeout 120000
```

If published later, the bin name is planned as:

```bash
npx devtools-qa-runner \
  --url https://example.com \
  --profile examples/simple-chat.profile.json \
  --timeout 120000
```

## Profile

Profiles define selectors, quality rules, and scenarios. See:

- `profiles/lms-chatbot.json`
- `examples/simple-chat.profile.json`
- `examples/generic-page.profile.json`
- `docs/profile-schema.md`
- `docs/github-actions.md`

Supported scenario types in this prototype:

- Chatbot-oriented: `consent`, `question`, `empty-input`
- Generic primitives: `click`, `fill`, `press-key`, `wait-for-text`, `screenshot`

## Development checks

Inside this monorepo:

```bash
npm --prefix qa/devtools-qa-runner run check
npm --prefix qa/devtools-qa-runner test
npm --prefix qa/devtools-qa-runner run pack:dry
```

After extraction into a standalone repo:

```bash
npm run check
npm test
npm run pack:dry
```

## Output

```txt
reports/devtools-qa-runner/<profile-name>/latest/
├── qa-report.md
├── devtools-qa-runner.json
├── screenshots/
├── snapshots/
└── lighthouse/
```

## Source layout

```txt
src/
├── cli.mjs
├── core/
│   ├── args.mjs
│   ├── artifacts.mjs
│   ├── devtools-client.mjs
│   ├── profile.mjs
│   ├── quality.mjs
│   ├── reporter.mjs
│   ├── runner.mjs
│   ├── snapshot.mjs
│   └── utils.mjs
└── scenarios/
    └── chatbot.mjs
```

## Extraction plan

1. Keep this package under `qa/devtools-qa-runner` until stable.
2. Add more profile examples and scenario types.
3. Add tests for profile validation and snapshot matching.
4. Add npm `bin` entry in the standalone package.
5. Move to standalone repo `devtools-qa-runner`.
