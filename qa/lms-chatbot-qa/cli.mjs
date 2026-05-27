#!/usr/bin/env node
import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

const args = parseArgs(process.argv.slice(2));
const url = args.url || 'http://localhost:8080';
const outDir = path.resolve(args.out || 'reports/lms-chatbot-qa/latest');
const mockChat = Boolean(args['mock-chat']);
const headed = Boolean(args.headed);
const timeoutMs = Number(args.timeout || 30000);
const devtools = Boolean(args.devtools);

const evidence = {
  startedAt: new Date().toISOString(),
  url,
  mockChat,
  devtools,
  console: [],
  pageErrors: [],
  requestFailures: [],
  badResponses: [],
  scenarios: [],
  chromeDevTools: null,
};

async function main() {
  await resetDir(outDir);
  await fs.mkdir(path.join(outDir, 'screenshots'), { recursive: true });

  const browser = await chromium.launch({ headless: !headed });
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await context.newPage();
    page.setDefaultTimeout(timeoutMs);
    page.setDefaultNavigationTimeout(timeoutMs);
    attachObservers(page, evidence);
    if (mockChat) await installMockRoutes(page);

    await step(evidence, 'desktop-consent', async (s) => {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: timeoutMs });
      await acceptConsent(page);
      await screenshot(page, s, '01-desktop-consent');
      assert(await page.locator('#q').isEnabled(), 'question input should be enabled after consent');
    });
    if (evidence.scenarios.at(-1)?.status === 'fail') {
      await writeArtifacts(evidence);
      console.log(`QA report: ${path.join(outDir, 'qa-report.md')}`);
      process.exitCode = 1;
      return;
    }

    await step(evidence, 'basic-question', async (s) => {
      const before = await turnCount(page);
      await ask(page, '퀴즈 출제하는 방법을 알려줘');
      await waitForTurnComplete(page, before + 1, timeoutMs);
      await screenshot(page, s, '02-basic-question');
      await assertLastAnswerNonEmpty(page);
    });

    await step(evidence, 'empty-input-guard', async (s) => {
      const before = await turnCount(page);
      await page.locator('#q').fill('   ');
      await page.locator('#form').evaluate((form) => form.requestSubmit());
      await page.waitForTimeout(400);
      await screenshot(page, s, '03-empty-input');
      const after = await turnCount(page);
      assert(after === before, `empty input should not create a turn: before=${before}, after=${after}`);
    });

    await step(evidence, 'long-input', async (s) => {
      const before = await turnCount(page);
      const longQuestion = '피어리뷰 과제 설정 방법을 자세히 알려줘. '.repeat(80);
      await ask(page, longQuestion);
      await waitForTurnComplete(page, before + 1, timeoutMs);
      await screenshot(page, s, '04-long-input');
      await assertLastAnswerNonEmpty(page);
    });

    await step(evidence, 'rapid-input', async (s) => {
      const before = await turnCount(page);
      await page.locator('#q').fill('첫 번째 빠른 질문');
      await page.keyboard.press('Enter');
      await page.locator('#q').fill('두 번째 빠른 질문');
      await page.keyboard.press('Enter');
      await page.locator('#q').fill('세 번째 빠른 질문');
      await page.keyboard.press('Enter');
      await waitForTurnComplete(page, before + 3, timeoutMs);
      await screenshot(page, s, '05-rapid-input');
      const after = await turnCount(page);
      assert(after >= before + 3, `rapid input should create 3 turns: before=${before}, after=${after}`);
    });

    await step(evidence, 'mobile-basic-question', async (s) => {
      await page.setViewportSize({ width: 390, height: 844 });
      const before = await turnCount(page);
      await ask(page, '모바일에서 출석 확인 방법 알려줘');
      await waitForTurnComplete(page, before + 1, timeoutMs);
      await screenshot(page, s, '06-mobile-basic');
      const box = await page.locator('.input').boundingBox();
      assert(box && box.x >= -1 && box.x + box.width <= 391, 'mobile input row should stay within viewport width');
      await assertLastAnswerNonEmpty(page);
    });

    if (devtools) {
      evidence.chromeDevTools = await runChromeDevToolsAudit(url, outDir, timeoutMs);
    }

    await writeArtifacts(evidence);
    const failed = evidence.scenarios.filter((s) => s.status === 'fail').length;
    console.log(`QA report: ${path.join(outDir, 'qa-report.md')}`);
    process.exitCode = failed ? 1 : 0;
  } finally {
    await browser.close();
  }
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

async function resetDir(dir) {
  await fs.rm(dir, { recursive: true, force: true });
  await fs.mkdir(dir, { recursive: true });
}

