# Profile schema

A profile tells `devtools-qa-runner` how to find elements in Chrome DevTools accessibility snapshots, which scenarios to run, and how to classify quality findings.

## Top-level fields

```json
{
  "name": "my-app",
  "description": "Human readable description",
  "selectors": {},
  "quality": {},
  "scenarios": []
}
```

## Selectors

Selectors match nodes from `chrome-devtools take_snapshot` output.

```json
{
  "role": "textbox",
  "nameIncludes": "Ask anything",
  "excludeNameIncludes": ["Search"]
}
```

Supported selector fields:

- `role`: exact accessibility role match.
- `nameIncludes`: substring match on the accessibility name.
- `excludeNameIncludes`: reject nodes whose name contains any listed string.

Required selectors for chatbot-style profiles:

```json
{
  "chatInput": { "role": "textbox", "nameIncludes": "..." }
}
```

`answerDoneText` is optional. When set, `question` scenarios wait for an extra occurrence of this text to confirm the answer finished; when omitted, they wait only for the submitted text to appear.

Optional consent selectors:

```json
{
  "consentAgreeButton": { "role": "button", "nameIncludes": "Agree" },
  "consentLabelInput": { "role": "textbox", "excludeNameIncludes": ["Ask"] }
}
```

## Scenarios

### `consent`

Finds the consent button, optionally fills a label input, clicks agree, then waits for `selectors.chatInput`.

```json
{
  "type": "consent",
  "name": "consent-flow",
  "label": "qa-user"
}
```

### `question`

Fills `selectors.chatInput`, presses Enter, then waits for the submitted text to appear. If `selectors.answerDoneText` is set, it additionally waits for one more occurrence of that marker (used to detect that the answer finished streaming). When `answerDoneText` is omitted, the scenario waits only for the submitted text — it does not hang.

```json
{
  "type": "question",
  "name": "basic-question",
  "text": "How do I reset my password?",
  "viewport": "390x844x2,mobile,touch"
}
```

### `empty-input`

Attempts to submit empty/blank input and asserts the accessibility tree does not materially change (i.e. no new answer was produced).

`maxNodeDelta` (default `2`) is the number of additional accessibility nodes tolerated after submitting blank input — raise it if the UI legitimately shows an aria-live validation hint on empty submit.

```json
{
  "type": "empty-input",
  "name": "empty-input-guard",
  "text": "   ",
  "waitMs": 500,
  "maxNodeDelta": 2
}
```

### `fill`

Takes a snapshot, finds `target`, fills it with `value`, and optionally presses `submitKey`.

```json
{
  "type": "fill",
  "name": "fill-search",
  "target": { "role": "textbox", "nameIncludes": "Search" },
  "value": "hello world",
  "submitKey": "Enter"
}
```

### `click`

Takes a snapshot, finds `target`, and clicks it.

```json
{
  "type": "click",
  "name": "open-menu",
  "target": { "role": "button", "nameIncludes": "Menu" }
}
```

### `press-key`

Presses a key or key combination.

```json
{
  "type": "press-key",
  "name": "submit",
  "key": "Enter"
}
```

### `wait-for-text`

Polls snapshots until text appears.

```json
{
  "type": "wait-for-text",
  "name": "wait-results",
  "text": "Results",
  "timeoutMs": 10000
}
```

### `screenshot`

Captures a screenshot artifact.

```json
{
  "type": "screenshot",
  "name": "after-submit"
}
```

### `assert-no-console-errors`

Fails the scenario if DevTools reports console messages of type `error`. Use `ignoreTextIncludes` for known noisy messages.

```json
{
  "type": "assert-no-console-errors",
  "name": "no-console-errors",
  "ignoreTextIncludes": ["Failed to load resource"]
}
```

### `assert-no-http-errors`

Fails the scenario if DevTools reports HTTP 4xx/5xx responses. Use `ignoreFavicon404`, `ignoreUrlIncludes`, or `failOn4xx: false` to tune strictness.

```json
{
  "type": "assert-no-http-errors",
  "name": "no-http-errors",
  "ignoreFavicon404": true,
  "ignoreUrlIncludes": ["/analytics"],
  "failOn4xx": true
}
```

## Quality rules

```json
{
  "ignoreSeo": true,
  "ignoreFavicon404": true,
  "lighthouseFailBelow": 0.8,
  "lighthouseWarnBelow": 0.9
}
```

Current quality checks:

- Console errors become warnings.
- HTTP 5xx responses become failures.
- HTTP 4xx responses become warnings unless ignored favicon 404.
- Lighthouse scores below thresholds become warnings/failures.
