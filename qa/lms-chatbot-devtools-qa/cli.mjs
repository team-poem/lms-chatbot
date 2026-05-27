#!/usr/bin/env node
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import fs from 'node:fs/promises';
import path from 'node:path';

const execFileAsync = promisify(execFile);
const args = parseArgs(process.argv.slice(2));
const url = args.url || 'http://localhost:8080';
const outDir = path.resolve(args.out || 'reports/lms-chatbot-devtools-qa/latest');
const timeoutMs = Number(args.timeout || 120000);

const report = {
  startedAt: new Date().toISOString(),
  url,
  engine: 'chrome-devtools-cli',
  scenarios: [],
  commands: [],
  consoleMessages: null,
  networkRequests: null,
  lighthouse: null,
  quality: null,
};

async function main() {
  await resetDir(outDir);
  await fs.mkdir(path.join(outDir, 'screenshots'), { recursive: true });
  await fs.mkdir(path.join(outDir, 'snapshots'), { recursive: true });
  await fs.mkdir(path.join(outDir, 'lighthouse'), { recursive: true });

  await stopDevTools();
  try {
    await run('new_page', ['new_page', url, '--timeout', String(timeoutMs)]);

    await scenario('consent-flow', async (s) => {
      let snap = await snapshot('01-before-consent', s);
      const agree = findNode(snap, { role: 'button', nameIncludes: '동의하고 시작' });
      if (agree) {
        const labelBox = findTextboxExcept(snap, ['질문을 입력하십시오']);
        if (labelBox) await run('fill-label', ['fill', labelBox.id, 'qa-devtools']);
        await run('click-agree', ['click', agree.id]);
        await waitForSnapshot((next) => Boolean(findNode(next, { role: 'textbox', nameIncludes: '질문을 입력하십시오' })), 10000);
      }
      snap = await snapshot('02-after-consent', s);
      assert(findNode(snap, { role: 'textbox', nameIncludes: '질문을 입력하십시오' }), 'chat textbox should be visible after consent');
      await screenshot('02-after-consent', s);
    });

    await scenario('basic-question', async (s) => {
      const before = await snapshot('03-basic-before', s);
      const beforeTurns = countUserQuestions(before);
      await askFromSnapshot(before, '퀴즈 출제하는 방법을 알려줘');
      const done = await waitForSnapshot((snap) => countUserQuestions(snap) >= beforeTurns + 1 && hasText(snap, '이 응답이 도움이 되었습니까?'), timeoutMs);
      assert(hasText(done, '퀴즈 출제하는 방법을 알려줘'), 'submitted question should appear in snapshot');
      await snapshot('04-basic-after', s);
      await screenshot('04-basic-after', s);
    });

    await scenario('empty-input-guard', async (s) => {
      const before = await snapshot('05-empty-before', s);
      const beforeTurns = countUserQuestions(before);
      await askFromSnapshot(before, '   ');
      await sleep(500);
      const after = await snapshot('06-empty-after', s);
      assert(countUserQuestions(after) === beforeTurns, `empty input should not create a turn: before=${beforeTurns}, after=${countUserQuestions(after)}`);
      await screenshot('06-empty-after', s);
    });

    await scenario('mobile-basic-question', async (s) => {
      await run('emulate-mobile', ['emulate', '--viewport', '390x844x2,mobile,touch']);
      const before = await snapshot('07-mobile-before', s);
      const beforeTurns = countUserQuestions(before);
      await askFromSnapshot(before, '모바일에서 출석 확인 방법 알려줘');
      const done = await waitForSnapshot((snap) => countUserQuestions(snap) >= beforeTurns + 1 && hasText(snap, '이 응답이 도움이 되었습니까?'), timeoutMs);
      assert(hasText(done, '모바일에서 출석 확인 방법 알려줘'), 'mobile question should appear in snapshot');
      await snapshot('08-mobile-after', s);
      await screenshot('08-mobile-after', s);
    });

    report.consoleMessages = await run('list_console_messages', ['list_console_messages', '--includePreservedMessages']);
    report.networkRequests = await run('list_network_requests', ['list_network_requests', '--includePreservedRequests']);
    report.lighthouse = await run('lighthouse_audit', ['lighthouse_audit', '--mode', 'snapshot', '--device', 'desktop', '--outputDirPath', path.join(outDir, 'lighthouse')]);
    report.quality = analyzeQuality(report);
  } finally {
    await stopDevTools();
  }

  await writeArtifacts();
  const failed = report.scenarios.some((s) => s.status === 'fail') || report.quality?.status === 'fail';
  console.log(`DevTools-only QA report: ${path.join(outDir, 'qa-report.md')}`);
  process.exitCode = failed ? 1 : 0;
}

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const token = argv[i];
    if (!token.startsWith('--')) continue;
    const key = token.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith('--')) out[key] = true;
    else out[key] = argv[++i];
  }
  return out;
}

