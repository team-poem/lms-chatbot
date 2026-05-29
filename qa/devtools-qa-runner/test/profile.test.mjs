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

test('validateProfile requires chatInput selector for chatbot scenarios', () => {
  assert.throws(() => validateProfile({
    name: 'missing-chat-input',
    selectors: {},
    scenarios: [{ type: 'question' }],
  }), /selectors\.chatInput is required for chatbot scenarios/);
});


test('validateProfile accepts generic scenarios without chatInput selector', () => {
  assert.doesNotThrow(() => validateProfile({
    name: 'generic',
    scenarios: [
      { type: 'fill', target: { role: 'textbox', nameIncludes: 'Search' }, value: 'hello' },
      { type: 'press-key', key: 'Enter' },
      { type: 'wait-for-text', text: 'Results' },
      { type: 'screenshot' },
      { type: 'assert-no-console-errors' },
      { type: 'assert-no-http-errors' },
    ],
  }));
});


test('validateProfile validates required generic scenario fields', () => {
  assert.throws(() => validateProfile({ name: 'bad-fill', scenarios: [{ type: 'fill' }] }), /fill requires target/);
  assert.throws(() => validateProfile({ name: 'bad-click', scenarios: [{ type: 'click' }] }), /click requires target/);
  assert.throws(() => validateProfile({ name: 'bad-key', scenarios: [{ type: 'press-key' }] }), /press-key requires key/);
  assert.throws(() => validateProfile({ name: 'bad-wait', scenarios: [{ type: 'wait-for-text' }] }), /wait-for-text requires text/);
});

test('validateProfile rejects unsupported scenario types', () => {
  assert.throws(() => validateProfile({
    name: 'bad-scenario',
    selectors: { chatInput: { role: 'textbox' } },
    scenarios: [{ type: 'click-random' }],
  }), /unsupported scenario type/);
});
