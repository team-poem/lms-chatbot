import fs from 'node:fs/promises';
import path from 'node:path';

export async function loadProfile(profilePath) {
  const resolved = path.resolve(profilePath);
  const profile = JSON.parse(await fs.readFile(resolved, 'utf8'));
  validateProfile(profile, resolved);
  return { profile, profilePath: resolved };
}

export function validateProfile(profile, source = '<profile>') {
  if (!profile || typeof profile !== 'object') throw new Error(`${source}: profile must be an object`);
  if (!profile.name) throw new Error(`${source}: profile.name is required`);
  if (!profile.selectors?.chatInput) throw new Error(`${source}: selectors.chatInput is required`);
  if (!Array.isArray(profile.scenarios) || profile.scenarios.length === 0) {
    throw new Error(`${source}: scenarios must be a non-empty array`);
  }
  for (const [index, scenario] of profile.scenarios.entries()) {
    if (!scenario.type) throw new Error(`${source}: scenarios[${index}].type is required`);
    if (!['consent', 'question', 'empty-input'].includes(scenario.type)) {
      throw new Error(`${source}: unsupported scenario type ${scenario.type}`);
    }
  }
}
