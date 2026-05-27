import test from 'node:test';
import assert from 'node:assert/strict';
import { validateProfile } from '../src/core/profile.mjs';

test('validateProfile accepts minimal chatbot profile', () => {
  assert.doesNotThrow(() => validateProfile({
    name: 'minimal',
    selectors: {
      chatInput: { role: 'textbox', nameIncludes: 'Ask' },
      answerDoneText: 'Done',
    },
    scenarios: [
      { type: 'question', name: 'ask', text: 'Hello' },
    ],
  }));
});

test('validateProfile requires profile name', () => {
  assert.throws(() => validateProfile({
    selectors: { chatInput: { role: 'textbox' } },
    scenarios: [{ type: 'question' }],
  }), /profile\.name is required/);
});

test('validateProfile requires chatInput selector', () => {
  assert.throws(() => validateProfile({
    name: 'missing-chat-input',
    selectors: {},
    scenarios: [{ type: 'question' }],
  }), /selectors\.chatInput is required/);
});

test('validateProfile rejects unsupported scenario types', () => {
  assert.throws(() => validateProfile({
    name: 'bad-scenario',
    selectors: { chatInput: { role: 'textbox' } },
    scenarios: [{ type: 'click-random' }],
  }), /unsupported scenario type/);
});
