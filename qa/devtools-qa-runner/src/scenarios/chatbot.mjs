import { assert, sleep } from '../core/utils.mjs';
import { countTextOccurrences, findBySpec, flatten, hasText } from '../core/snapshot.mjs';

export async function runScenarioSpec({ spec, item, profile, client, artifacts, timeoutMs }) {
  if (spec.viewport) await client.run(`emulate-${spec.name}`, ['emulate', '--viewport', spec.viewport]);
  if (spec.type === 'consent') return runConsentScenario({ spec, item, profile, client, artifacts });
  if (spec.type === 'question') return runQuestionScenario({ spec, item, profile, client, artifacts, timeoutMs });
  if (spec.type === 'empty-input') return runEmptyInputScenario({ spec, item, profile, client, artifacts });
  throw new Error(`unsupported scenario type: ${spec.type}`);
}

async function runConsentScenario({ spec, item, profile, client, artifacts }) {
  let snap = await artifacts.snapshot(`${item.name}-before`, item);
  const agree = findBySpec(snap, profile.selectors?.consentAgreeButton);
  if (agree) {
    const labelBox = findBySpec(snap, profile.selectors?.consentLabelInput);
    if (labelBox && spec.label) await client.run('fill-consent-label', ['fill', labelBox.id, spec.label]);
    await client.run('click-consent-agree', ['click', agree.id]);
    await artifacts.waitForSnapshot((next) => Boolean(findBySpec(next, profile.selectors?.chatInput)), spec.timeoutMs || 10000);
  }
  snap = await artifacts.snapshot(`${item.name}-after`, item);
  assert(findBySpec(snap, profile.selectors?.chatInput), 'chat input should be visible after consent');
  await artifacts.screenshot(`${item.name}-after`, item);
}

async function runQuestionScenario({ spec, item, profile, client, artifacts, timeoutMs }) {
  const before = await artifacts.snapshot(`${item.name}-before`, item);
  const answerDoneText = profile.selectors?.answerDoneText || '';
  const beforeCount = countTextOccurrences(before, answerDoneText);
  await askFromSnapshot({ snap: before, text: spec.text || '', profile, client });
  const done = await artifacts.waitForSnapshot((snap) => {
    if (!hasText(snap, spec.text || '')) return false;
    // When no answerDoneText marker is configured, degrade to waiting only for
    // the submitted text. countTextOccurrences('') is always 0, so requiring the
    // marker here would otherwise guarantee a timeout.
    if (!answerDoneText) return true;
    return countTextOccurrences(snap, answerDoneText) >= beforeCount + 1;
  }, spec.timeoutMs || timeoutMs);
  assert(hasText(done, spec.text || ''), 'submitted text should appear in snapshot');
  await artifacts.snapshot(`${item.name}-after`, item);
  await artifacts.screenshot(`${item.name}-after`, item);
}

async function runEmptyInputScenario({ spec, item, profile, client, artifacts }) {
  const before = await artifacts.snapshot(`${item.name}-before`, item);
  const beforeTextCount = flatten(before).length;
  await askFromSnapshot({ snap: before, text: spec.text || '   ', profile, client });
  await sleep(spec.waitMs || 500);
  const after = await artifacts.snapshot(`${item.name}-after`, item);
  // Empty input should not produce a new answer. A few extra nodes (e.g. an
  // aria-live validation hint) are tolerated; tune via spec.maxNodeDelta.
  const maxNodeDelta = Number.isInteger(spec.maxNodeDelta) ? spec.maxNodeDelta : 2;
  assert(
    flatten(after).length <= beforeTextCount + maxNodeDelta,
    `empty input should not materially change the accessibility tree (added ${flatten(after).length - beforeTextCount} nodes, allowed ${maxNodeDelta})`,
  );
  await artifacts.screenshot(`${item.name}-after`, item);
}

async function askFromSnapshot({ snap, text, profile, client }) {
  const input = findBySpec(snap, profile.selectors?.chatInput);
  assert(input, 'chat input not found');
  await client.run('fill-chat-input', ['fill', input.id, text]);
  await client.run('press-enter', ['press_key', 'Enter']);
}