function attachObservers(page, target) {
  page.on('console', (msg) => {
    if (msg.type() === 'error') target.console.push({ type: msg.type(), text: msg.text(), location: msg.location() });
  });
  page.on('pageerror', (err) => target.pageErrors.push({ message: err.message, stack: err.stack }));
  page.on('requestfailed', (req) => target.requestFailures.push({ url: req.url(), method: req.method(), failure: req.failure()?.errorText }));
  page.on('response', (res) => {
    if (res.status() >= 400) target.badResponses.push({ url: res.url(), status: res.status(), statusText: res.statusText() });
  });
}

async function runChromeDevToolsAudit(targetUrl, targetOutDir, timeout) {
  const devtoolsDir = path.join(targetOutDir, 'chrome-devtools');
  await fs.mkdir(devtoolsDir, { recursive: true });
  const result = {
    status: 'pass',
    startedAt: new Date().toISOString(),
    commands: [],
    files: {
      snapshot: 'chrome-devtools/snapshot.txt',
      screenshot: 'chrome-devtools/screenshot.png',
      lighthouseDir: 'chrome-devtools/lighthouse',
    },
    consoleMessages: null,
    networkRequests: null,
    lighthouse: null,
    error: null,
  };

  const run = async (name, cliArgs) => {
    const started = Date.now();
    try {
      const { stdout, stderr } = await execFileAsync('npx', ['chrome-devtools', ...cliArgs, '--output-format=json'], {
        cwd: process.cwd(),
        timeout: Math.max(timeout, 60000),
        env: {
          ...process.env,
          CI: '1',
          CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS: '1',
          CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS: '1',
        },
      });
      const parsed = parseJsonOutput(stdout);
      result.commands.push({ name, status: 'pass', durationMs: Date.now() - started, stderr: stderr.trim() || null });
      return parsed;
    } catch (err) {
      result.status = 'fail';
      result.commands.push({
        name,
        status: 'fail',
        durationMs: Date.now() - started,
        error: err?.message || String(err),
        stdout: err?.stdout || '',
        stderr: err?.stderr || '',
      });
      throw err;
    }
  };

  try {
    await execFileAsync('npx', ['chrome-devtools', 'stop'], { timeout: 10000 }).catch(() => {});
    await run('new_page', ['new_page', targetUrl, '--timeout', String(timeout)]);
    result.consentState = await run('accept_consent', [
      'evaluate_script',
      `async () => {
        const modal = document.querySelector('#modal');
        if (modal && getComputedStyle(modal).display !== 'none') {
          const label = document.querySelector('#ulabel');
          if (label) label.value = 'qa-devtools';
          document.querySelector('#agree')?.click();
          await new Promise((resolve) => setTimeout(resolve, 1000));
        }
        const input = document.querySelector('#q');
        const modalAfter = document.querySelector('#modal');
        return {
          inputEnabled: Boolean(input && !input.disabled),
          modalDisplay: modalAfter ? getComputedStyle(modalAfter).display : null,
          turnCount: document.querySelectorAll('.turn').length,
        };
      }`,
    ]);
    result.consoleMessages = await run('list_console_messages', ['list_console_messages', '--includePreservedMessages']);
    result.networkRequests = await run('list_network_requests', ['list_network_requests', '--includePreservedRequests']);
    await run('take_snapshot', ['take_snapshot', '--filePath', path.join(devtoolsDir, 'snapshot.txt')]);
    await run('take_screenshot', ['take_screenshot', '--filePath', path.join(devtoolsDir, 'screenshot.png'), '--fullPage']);
    result.lighthouse = await run('lighthouse_audit', [
      'lighthouse_audit',
      '--mode',
      'snapshot',
      '--device',
      'desktop',
      '--outputDirPath',
      path.join(devtoolsDir, 'lighthouse'),
    ]);
    result.quality = analyzeChromeDevToolsQuality(result);
  } catch (err) {
    result.error = err?.stack || err?.message || String(err);
    result.quality = analyzeChromeDevToolsQuality(result);
  } finally {
    await execFileAsync('npx', ['chrome-devtools', 'stop'], { timeout: 10000 }).catch(() => {});
  }
  return result;
}

