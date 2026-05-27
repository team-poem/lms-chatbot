# GitHub Actions example

This is a future standalone-repo CI example for `devtools-qa-runner`.

## Unit checks only

```yaml
name: ci

on:
  pull_request:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
      - run: npm ci
      - run: npm run check
      - run: npm test
```

## Smoke test against a deployed URL

Use this when the target app is reachable from GitHub-hosted runners.

```yaml
name: smoke

on:
  workflow_dispatch:
    inputs:
      url:
        description: Target URL
        required: true
        type: string

jobs:
  devtools-smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
      - run: npm ci
      - name: Run DevTools QA
        run: |
          npx devtools-qa-runner \
            --url "${{ inputs.url }}" \
            --profile examples/simple-chat.profile.json \
            --timeout 120000
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: devtools-qa-report
          path: reports/
```

## Notes

- `chrome-devtools-mcp` disables usage statistics automatically when `CI=1` is set.
- For private/staging URLs, prefer self-hosted runners or run this tool from a deployment job inside the same network.
- Upload `reports/` as an artifact even on failure so screenshots, snapshots, and Lighthouse reports remain inspectable.
