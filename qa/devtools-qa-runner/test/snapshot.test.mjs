import test from 'node:test';
import assert from 'node:assert/strict';
import { countTextOccurrences, findBySpec, flatten, hasText } from '../src/core/snapshot.mjs';

const snapshot = {
  role: 'RootWebArea',
  name: 'Test App',
  children: [
    { id: '1', role: 'heading', name: 'Chat' },
    { id: '2', role: 'textbox', name: 'Ask anything' },
    { id: '3', role: 'button', name: 'Send' },
    {
      id: '4',
      role: 'group',
      name: 'Messages',
      children: [
        { id: '5', role: 'StaticText', name: 'How do I start?' },
        { id: '6', role: 'StaticText', name: 'Helpful?' },
      ],
    },
  ],
};

test('flatten returns nested accessibility nodes', () => {
  assert.equal(flatten(snapshot).length, 7);
});

test('findBySpec matches role and name substring', () => {
  assert.equal(findBySpec(snapshot, { role: 'textbox', nameIncludes: 'Ask' })?.id, '2');
  assert.equal(findBySpec(snapshot, { role: 'button', nameIncludes: 'Send' })?.id, '3');
});

test('findBySpec supports excluded name substrings', () => {
  assert.equal(findBySpec(snapshot, {
    role: 'textbox',
    excludeNameIncludes: ['Ask'],
  }), undefined);
});

test('text helpers find and count visible names', () => {
  assert.equal(hasText(snapshot, 'How do I start?'), true);
  assert.equal(hasText(snapshot, 'Missing'), false);
  assert.equal(countTextOccurrences(snapshot, 'Helpful?'), 1);
});
