import fs from 'node:fs/promises';
import path from 'node:path';
import { codeBlock } from './utils.mjs';

export async function writeReport({ outDir, report, profilePath, timeoutMs }) {
  await fs.writeFile(path.join(outDir, 'devtools-qa-runner.json'), JSON.stringify(report, null, 2));
  await fs.writeFile(path.join(outDir, 'qa-report.md'), renderMarkdown({ report, profilePath, timeoutMs }));
}

function renderMarkdown({ report: r, profilePath, timeoutMs }) {
  const failed = r.scenarios.filter((s) => s.status === 'fail');
  const scores = r.lighthouse?.lighthouseResult?.summary?.scores || [];
  return `# DevTools QA Runner Report\n\n## Summary\n\n- URL: ${r.url}\n- Profile: ${r.profile.name}\n- Started: ${r.startedAt}\n- Engine: ${r.engine}\n- Result: ${failed.length || r.quality?.status === 'fail' ? 'FAIL' : 'PASS'}\n- Scenarios: ${r.scenarios.length - failed.length} passed / ${failed.length} failed / ${r.scenarios.length} total\n- Quality: ${r.quality?.status || 'unknown'}\n\n## Scenario Results\n\n${r.scenarios.map(renderScenario).join('\n\n')}\n\n## Lighthouse Scores\n\n${scores.length ? scores.map((s) => `- ${s.title}: ${s.score}`).join('\n') : '(not run)'}\n\n## Quality Findings\n\n${codeBlock(JSON.stringify(r.quality, null, 2))}\n\n## Console Messages\n\n${codeBlock(JSON.stringify(r.consoleMessages?.consoleMessages || [], null, 2))}\n\n## Network Requests\n\n${codeBlock(JSON.stringify(r.networkRequests?.networkRequests || [], null, 2))}\n\n## Reproduction\n\n\`\`\`bash\nnpm run qa:devtools-runner -- --url ${r.url} --profile ${path.relative(process.cwd(), profilePath)} --timeout ${timeoutMs}\n\`\`\`\n`;
}

function renderScenario(s) {
  return `### ${s.name}\n\n- Status: ${s.status.toUpperCase()}\n- Duration: ${s.durationMs}ms\n- Screenshots: ${s.screenshots.length ? s.screenshots.map((p) => `\`${p}\``).join(', ') : '(none)'}\n- Snapshots: ${s.snapshots.length ? s.snapshots.map((p) => `\`${p}\``).join(', ') : '(none)'}\n${s.error ? `- Error:\n\n${codeBlock(s.error)}` : ''}`;
}
