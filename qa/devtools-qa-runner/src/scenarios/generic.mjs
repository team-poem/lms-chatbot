import { assert } from '../core/utils.mjs';
import { findBySpec, hasText } from '../core/snapshot.mjs';

export const genericScenarioTypes = [
  'click',
  'fill',
  'press-key',
  'wait-for-text',
  'screenshot',
  'assert-no-console-errors',
  'assert-no-http-errors',
];

export async function runGenericScenarioSpec({ spec, item, client, artifacts, timeoutMs }) {
  if (spec.viewport) await client.run(`emulate-${spec.name || spec.type}`, ['emulate', '--viewport', spec.viewport]);
  if (spec.type === 'click') return clickScenario({ spec, item, client, artifacts });
  if (spec.type === 'fill') return fillScenario({ spec, item, client, artifacts });
  if (spec.type === 'press-key') return pressKeyScenario({ spec, client });
  if (spec.type === 'wait-for-text') return waitForTextScenario({ spec, item, artifacts, timeoutMs });
  if (spec.type === 'screenshot') return screenshotScenario({ spec, item, artifacts });
  if (spec.type === 'assert-no-console-errors') return assertNoConsoleErrorsScenario({ spec, item, client });
  if (spec.type === 'assert-no-http-errors') return assertNoHttpErrorsScenario({ spec, item, client });
  throw new Error(`unsupported generic scenario type: ${spec.type}`);
}

async function clickScenario({ spec, item, client, artifacts }) {
  const snap = await artifacts.snapshot(`${item.name}-before`, item);
  const node = findBySpec(snap, spec.target);
  assert(node, `click target not found: ${JSON.stringify(spec.target)}`);
  await client.run(`click-${item.name}`, ['click', node.id]);
  if (spec.screenshot !== false) await artifacts.screenshot(`${item.name}-after`, item);
}

async function fillScenario({ spec, item, client, artifacts }) {
  const snap = await artifacts.snapshot(`${item.name}-before`, item);
  const node = findBySpec(snap, spec.target);
  assert(node, `fill target not found: ${JSON.stringify(spec.target)}`);
  await client.run(`fill-${item.name}`, ['fill', node.id, spec.value || '']);
  if (spec.submitKey) await client.run(`submit-${item.name}`, ['press_key', spec.submitKey]);
  if (spec.screenshot) await artifacts.screenshot(`${item.name}-after`, item);
}

async function pressKeyScenario({ spec, client }) {
  assert(spec.key, 'press-key scenario requires key');
  await client.run(`press-${spec.name || spec.key}`, ['press_key', spec.key]);
}

async function waitForTextScenario({ spec, item, artifacts, timeoutMs }) {
  assert(spec.text, 'wait-for-text scenario requires text');
  const snap = await artifacts.waitForSnapshot((next) => hasText(next, spec.text), spec.timeoutMs || timeoutMs);
  assert(hasText(snap, spec.text), `text not found: ${spec.text}`);
  await artifacts.snapshot(`${item.name}-after`, item);
  if (spec.screenshot !== false) await artifacts.screenshot(`${item.name}-after`, item);
}

async function screenshotScenario({ spec, item, artifacts }) {
  await artifacts.screenshot(spec.fileName || `${item.name}`, item);
}

async function assertNoConsoleErrorsScenario({ spec, item, client }) {
  const result = await client.run(`console-${item.name}`, ['list_console_messages', '--includePreservedMessages']);
  const messages = result.consoleMessages || [];
  const errors = messages.filter((message) => message.type === 'error' && !isIgnored(message.text || '', spec.ignoreTextIncludes || []));
  item.evidence = { ...(item.evidence || {}), consoleErrors: errors };
  assert(errors.length === 0, `console errors found: ${errors.map((message) => message.text).join(' | ')}`);
}

async function assertNoHttpErrorsScenario({ spec, item, client }) {
  const result = await client.run(`network-${item.name}`, ['list_network_requests', '--includePreservedRequests']);
  const requests = result.networkRequests || [];
  const errors = requests.filter((request) => isHttpError(request, spec));
  item.evidence = { ...(item.evidence || {}), httpErrors: errors };
  assert(errors.length === 0, `HTTP errors found: ${errors.map((request) => `${request.method} ${request.url} -> ${request.status}`).join(' | ')}`);
}

function isIgnored(text, patterns) {
  return patterns.some((pattern) => text.includes(pattern));
}

function isHttpError(request, spec) {
  const status = Number(request.status);
  if (!status || status < 400) return false;
  const url = String(request.url || '');
  if (spec.ignoreFavicon404 && status === 404 && url.endsWith('/favicon.ico')) return false;
  if ((spec.ignoreUrlIncludes || []).some((part) => url.includes(part))) return false;
  if (spec.failOn4xx === false && status < 500) return false;
  return true;
}
