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
  const beforeCount = countTextOccurrences(before, profile.selectors?.answerDoneText || '');
  await askFromSnapshot({ snap: before, text: spec.text || '', profile, client });
  const done = await artifacts.waitForSnapshot((snap) => {
    return hasText(snap, spec.text || '') && countTextOccurrences(snap, profile.selectors?.answerDoneText || '') >= beforeCount + 1;
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
  assert(flatten(after).length <= beforeTextCount + 2, 'empty input should not materially change the accessibility tree');
  await artifacts.screenshot(`${item.name}-after`, item);
}

async function askFromSnapshot({ snap, text, profile, client }) {
  const input = findBySpec(snap, profile.selectors?.chatInput);
  assert(input, 'chat input not found');
  await client.run('fill-chat-input', ['fill', input.id, text]);
  await client.run('press-enter', ['press_key', 'Enter']);
}
