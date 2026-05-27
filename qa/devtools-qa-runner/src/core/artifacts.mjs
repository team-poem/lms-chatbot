import fs from 'node:fs/promises';
import path from 'node:path';
import { safeName, sleep } from './utils.mjs';

export class ArtifactStore {
  constructor({ outDir, client }) {
    this.outDir = outDir;
    this.client = client;
    this.counter = 0;
  }

  async prepare() {
    await fs.rm(this.outDir, { recursive: true, force: true });
    await fs.mkdir(this.outDir, { recursive: true });
    await fs.mkdir(path.join(this.outDir, 'screenshots'), { recursive: true });
    await fs.mkdir(path.join(this.outDir, 'snapshots'), { recursive: true });
    await fs.mkdir(path.join(this.outDir, 'lighthouse'), { recursive: true });
  }

  async snapshot(name, item = null) {
    const rel = `snapshots/${String(++this.counter).padStart(2, '0')}-${safeName(name)}.json`;
    const result = await this.client.run(`snapshot-${name}`, ['take_snapshot']);
    await fs.writeFile(path.join(this.outDir, rel), JSON.stringify(result, null, 2));
    if (item) item.snapshots.push(rel);
    return result.snapshot || result;
  }

  async screenshot(name, item = null) {
    const rel = `screenshots/${String(++this.counter).padStart(2, '0')}-${safeName(name)}.png`;
    await this.client.run(`screenshot-${name}`, ['take_screenshot', '--filePath', path.join(this.outDir, rel), '--fullPage']);
    if (item) item.screenshots.push(rel);
  }

  async waitForSnapshot(predicate, timeout) {
    const deadline = Date.now() + timeout;
    let last;
    while (Date.now() < deadline) {
      last = await this.snapshot(`poll-${Date.now()}`);
      if (predicate(last)) return last;
      await sleep(1000);
    }
    throw new Error('timeout while waiting for desired snapshot state');
  }
}
