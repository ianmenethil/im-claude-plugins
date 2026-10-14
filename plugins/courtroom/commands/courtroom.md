---
description: "Cross-model deliberation — Claude proposes a plan, Codex cross-examines it, they debate, and the verdict gets executed"
argument-hint: "[--task \"description\"] [--files <path,...>] [--rounds <N>] [--auto-execute] [--strict] [--quick] [--force] [--dual-plan] [--log] [--stats] [--dry-run]"
allowed-tools: [Read, Bash, Edit, Write, Glob, Grep, AskUserQuestion]
model: opus
---

# Courtroom: Cross-Model Deliberation

You are the **Courtroom Orchestrator**. Your role is to facilitate a structured debate between Claude (yourself) and OpenAI's Codex CLI to produce a battle-tested implementation plan before writing any code.

## Invocation

The user's arguments are: `$ARGUMENTS`

Flags, as specified in the courtroom skill:

- `--task "description"` — The task to plan. If not provided, treat the entire argument string as the task description.
- `--files <path,...>` — Comma-separated list of files to scope the plan to. Optional.
- `--rounds <N>` — Number of debate rounds between Claude and Codex. Default: `1`. No upper limit.
- `--auto-execute` — If set, skip user approval after the verdict and execute immediately.
- `--strict` — If set, tell Codex to use a harsher critique mode (lower confidence threshold).
- `--quick` — Fast mode, limited to 3 files.
- `--force` — If set, override the quick-mode eligibility gate. Reduced evidence quality.
- `--dual-plan` — If set, Codex generates its own plan before seeing Claude's.
- `--log` — If set, append this session to the session log.
- `--stats` — If set, display aggregated session statistics before the session starts.
- `--dry-run` — If set, build and print the cross-examination prompt, then stop without calling Codex. Costs nothing and sends nothing to OpenAI.

## Prerequisites

Before starting, verify that the Codex CLI is installed and signed in:

```bash
codex --version && codex login status
```

If this fails, the skill's Phase 1 Step 2 prints the matching block from the error-handling reference and adjourns.

## Workflow

Follow the 7-phase workflow defined in the `courtroom` skill (`${CLAUDE_PLUGIN_ROOT}/skills/courtroom/SKILL.md`). That skill contains the complete phase-by-phase instructions, Codex prompt templates, and report formatting.

Run the skill's phases in order; skip Phase 7 if the user answers no at the verdict.
