export function assert(condition, message) {
  if (!condition) throw new Error(message);
}

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function safeName(value) {
  return String(value)
    .replace(/[^a-z0-9가-힣_-]+/gi, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 80) || 'artifact';
}

export function codeBlock(text) {
  return `\`\`\`\n${text || '[]'}\n\`\`\``;
}

export function parseJsonOutput(stdout) {
  const lines = stdout.split('\n').map((line) => line.trim()).filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i--) {
    if (!lines[i].startsWith('{') && !lines[i].startsWith('[')) continue;
    try {
      return JSON.parse(lines.slice(i).join('\n'));
    } catch {
      // CLI startup notices can precede JSON; keep scanning.
    }
  }
  // Surface the real CLI failure instead of letting an unparseable response flow
  // downstream as missing `.snapshot`, which masquerades as "element not found".
  throw new Error(`chrome-devtools did not return parseable JSON output:\n${stdout.slice(0, 500)}`);
}