function analyzeChromeDevToolsQuality(result) {
  const consoleMessages = result.consoleMessages?.consoleMessages || [];
  const networkRequests = result.networkRequests?.networkRequests || [];
  const scores = result.lighthouse?.lighthouseResult?.summary?.scores || [];
  const warnings = [];
  const failures = [];

  const nonFaviconClientErrors = networkRequests.filter((request) => {
    const status = Number(request.status);
    return status >= 400 && status < 500 && !String(request.url).endsWith('/favicon.ico');
  });
  const serverErrors = networkRequests.filter((request) => Number(request.status) >= 500);

  for (const message of consoleMessages) {
    const text = message.text || '';
    if (message.type !== 'error') continue;
    if (text.includes('Failed to load resource') && serverErrors.length + nonFaviconClientErrors.length === 0) {
      warnings.push(`Console warning, likely favicon/noisy resource: ${text}`);
    } else {
      failures.push(`Console error: ${text}`);
    }
  }

  for (const request of networkRequests) {
    const status = Number(request.status);
    if (!status || status < 400) continue;
    const label = `${request.method || 'GET'} ${request.url} -> ${request.status}`;
    if (status >= 500) failures.push(`Server error response: ${label}`);
    else if (!String(request.url).endsWith('/favicon.ico')) failures.push(`Client error response: ${label}`);
    else warnings.push(`Ignored favicon response: ${label}`);
  }

  for (const score of scores) {
    if (typeof score.score !== 'number') continue;
    if (score.id === 'seo') {
      if (score.score < 0.9) warnings.push(`SEO Lighthouse finding: ${score.score}`);
      continue;
    }
    if (score.score < 0.8) failures.push(`Low Lighthouse ${score.title}: ${score.score}`);
    else if (score.score < 0.9) warnings.push(`Borderline Lighthouse ${score.title}: ${score.score}`);
  }

  return {
    status: failures.length ? 'fail' : warnings.length ? 'warning' : 'pass',
    warnings,
    failures,
  };
}

function parseJsonOutput(stdout) {
  const lines = stdout.split('\n').map((line) => line.trim()).filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i--) {
    if (!lines[i].startsWith('{') && !lines[i].startsWith('[')) continue;
    try {
      return JSON.parse(lines.slice(i).join('\n'));
    } catch {
      // Try earlier lines; CLI startup disclaimers can precede JSON.
    }
  }
  return { raw: stdout };
}

async function installMockRoutes(page) {
  await page.route('**/consent', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ session_id: 'qa-session', consent_version: 'qa' }),
    });
  });
  await page.route('**/feedback', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' }));
  await page.route('**/chat', async (route) => {
    const post = route.request().postDataJSON();
    const query = post?.query || '';
    const safe = query.length > 120 ? `${query.slice(0, 120)}…` : query;
    const body = [
      sse({ type: 'text', delta: 'QA mock 응답입니다. ' }),
      sse({ type: 'text_final', text: `질문 「${safe}」에 대한 QA mock 응답입니다.` }),
      sse({ type: 'done', images: [], sources: ['QA mock source'], score: 1 }),
      sse({ type: 'turn_id', turn_id: Date.now() }),
    ].join('');
    await route.fulfill({ status: 200, contentType: 'text/event-stream; charset=utf-8', body });
  });
}

function sse(obj) {
  return `data: ${JSON.stringify(obj)}\n\n`;
}

async function acceptConsent(page) {
  if (await page.locator('#modal').isVisible().catch(() => false)) {
    await page.locator('#ulabel').fill('qa');
    await Promise.all([
      page.waitForFunction(() => {
        const input = document.querySelector('#q');
        const modal = document.querySelector('#modal');
        return input && !input.disabled && modal && getComputedStyle(modal).display === 'none';
      }),
      page.locator('#agree').click(),
    ]);
  }
}

async function ask(page, text) {
  await page.locator('#q').fill(text);
  await page.keyboard.press('Enter');
}

async function turnCount(page) {
  return await page.locator('.turn').count();
}

async function waitForTurnComplete(page, expectedTurns, timeout) {
  await page.waitForFunction(
    (n) => document.querySelectorAll('.turn').length >= n && !document.querySelector('.turn:last-child .loading'),
    expectedTurns,
    { timeout },
  );
}

async function assertLastAnswerNonEmpty(page) {
  const text = await page.locator('.turn:last-child .a').innerText();
  assert(text.trim().length > 0, 'last answer should not be empty');
}

async function screenshot(page, scenario, name) {
  const rel = `screenshots/${name}.png`;
  await page.screenshot({ path: path.join(outDir, rel), fullPage: true });
  scenario.screenshots.push(rel);
}

