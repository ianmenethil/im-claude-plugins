# The Courtroom

Cross-model deliberation plugin for Claude Code. Claude proposes an implementation plan, Codex cross-examines it, they debate, and the verdict gets executed.

Two AI models arguing so your code doesn't have to.

A fork of [JustineDaveMagnaye/the-courtroom](https://github.com/JustineDaveMagnaye/the-courtroom).

## Install

One step:

```bash
/plugin install courtroom --marketplace ianmenethil/the-courtroom
```

Or add the marketplace first:

```bash
/plugin marketplace add ianmenethil/the-courtroom
/plugin install courtroom
```

## Usage

```bash
/courtroom --task "refactor auth module" --files src/auth.ts
```

### Flags

| Flag | Description |
|------|-------------|
| `--task "description"` | What to plan |
| `--files path,...` | Scope to specific files |
| `--rounds N` | Number of debate rounds (default: 1) |
| `--auto-execute` | Skip user approval |
| `--strict` | Harsher critique mode |
| `--quick` | Fast mode (limited to 3 files) |
| `--force` | Override the quick-mode eligibility gate (reduced evidence quality) |
| `--dual-plan` | Codex generates its own plan before seeing Claude's |
| `--log` | Log session statistics |
| `--stats` | Show aggregated stats |
| `--dry-run` | Build and print the Codex prompt, then stop — no Codex call, no cost |

## How It Works

| Role | Model |
|------|-------|
| Prosecution | Claude (proposes the plan) |
| Cross-Examiner | Codex CLI (challenges it) |
| Judge | You (approve or reject) |

**8-phase workflow:**

1. **Opening Statements** - Gather context, verify Codex CLI, parse arguments
2. **Prosecution** - Claude builds a detailed implementation plan
2.5. **Independent Plan** - Codex writes its own plan before seeing Claude's (`--dual-plan` only)
3. **Cross-Examination** - Codex challenges the plan (logical flaws, edge cases, architecture, security)
4. **Rebuttal** - Claude responds: ACCEPT / REJECT / COMPROMISE per objection
5. **Deliberation** - Codex reviews the revised plan as neutral arbiter
6. **Verdict** - Final plan presented for approval
7. **Execution** - Approved plan gets implemented

## Key Features

- **Weak Objection Catalog** - Auto-filters 22 known false-positive patterns across six categories (style, yagni, validation, scope, framework, wrong)
- **Dual-Plan Mode** - Codex generates an independent plan before seeing Claude's for comparison
- **Session Logging** - Tracks objection acceptance rates across sessions

## Requirements

- [Claude Code](https://claude.ai/code)
- [Codex CLI](https://github.com/openai/codex): `npm install -g @openai/codex`, signed in with `codex login` (ChatGPT plan) or by setting `OPENAI_API_KEY`, and confirmed with `codex login status`
- Network access to OpenAI
- A writable `$TEMP` directory

Note: the affected files are copied into a temporary working directory and sent to Codex for review. Do not run the courtroom on code that must not leave this machine.

**Cost.** Every round makes at least two Codex calls — cross-examination and deliberation. The independent-observation pass, `--dual-plan`, and the retry paths add more, and `--rounds` has no upper limit. `--dry-run` builds and prints the prompt without calling Codex at all, and `--quick` skips the observation pass.

## Development checks

Two scripts run against this repo from its root:

```bash
python3 scripts/check-plugin.py .   # static: paths, flags, verdict tokens, bash-block variables
python3 scripts/run-blocks.py .     # executes the self-contained shell blocks in a sandbox
```

`check-plugin.py` exits non-zero on any failure. `run-blocks.py` skips every block that calls
Codex and gives each one a throwaway `$HOME` and `$TMPDIR` under `/tmp`, so it never touches
your real configuration or your OpenAI account.

## License

MIT