async function run(name, cliArgs) {
  const started = Date.now();
  try {
    const { stdout, stderr } = await execFileAsync('npx', ['chrome-devtools', ...cliArgs, '--output-format=json'], {
      cwd: process.cwd(),
      timeout: Math.max(timeoutMs, 60000),
      env: {
        ...process.env,
        CI: '1',
        CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS: '1',
        CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS: '1',
      },
    });
    const parsed = parseJsonOutput(stdout);
    report.commands.push({ name, status: 'pass', durationMs: Date.now() - started, stderr: stderr.trim() || null });
    return parsed;
  } catch (err) {
    report.commands.push({ name, status: 'fail', durationMs: Date.now() - started, error: err.message, stdout: err.stdout || '', stderr: err.stderr || '' });
    throw err;
  }
}

async function stopDevTools() {
  await execFileAsync('npx', ['chrome-devtools', 'stop'], { timeout: 10000 }).catch(() => {});
}

async function scenario(name, fn) {
  const item = { name, status: 'pass', durationMs: 0, screenshots: [], snapshots: [], error: null };
  const started = Date.now();
  try {
    await fn(item);
  } catch (err) {
    item.status = 'fail';
    item.error = err?.stack || err?.message || String(err);
  } finally {
    item.durationMs = Date.now() - started;
    report.scenarios.push(item);
  }
}

async function snapshot(name, scenarioItem = null) {
  const rel = `snapshots/${name}.json`;
  const result = await run(`snapshot-${name}`, ['take_snapshot']);
  await fs.writeFile(path.join(outDir, rel), JSON.stringify(result, null, 2));
  if (scenarioItem) scenarioItem.snapshots.push(rel);
  return result.snapshot || result;
}

async function screenshot(name, scenarioItem = null) {
  const rel = `screenshots/${name}.png`;
  await run(`screenshot-${name}`, ['take_screenshot', '--filePath', path.join(outDir, rel), '--fullPage']);
  if (scenarioItem) scenarioItem.screenshots.push(rel);
}

async function askFromSnapshot(snap, text) {
  const input = findNode(snap, { role: 'textbox', nameIncludes: '질문을 입력하십시오' });
  assert(input, 'chat textbox not found');
  await run('fill-chat-input', ['fill', input.id, text]);
  await run('press-enter', ['press_key', 'Enter']);
}

async function waitForSnapshot(predicate, timeout) {
  const deadline = Date.now() + timeout;
  let last;
  while (Date.now() < deadline) {
    last = await snapshot(`poll-${Date.now()}`);
    if (predicate(last)) return last;
    await sleep(1000);
  }
  throw new Error('timeout while waiting for desired snapshot state');
}

function findTextboxExcept(root, excludedNames) {
  return flatten(root).find((n) => n.role === 'textbox' && !excludedNames.includes(n.name || ''));
}

function findNode(root, query) {
  return flatten(root).find((node) => {
    if (query.role && node.role !== query.role) return false;
    if (query.nameIncludes && !String(node.name || '').includes(query.nameIncludes)) return false;
    return true;
  });
}

function flatten(root) {
  const nodes = [];
  const visit = (node) => {
    if (!node || typeof node !== 'object') return;
    nodes.push(node);
    for (const child of node.children || []) visit(child);
  };
  visit(root);
  return nodes;
}

function hasText(root, text) {
  return flatten(root).some((node) => String(node.name || '').includes(text));
}