async function step(target, name, fn) {
  const scenario = { name, status: 'pass', startedAt: new Date().toISOString(), durationMs: 0, screenshots: [], error: null };
  const started = Date.now();
  try {
    await fn(scenario);
  } catch (err) {
    scenario.status = 'fail';
    scenario.error = err?.stack || err?.message || String(err);
  } finally {
    scenario.durationMs = Date.now() - started;
    target.scenarios.push(scenario);
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function writeArtifacts(target) {
  await fs.writeFile(path.join(outDir, 'console.json'), JSON.stringify(target.console.concat(target.pageErrors), null, 2));
  await fs.writeFile(path.join(outDir, 'network-failures.json'), JSON.stringify(target.requestFailures, null, 2));
  await fs.writeFile(path.join(outDir, 'responses-4xx-5xx.json'), JSON.stringify(target.badResponses, null, 2));
  if (target.chromeDevTools) {
    await fs.writeFile(path.join(outDir, 'chrome-devtools.json'), JSON.stringify(target.chromeDevTools, null, 2));
  }
  await fs.writeFile(path.join(outDir, 'qa-report.md'), renderMarkdown(target));
}

function renderMarkdown(r) {
  const failed = r.scenarios.filter((s) => s.status === 'fail');
  const passed = r.scenarios.filter((s) => s.status === 'pass');
  return `# LMS Chatbot QA Report

## Summary

- URL: ${r.url}
- Started: ${r.startedAt}
- Mock chat: ${r.mockChat ? 'yes' : 'no'}
- Chrome DevTools audit: ${r.devtools ? `${r.chromeDevTools?.status || 'requested'}${r.chromeDevTools?.quality ? ` / quality ${r.chromeDevTools.quality.status}` : ''}` : 'no'}
- Result: ${failed.length || r.chromeDevTools?.status === 'fail' || r.chromeDevTools?.quality?.status === 'fail' ? 'FAIL' : 'PASS'}
- Scenarios: ${passed.length} passed / ${failed.length} failed / ${r.scenarios.length} total
- Console/Page errors: ${r.console.length + r.pageErrors.length}
- Request failures: ${r.requestFailures.length}
- 4xx/5xx responses: ${r.badResponses.length}

## Scenario Results

${r.scenarios.map(renderScenario).join('\n\n')}

## Console / Page Errors

${codeBlock(JSON.stringify(r.console.concat(r.pageErrors), null, 2))}

## Network Failures

${codeBlock(JSON.stringify(r.requestFailures, null, 2))}

## 4xx / 5xx Responses

${codeBlock(JSON.stringify(r.badResponses, null, 2))}

${renderChromeDevTools(r.chromeDevTools)}

## Reproduction

\`\`\`bash
npm run qa:chatbot -- --url ${r.url}${r.mockChat ? ' --mock-chat' : ''}${r.devtools ? ' --devtools' : ''}
\`\`\`
`;
}

function renderChromeDevTools(devtoolsResult) {
  if (!devtoolsResult) return '## Chrome DevTools for Agents Audit\n\n(Not run. Add `--devtools` to run the Chrome DevTools CLI evidence collector.)';
  const scores = devtoolsResult.lighthouse?.lighthouseResult?.summary?.scores || [];
  const consoleCount = devtoolsResult.consoleMessages?.consoleMessages?.length ?? 'n/a';
  const networkCount = devtoolsResult.networkRequests?.networkRequests?.length ?? 'n/a';
  return `## Chrome DevTools for Agents Audit

- Status: ${devtoolsResult.status.toUpperCase()}
- Quality status: ${(devtoolsResult.quality?.status || 'unknown').toUpperCase()}
- Console messages: ${consoleCount}
- Network requests: ${networkCount}
- Snapshot: \`${devtoolsResult.files.snapshot}\`
- Screenshot: \`${devtoolsResult.files.screenshot}\`
- Lighthouse reports: \`${devtoolsResult.files.lighthouseDir}/report.html\`, \`${devtoolsResult.files.lighthouseDir}/report.json\`

### Consent State

${codeBlock(JSON.stringify(devtoolsResult.consentState || null, null, 2))}

### Lighthouse Scores

${scores.length ? scores.map((s) => `- ${s.title}: ${s.score}`).join('\n') : '(not available)'}

### Quality Findings

- Failures: ${devtoolsResult.quality?.failures?.length || 0}
- Warnings: ${devtoolsResult.quality?.warnings?.length || 0}

${codeBlock(JSON.stringify(devtoolsResult.quality || null, null, 2))}

### DevTools CLI Commands

${codeBlock(JSON.stringify(devtoolsResult.commands, null, 2))}
${devtoolsResult.error ? `\n### DevTools Error\n\n${codeBlock(devtoolsResult.error)}` : ''}`;
}

function renderScenario(s) {
  return `### ${s.name}

- Status: ${s.status.toUpperCase()}
- Duration: ${s.durationMs}ms
- Screenshots: ${s.screenshots.length ? s.screenshots.map((p) => `\`${p}\``).join(', ') : '(none)'}
${s.error ? `- Error:\n\n${codeBlock(s.error)}` : ''}`;
}

function codeBlock(text) {
  return `\`\`\`\n${text || '[]'}\n\`\`\``;
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
