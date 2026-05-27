import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { parseJsonOutput } from './utils.mjs';

const execFileAsync = promisify(execFile);

export class DevToolsClient {
  constructor({ timeoutMs, cwd = process.cwd(), report }) {
    this.timeoutMs = timeoutMs;
    this.cwd = cwd;
    this.report = report;
  }

  async run(name, cliArgs) {
    const started = Date.now();
    try {
      const { stdout, stderr } = await execFileAsync('npx', ['chrome-devtools', ...cliArgs, '--output-format=json'], {
        cwd: this.cwd,
        timeout: Math.max(this.timeoutMs, 60000),
        env: {
          ...process.env,
          CI: '1',
          CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS: '1',
          CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS: '1',
        },
      });
      const parsed = parseJsonOutput(stdout);
      this.report.commands.push({ name, status: 'pass', durationMs: Date.now() - started, stderr: stderr.trim() || null });
      return parsed;
    } catch (err) {
      this.report.commands.push({
        name,
        status: 'fail',
        durationMs: Date.now() - started,
        error: err.message,
        stdout: err.stdout || '',
        stderr: err.stderr || '',
      });
      throw err;
    }
  }

  async stop() {
    await execFileAsync('npx', ['chrome-devtools', 'stop'], { timeout: 10000 }).catch(() => {});
  }
}