function countUserQuestions(root) {
  return flatten(root).filter((node) => node.role === 'StaticText' && /질문|퀴즈|모바일|피어리뷰|출석|빠른/.test(node.name || '')).length;
}

function analyzeQuality(r) {
  const failures = [];
  const warnings = [];
  for (const msg of r.consoleMessages?.consoleMessages || []) {
    if (msg.type === 'error') warnings.push(`Console error/warning: ${msg.text}`);
  }
  for (const req of r.networkRequests?.networkRequests || []) {
    const status = Number(req.status);
    if (status >= 500) failures.push(`${req.method} ${req.url} -> ${req.status}`);
    else if (status >= 400 && !String(req.url).endsWith('/favicon.ico')) warnings.push(`${req.method} ${req.url} -> ${req.status}`);
  }
  for (const score of r.lighthouse?.lighthouseResult?.summary?.scores || []) {
    if (score.id === 'seo') continue;
    if (typeof score.score === 'number' && score.score < 0.8) failures.push(`Low Lighthouse ${score.title}: ${score.score}`);
    else if (typeof score.score === 'number' && score.score < 0.9) warnings.push(`Borderline Lighthouse ${score.title}: ${score.score}`);
  }
  return { status: failures.length ? 'fail' : warnings.length ? 'warning' : 'pass', failures, warnings };
}

async function writeArtifacts() {
  await fs.writeFile(path.join(outDir, 'chrome-devtools-qa.json'), JSON.stringify(report, null, 2));
  await fs.writeFile(path.join(outDir, 'qa-report.md'), renderMarkdown(report));
}

function renderMarkdown(r) {
  const failed = r.scenarios.filter((s) => s.status === 'fail');
  const scores = r.lighthouse?.lighthouseResult?.summary?.scores || [];
  return `# LMS Chatbot DevTools-only QA Report

## Summary

- URL: ${r.url}
- Started: ${r.startedAt}
- Engine: ${r.engine}
- Result: ${failed.length || r.quality?.status === 'fail' ? 'FAIL' : 'PASS'}
- Scenarios: ${r.scenarios.length - failed.length} passed / ${failed.length} failed / ${r.scenarios.length} total
- Quality: ${r.quality?.status || 'unknown'}

## Scenario Results

${r.scenarios.map(renderScenario).join('\n\n')}

## Lighthouse Scores

${scores.length ? scores.map((s) => `- ${s.title}: ${s.score}`).join('\n') : '(not run)'}

## Quality Findings

${codeBlock(JSON.stringify(r.quality, null, 2))}

## Console Messages

${codeBlock(JSON.stringify(r.consoleMessages?.consoleMessages || [], null, 2))}

## Network Requests

${codeBlock(JSON.stringify(r.networkRequests?.networkRequests || [], null, 2))}

## DevTools Commands

${codeBlock(JSON.stringify(r.commands, null, 2))}

## Reproduction

\`\`\`bash
npm run qa:chatbot:devtools -- --url ${r.url} --timeout ${timeoutMs}
\`\`\`
`;
}

function renderScenario(s) {
  return `### ${s.name}

- Status: ${s.status.toUpperCase()}
- Duration: ${s.durationMs}ms
- Screenshots: ${s.screenshots.length ? s.screenshots.map((p) => `\`${p}\``).join(', ') : '(none)'}
- Snapshots: ${s.snapshots.length ? s.snapshots.map((p) => `\`${p}\``).join(', ') : '(none)'}
${s.error ? `- Error:\n\n${codeBlock(s.error)}` : ''}`;
}

function parseJsonOutput(stdout) {
  const lines = stdout.split('\n').map((line) => line.trim()).filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i--) {
    if (!lines[i].startsWith('{') && !lines[i].startsWith('[')) continue;
    try { return JSON.parse(lines.slice(i).join('\n')); } catch {}
  }
  return { raw: stdout };
}

function codeBlock(text) { return `\`\`\`\n${text || '[]'}\n\`\`\``; }
function assert(condition, message) { if (!condition) throw new Error(message); }
function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }
async function resetDir(dir) { await fs.rm(dir, { recursive: true, force: true }); await fs.mkdir(dir, { recursive: true }); }

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
