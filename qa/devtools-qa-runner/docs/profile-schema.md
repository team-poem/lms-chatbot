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
  "chatInput": { "role": "textbox", "nameIncludes": "..." },
  "answerDoneText": "..."
}
```

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

Fills `selectors.chatInput`, presses Enter, waits for submitted text and an additional `selectors.answerDoneText` occurrence.

```json
{
  "type": "question",
  "name": "basic-question",
  "text": "How do I reset my password?",
  "viewport": "390x844x2,mobile,touch"
}
```

### `empty-input`

Attempts to submit empty/blank input and asserts the accessibility tree does not materially change.

```json
{
  "type": "empty-input",
  "name": "empty-input-guard",
  "text": "   ",
  "waitMs": 500
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
