# Noodle Pattern Reference

This skill adapts the `noodle/.agents/skills/adversarial-review` pattern.

## What Noodle does in Go
- Discovers schedulable skills from frontmatter with `schedule:`.
- Builds a task registry keyed by skill name.
- Scheduler emits compact orders with stages like `{ "do": "adversarial-review" }`.
- Compact orders expand into canonical stages with `task_key` and `skill`.
- Dispatch loads the skill bundle (`SKILL.md` + references) into the agent prompt.
- Go does not implement reviewer logic itself; the skill instructs the agent to call the opposite-model CLI.

## Important adaptation
For `adversarial-ideate`, there is no Noodle loop here. Pi invokes the skill directly. Therefore:
- Pi is the lead orchestrator.
- `scripts/run.go` is the reviewer launcher.
- Codex reviewers are independent external CLI calls.
- Pi reads reviewer outputs and presents all five reports separately by default.
- Pi only synthesizes a follow-up judgment if the user explicitly asks for one.

## Non-goals
- Do not simulate five reviewers in one model call.
- Do not require reviewers to debate each other.
- Do not build a full Noodle-style Go scheduler unless this workspace later needs autonomous scheduled ideation.
