# Plugins

A Claude Code marketplace carrying two plugins. Each has its own README, licence and version.

| Plugin | What it does |
| --- | --- |
| [`courtroom`](plugins/courtroom/README.md) | Two models argue about your plan before you write code: Claude proposes, the OpenAI Codex CLI cross-examines, they debate, and the surviving plan is what gets executed. |
| [`recall`](plugins/recall/README.md) | Searchable local memory of past Claude Code and Codex sessions, with checked citations, so a `/clear` or a compaction doesn't lose the thread. |

## Install

```
/plugin marketplace add ianmenethil/im-claude-plugins
/plugin install courtroom
/plugin install recall
```

Or one plugin at a time from the shell:

```bash
claude plugin install courtroom --marketplace ianmenethil/im-claude-plugins
claude plugin install recall    --marketplace ianmenethil/im-claude-plugins
```

## What each plugin needs

- **courtroom** — the [Codex CLI](https://github.com/openai/codex) signed in (`codex login status`), and network access to OpenAI. Affected files are copied to a temp directory and sent to Codex, so don't point it at code you can't share. `--dry-run` builds the prompt without calling Codex.
- **recall** — Python 3 on `PATH`. It writes a local SQLite store under `~/.claude/context-recall/` and nothing else leaves your machine.

## Licence

MIT throughout, one `LICENSE` per plugin:

- `plugins/courtroom/LICENSE` — Copyright (c) 2026 JustineDaveMagnaye. Fork of [JustineDaveMagnaye/the-courtroom](https://github.com/JustineDaveMagnaye/the-courtroom).
- `plugins/recall/LICENSE` — Copyright (c) 2026 bledden. Copy of [bledden/claude-recall-plugin](https://github.com/bledden/claude-recall-plugin).

Both licences require their copyright notice to stay with the code. Neither repo is tracked for upstream updates any more; this repo is the source.
