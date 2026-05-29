import fs from 'node:fs/promises';
import path from 'node:path';

const supportedScenarioTypes = ['consent', 'question', 'empty-input', 'click', 'fill', 'press-key', 'wait-for-text', 'screenshot'];

export async function loadProfile(profilePath) {
  const resolved = path.resolve(profilePath);
  const profile = JSON.parse(await fs.readFile(resolved, 'utf8'));
  validateProfile(profile, resolved);
  return { profile, profilePath: resolved };
}

export function validateProfile(profile, source = '<profile>') {
  if (!profile || typeof profile !== 'object') throw new Error(`${source}: profile must be an object`);
  if (!profile.name) throw new Error(`${source}: profile.name is required`);
  if (!Array.isArray(profile.scenarios) || profile.scenarios.length === 0) {
    throw new Error(`${source}: scenarios must be a non-empty array`);
  }

  const needsChatInput = profile.scenarios.some((scenario) => ['consent', 'question', 'empty-input'].includes(scenario.type));
  if (needsChatInput && !profile.selectors?.chatInput) {
    throw new Error(`${source}: selectors.chatInput is required for chatbot scenarios`);
  }

  for (const [index, scenario] of profile.scenarios.entries()) {
    if (!scenario.type) throw new Error(`${source}: scenarios[${index}].type is required`);
    if (!supportedScenarioTypes.includes(scenario.type)) {
      throw new Error(`${source}: unsupported scenario type ${scenario.type}`);
    }
    validateScenarioFields(scenario, index, source);
  }
}

function validateScenarioFields(scenario, index, source) {
  const prefix = `${source}: scenarios[${index}]`;
  if (['click', 'fill'].includes(scenario.type) && !scenario.target) {
    throw new Error(`${prefix}.${scenario.type} requires target`);
  }
  if (scenario.type === 'press-key' && !scenario.key) {
    throw new Error(`${prefix}.press-key requires key`);
  }
  if (scenario.type === 'wait-for-text' && !scenario.text) {
    throw new Error(`${prefix}.wait-for-text requires text`);
  }
}
