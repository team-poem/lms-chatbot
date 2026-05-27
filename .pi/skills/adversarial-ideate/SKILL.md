---
name: adversarial-ideate
description: Cross-model adversarial review of a seed idea or inspiration (not code). Spawns 5 Codex reviewers to challenge reality, prior art, counter-thesis, software shape, and deeper questions. Shows all reviewer reports separately instead of merging them.
---

# Adversarial Ideate

Take a seed idea / inspiration / hunch from the user and challenge it with five independent cross-model reviewers. The output is the five reviewer reports shown separately, so the user can inspect each lens directly rather than receiving a merged verdict.

This follows the Noodle `adversarial-review` pattern: the harness/agent schedules or invokes the skill, but the reviewers themselves must run through an external opposite-model CLI. Reviewers do not debate each other directly; they produce independent reports. The lead agent must show the reviewer reports to the user without merging them into a blended summary. Any lead note must be short and clearly separated from reviewer text.

## Hard Constraint
Reviewers MUST run via Codex CLI (`codex exec`) from `scripts/run.go`. Do not simulate reviewers with the current model, Pi subagents, internal delegation, or a single combined prompt. Those defeat the cross-model purpose.

## What this skill does
This skill runs **five separate Codex CLI calls** via `scripts/run.go`:
- Reality Tester
- Prior Art Hunter
- Devil's Advocate
- Software Materializer
- Depth Probe

## Usage
```bash
cd .pi/skills/adversarial-ideate && go run ./scripts/run.go "your seed idea here"
```

Or in Pi interactive mode:
```txt
/skill:adversarial-ideate your seed idea here
```
From the repo root, invoke `cd .pi/skills/adversarial-ideate && go run ./scripts/run.go ...`, then read the generated review files and present each reviewer output separately.

## Flow
1. Capture the seed verbatim.
2. Read `CURRENT_CONCERNS.md` at the repo root if it exists.
3. Run five Codex reviewers through `scripts/run.go`.
4. Verify all five output files exist and are non-empty.
5. Read the five outputs.
6. Present all five reviewer outputs separately, preserving each reviewer's opinion and evidence.
7. Do not merge reviewer opinions into a single blended synthesis. If useful, add only a short lead note after the reviewer outputs.

## Current Concerns
If `CURRENT_CONCERNS.md` exists, treat it as standing context for this workspace: recurring problems, open questions, and themes worth connecting the seed to. Use it to bias reviewer prompts toward personally meaningful critique, not generic output.

## Output shape
- Seed
- Reviewer outputs, unmerged and separated by lens:
  - Reality Tester
  - Prior Art Hunter
  - Devil's Advocate
  - Software Materializer
  - Depth Probe
- Optional short lead note:
  - where the reviewers agree / disagree
  - what to read first
  - no blended replacement for reviewer opinions

## Rules
- Do not drift into code review.
- Do not soften criticism to be balanced.
- Quote the seed back to itself.
- Distinguish content from form.
- If the seed is weak, say so plainly.
- Do not treat more reviewers, debate, or orchestration as value by itself.
- Preserve detailed reviewer evidence. Do not replace it with a compressed blended verdict unless the user explicitly asks for a summary.
- If the user asks for judgment later, synthesize only then, clearly marking it as a separate follow-up.

## Portability
The detailed lens definitions and verdict format live in the `references/` folder next to this skill.
