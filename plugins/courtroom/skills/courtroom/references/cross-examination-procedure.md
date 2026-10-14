# Cross-Examination Procedure

Phase 3 instructions for the Courtroom plugin. Referenced from SKILL.md Phase 3.

EXECUTION MODEL: Each Bash invocation runs in a fresh shell. No state persists.
Track all state (file paths, output, retry counts) in conversation context.
On Windows, the Write tool and bash use different /tmp paths. Always write temp
files via bash (printf preferred; heredoc as fallback only in raw terminals).
Never use the Write tool or Python to create files that bash will read.

---

## Step 0: Resolve Repository Access

Runs BEFORE Step 1: Step 1's substitution rules and Step 1b's chunk sizing depend on
REPO_ACCESS, and Step 1a prints the assembled prompt. Read-only checks only -- no directory
creation, which stays in Step 2b.

```bash
# Re-declare AFFECTED_FILES from conversation context (fresh shell -- no state persists)
AFFECTED_FILES=(
  '/absolute/path/to/file1.md'
  '/absolute/path/to/file2.md'
)
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
REPO_ROOT=""
if [ -n "$GIT_ROOT" ]; then
  REPO_ROOT=$(cd "$GIT_ROOT" 2>/dev/null && pwd -P) || REPO_ROOT=""
fi
REPO_ACCESS=false
if [ -n "$REPO_ROOT" ]; then
  REPO_ACCESS=true
  for affected_file in "${AFFECTED_FILES[@]}"; do
    # Missing paths (files the plan proposes to create) are ignored here -- they are
    # unreadable in either mode, so they cannot constrain the access choice.
    [ -f "$affected_file" ] || continue
    file_dir=$(cd "$(dirname "$affected_file")" 2>/dev/null && pwd -P) \
      || { REPO_ACCESS=false; break; }
    file_path="${file_dir}/$(basename "$affected_file")"
    # A symlinked file resolves to its target, so containment is tested on the real path
    if [ -L "$file_path" ]; then
      file_path=$(readlink -f "$file_path" 2>/dev/null) \
        || { REPO_ACCESS=false; break; }
      [ -n "$file_path" ] || { REPO_ACCESS=false; break; }
    fi
    case "$file_path" in
      "$REPO_ROOT"|"$REPO_ROOT"/*) ;;
      *) REPO_ACCESS=false; break ;;
    esac
  done
fi
echo "REPO_ACCESS=$REPO_ACCESS"
echo "REPO_ROOT=$REPO_ROOT"
```

Rules:

- `REPO_ACCESS=true` when git resolves a root and every existing affected file resolves
  inside it. Containment is by path component on canonical paths -- a textual prefix is not
  enough, and the final path component counts: a file that is a symlink is resolved to its
  target first. A file whose symlink cannot be resolved with `readlink -f` forces
  `REPO_ACCESS=false`. A nested repository under the root is fine: the enclosing root reads
  it. A plan-only session (empty list) or an all-missing list uses the cwd's repository.
- `REPO_ACCESS=false` when no root resolves, a file resolves outside it, or a symlink is
  unresolvable. Copy mode (Step 2b) then applies.
- Store `REPO_ACCESS` and `REPO_ROOT` in conversation context. In repository mode
  `COURTROOM_WORKDIR` is `REPO_ROOT` -- no temp workdir is created. In copy mode it is the
  copy directory Step 2b builds.

---

## Step 1: Build the Codex Prompt (Partial Assembly)

Read template from `${CLAUDE_PLUGIN_ROOT}/skills/courtroom/references/cross-examination-prompt.md`.
Replace all placeholders EXCEPT {{CODEX_INDEPENDENT_OBSERVATIONS}} (leave that
token in place — it will be substituted after Step 2b-pre generates the value):
PROJECT_TYPE, LANGUAGE_FRAMEWORK, PROJECT_CONVENTIONS, AFFECTED_FILES,
EXISTING_CODE, SKILL_CONTEXT, PROPOSED_PLAN, FORCED_FOCUS, COMPETING_PLANS, REPO_ACCESS.

For REPO_ACCESS, use the value from Step 0:
- Repository mode (`REPO_ACCESS=true`): "You have READ-ONLY access to the repository at
  <REPO_ROOT> through your working directory. Verify any claim about existing code by
  reading the actual file before writing its `evidence` field. Do not attempt to modify
  anything."
- Copy mode (`REPO_ACCESS=false`): "Only the affected files listed above have been copied
  into your working directory. The wider repository is NOT available. Base claims on the
  files provided and mark anything you cannot verify as an assumption."

For AFFECTED_FILES: use the Phase 1 file list, one path per line. The empty string in a
plan-only session (`FILE_CONTEXT=none`) — the same empty-string rule as EXISTING_CODE in
SKILL.md Phase 2 Step 0. In repository mode, write them as repository-relative paths.

For EXISTING_CODE: the empty string in repository mode (`REPO_ACCESS=true`) — the reviewer
reads the files itself, and embedding contents it can read is waste. The SKILL.md Phase 2
Step 0 definition still applies in copy mode and plan-only sessions.

For SKILL_CONTEXT: use the value built in Phase 2 Step 0 of SKILL.md ("Load Domain Skill
Context") — the domain-skill block when a skill was named, the empty string when none was.
Never leave the {{SKILL_CONTEXT}} token in the prompt.

For COMPETING_PLANS: if `dualPlan=false` or `CODEX_INDEPENDENT_PLAN=null`, replace
with an empty string. If `dualPlan=true` and Codex plan is available, replace with:
"### Claude's Plan\n[Claude-proposed]\n<Claude plan summary>\n\n### Codex's
Independent Plan\n[Codex-proposed]\n<CODEX_INDEPENDENT_PLAN>"

In Round 1, replace {{FORCED_FOCUS}} with an empty string. Also initialize
FORCED_FOCUS_VALUE to the empty string in conversation context before Round 1, so the
round-2 back-edge always has a value to overwrite.
In Round N (N > 1), replace {{FORCED_FOCUS}} with FORCED_FOCUS_VALUE from conversation
context — the forced-focus set carried back from deliberation Step 4: sustained and
insufficiently-addressed objections, accepted objections marked `introduced-new-issue`, and
compromises marked `problematic`.
If --strict: append "STRICT MODE: Confidence threshold 30. Be aggressive."
Store the partially-assembled prompt text in conversation context.
Do NOT replace {{CODEX_INDEPENDENT_OBSERVATIONS}} yet.

Do NOT reorder the 7 numbered review priority sections (1, 2, 3, 3.5, 4, 5, 6) in the
prompt template.

## Step 1a: Dry Run (--dry-run)

If `dryRun` is true: print the assembled prompt from Step 1 verbatim, followed by

```
DRY RUN -- no Codex call made, no workdir created, nothing sent to OpenAI.
```

Then end the session. Do not run Step 1b or Step 2 onward, do not create the workdir or
manifest, and do not write the session log -- a dry run is not a session.

`{{CODEX_INDEPENDENT_OBSERVATIONS}}` stays unreplaced in the printed prompt, because
generating it requires the Codex call in Step 2b-pre that a dry run never makes. Say so in
the same output so the token is not mistaken for a bug.

## Step 1b: Pre-flight Size Check and Chunking

Threshold: 60,000 characters (~15K tokens).

**Plan-size check.** The plan-size gate is the Phase 2 Step 2 gate in SKILL.md: it offers
split the task / partial review / abort and says "Do not start Phase 3", so the oversized
case is already resolved by the time this file loads and no size menu belongs here. It
applies to this step only when the user chose partial review at that gate and the retained
sections still exceed the 60,000-character chunk limit — chunking cannot rescue that case
(every chunk carries the retained plan), so do not chunk and do not retry: go back to the
Phase 2 Step 2 gate.

If the full prompt (plan included) is <= 60,000: proceed with single prompt.
If > 60,000: chunking:
1. Classify files as critical-path or supporting:
   - Critical-path: files listed under "Files to Modify" in the plan, OR files
     referenced by more than 2 other affected files.
   - Supporting: all others.
2. Each chunk = full template + full plan + file list (paths only) + one file
   content + "Chunk N of M -- <filename>" header + critical-path classification.
   In repository mode, the chunk carries `Read <repository-relative path> in the
   repository.` instead of the file content -- the reviewer reads it itself.
   After assembling each chunk, check its total character count:
   - If <= 60,000 chars: proceed.
   - If > 60,000: apply Markdown truncation rules (see below) to the file content
     section, then recheck once.
   - If still > 60,000 after truncation: mark that chunk FAILED with reason
     "oversized even after truncation". Apply the same failure-gating rules as step 4.
3. Invoke Codex per chunk sequentially. The invocations run through Step 2d, once Step
   2-init and Step 2b have created the manifest and workdir — this step only assembles and
   sizes the chunks. Record CHUNK_N: OK or CHUNK_N: FAILED.
4. Failure gating:
   - If ANY critical-path chunk fails: review is incomplete.
     Offer: retry failed chunks / proceed-without / abort.
   - Exception: a chunk marked FAILED with reason "oversized even after truncation" is
     bounded by plan size, so retrying it cannot succeed. Never offer a retry for that
     failure — route to the Phase 2 Step 2 plan-size gate in SKILL.md instead.
   - If only supporting chunks fail: note in report, continue.
5. Deduplication: same target (case-insensitive substring match) AND same
   severity AND >50% Jaccard word overlap on objection text -> keep higher
   confidence.
6. Holistic pass: after per-chunk passes, send:
   - Full plan
   - All section headers from every file (for orientation)
   - All cross-file references (lines containing "see X.md", "per Y.md", etc.)
   - All fenced shell blocks that reference other files by name
   - All per-chunk objections found so far
   Instruction: "Identify NEW cross-file concerns only. Do not repeat existing
   objections."

Markdown file content > 40,000 chars: truncate to:
- Plan-referenced sections (with 10 lines of context each direction)
- All fenced code blocks (embedded shell scripts)
- All section headers (for orientation)
Remove prose between non-referenced sections. Do NOT use head/tail or
export-focused heuristics -- these are Markdown files, not source modules.

---

## Step 2: Invoke Codex

### Step 2-init: Initialize Manifest

Initialize the manifest FIRST, before any subcomponent runs. Both Step 2b-pre and Step 2c
will append to this file with >>. Store MANIFEST in conversation context immediately.

```bash
TEMP_DIR="${TEMP:-${TMP:-/tmp}}"
TEMP_DIR="${TEMP_DIR//\\//}"
if [[ "$TEMP_DIR" != /* ]]; then
  TEMP_DIR="$(cd "$TEMP_DIR" 2>/dev/null && pwd)" || TEMP_DIR="/tmp"
fi
MANIFEST="${TEMP_DIR}/courtroom-manifest-$(date +%s).txt"
touch "$MANIFEST" || { echo "ERROR: Cannot create manifest at $MANIFEST"; exit 1; }
# Round 2+ re-runs this step, and Phase 2's dual-plan step may already have created a
# manifest. Chain the new manifest onto the previous one before MANIFEST is overwritten in
# conversation context, so a cleanup that still holds the earlier path reaches this
# manifest too.
PREVIOUS_MANIFEST="<MANIFEST as held in conversation context before this block runs; empty string when none>"
if [ -n "$PREVIOUS_MANIFEST" ] && [ -f "$PREVIOUS_MANIFEST" ]; then
  echo "$MANIFEST" >> "$PREVIOUS_MANIFEST" \
    || { echo "ERROR: Failed to chain new manifest onto $PREVIOUS_MANIFEST"; exit 1; }
fi
echo "Manifest: $MANIFEST"
```

### Step 2a: Stale manifest cleanup

Manifest files are ALWAYS: in TEMP_DIR root (depth 0, no recursion), named
courtroom-manifest-TIMESTAMP.txt (no spaces, no dot prefix, workflow-created only).
No hidden files, no whitespace in names.

```bash
TEMP_DIR="${TEMP:-${TMP:-/tmp}}"
# Normalize Windows backslashes to forward slashes (Git Bash compatibility)
TEMP_DIR="${TEMP_DIR//\\//}"
# Resolve to absolute path if relative (e.g., $TEMP='tmp' on some Windows setups)
if [[ "$TEMP_DIR" != /* ]]; then
  TEMP_DIR="$(cd "$TEMP_DIR" 2>/dev/null && pwd)" || TEMP_DIR="/tmp"
fi
NOW=$(date +%s)
# find, not a glob: `shopt -s nullglob` is bash-only and this workflow also runs under
# zsh, where an unmatched glob aborts the whole block.
find "$TEMP_DIR" -maxdepth 1 -name 'courtroom-manifest-*.txt' 2>/dev/null \
  | while IFS= read -r stale_manifest; do
  [ -f "$stale_manifest" ] || continue
  # Three-way stat: Linux (stat -c), macOS/BSD (stat -f), Git Bash/MSYS2 (stat --format=)
  # Unsupported platforms: FILE_TIME empty -> skip with warning
  FILE_TIME=$(stat -c %Y "$stale_manifest" 2>/dev/null \
    || stat --format=%Y "$stale_manifest" 2>/dev/null \
    || stat -f %m "$stale_manifest" 2>/dev/null)
  if [ -z "$FILE_TIME" ]; then
    echo "WARNING: Cannot determine file age for $stale_manifest; skipping stale cleanup for this file."
    continue
  fi
  AGE=$(( NOW - FILE_TIME ))
  [ "$AGE" -le 3600 ] && continue
  while IFS= read -r stale_file || [ -n "$stale_file" ]; do
    case "$stale_file" in
      "${TEMP_DIR}"/courtroom-*) [ -f "$stale_file" ] && rm -f "$stale_file" ;;
      *) echo "WARNING: Skipping: $stale_file" ;;
    esac
  done < "$stale_manifest"
  rm -f "$stale_manifest"
done
echo "Stale manifest check complete."
```

### Step 2b: Determine the working directory

In repository mode (`REPO_ACCESS=true` from Step 0), `COURTROOM_WORKDIR` is `REPO_ROOT`:
skip this entire step -- no temp directory is created and no files are copied. Everything
below applies in copy mode only.

Never use the system temp dir as workdir -- thousands of files exhaust Codex context budget.

```bash
TEMP_DIR="${TEMP:-${TMP:-/tmp}}"
# Normalize Windows backslashes to forward slashes
TEMP_DIR="${TEMP_DIR//\\//}"
# Resolve to absolute path if relative (e.g., $TEMP='tmp' on some Windows setups)
if [[ "$TEMP_DIR" != /* ]]; then
  TEMP_DIR="$(cd "$TEMP_DIR" 2>/dev/null && pwd)" || TEMP_DIR="/tmp"
fi
COURTROOM_WORKDIR="${TEMP_DIR}/courtroom-wd"

# Clearing contents is safe by construction: COURTROOM_WORKDIR is always the fixed,
# workflow-owned $TEMP_DIR/courtroom-wd path -- never a user-supplied one.
if [ -d "$COURTROOM_WORKDIR" ]; then
  find "$COURTROOM_WORKDIR" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + 2>/dev/null
fi
mkdir -p "$COURTROOM_WORKDIR"
# Verify dir is writable before proceeding
[ -d "$COURTROOM_WORKDIR" ] && [ -w "$COURTROOM_WORKDIR" ] \
  || { echo "ERROR: Cannot create writable workdir at $COURTROOM_WORKDIR"; exit 1; }
echo "Workdir: $COURTROOM_WORKDIR"
```

After creating the workdir, copy each affected file into it so Codex can read them
during cross-examination. Use the file list from Phase 1 (--files or git diff):

```bash
# Re-declare AFFECTED_FILES from conversation context (fresh shell -- no state persists)
AFFECTED_FILES=(
  '/absolute/path/to/file1.md'
  '/absolute/path/to/file2.md'
)
# Re-declare COURTROOM_WORKDIR from conversation context (fresh shell -- no state persists)
COURTROOM_WORKDIR="<value from conversation context>"
# Copy affected files preserving relative path structure under workdir
# Avoids basename collisions (e.g. a/config.md and b/config.md both preserved)
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
# A file that cannot be read is recorded here instead of being dropped silently: Codex
# would otherwise review an incomplete workdir with no warning at all.
SKIPPED_FILES=()
for affected_file in "${AFFECTED_FILES[@]}"; do
  if [ -f "$affected_file" ]; then
    if [ -n "$GIT_ROOT" ] && [[ "$affected_file" == "$GIT_ROOT"* ]]; then
      rel="${affected_file#$GIT_ROOT/}"
      dest="${COURTROOM_WORKDIR}/${rel}"
      mkdir -p "$(dirname "$dest")"
      cp "$affected_file" "$dest" 2>/dev/null \
        && echo "Copied: ${rel}" \
        || echo "WARNING: Could not copy $affected_file"
    else
      # Mirror absolute path as workdir-relative to prevent basename collisions.
      # Strip leading / then strip colons (handles Windows drive letters: C:/x -> C/x).
      rel_dest="${affected_file#/}"
      rel_dest="${rel_dest//:/}"
      dest="${COURTROOM_WORKDIR}/${rel_dest}"
      mkdir -p "$(dirname "$dest")"
      cp "$affected_file" "$dest" 2>/dev/null \
        && echo "Copied (abs-mirror): ${rel_dest}" \
        || echo "WARNING: Could not copy $affected_file"
    fi
  else
    SKIPPED_FILES+=("$affected_file")
  fi
done
if [ ${#SKIPPED_FILES[@]} -gt 0 ]; then
  echo "WARNING: ${#SKIPPED_FILES[@]} affected file(s) not readable and not copied; Codex will not see them: ${SKIPPED_FILES[*]}"
fi
```

Store COURTROOM_WORKDIR in conversation context. Always pass -C "$COURTROOM_WORKDIR".

### Step 2b-pre: Codex Independent Observation (Anti-Bias Step)

**Quick-mode gate:** If `quickMode=true`: skip this step entirely. Set
`CODEX_INDEPENDENT_OBSERVATIONS` to `"INDEPENDENT SCAN SKIPPED: quick mode active"`.
Proceed directly to Step 2b-post. Do not write an observation prompt or invoke Codex.
`--force` does not lift this gate: `--quick --force` overrides only the quick-mode
eligibility refusal in `${CLAUDE_PLUGIN_ROOT}/skills/courtroom/references/error-handling.md`
— the independent scan stays skipped, and the `[QUICK MODE / FORCE OVERRIDE]` marker the
Verdict header carries is what makes the reduced scrutiny visible downstream.

**Goal:** Give Codex independent first-hand access to the affected files before it sees
the plan. This prevents cross-examination from being bounded by Claude's curated summary —
Codex reads the raw files itself and forms its own view. Note: this covers the affected
files only, not the full codebase.

This step runs after files are copied (Step 2b) and BEFORE the temp file is written (Step 2c).
If the workdir contains zero files (every copy failed), skip this step and set
`CODEX_INDEPENDENT_OBSERVATIONS` to `"INDEPENDENT SCAN SKIPPED: no files in workdir"` —
same marker convention as the gates above, so the degraded run stays visible instead of
silently empty.

**Pre-budget check:** Estimate the partial prompt size assembled in Step 1 (before
`{{CODEX_INDEPENDENT_OBSERVATIONS}}` substitution). If partial_prompt_size > 40,000 chars
(leaving less than 20K headroom for observations), set CODEX_INDEPENDENT_OBSERVATIONS to
`"INDEPENDENT SCAN SKIPPED: prompt too large for single-pass with observations"` and skip
directly to Step 2b-post. Do not write an observation prompt or invoke Codex for this step.

Build an observation-only prompt. List the files by the name Codex will read them under:
in repository mode, repository-relative paths (never the absolute AFFECTED_FILES paths);
in copy mode, the workdir-relative names from the copy output.

Repository mode (`REPO_ACCESS=true`):

```
OBSERVATION TASK: You have read-only access to the repository at <REPO_ROOT>. The files
below are the focus, by repository-relative path:
<list each file by its repository-relative name, one per line>

Read each listed file in the repository. For each file:
1. Summarize what the code does (1-3 sentences)
2. List any potential risks, edge cases, or architectural patterns you notice
3. Note anything that seems fragile, inconsistent, or likely to break under change

Do NOT propose solutions. Do NOT evaluate any plan. Simply report what you observe in the code.
Output your observations as a bulleted list under each filename.
Keep each file summary under 10 lines. Do not echo or dump raw file contents into your output — summarize
what you observe.
```

Copy mode (`REPO_ACCESS=false`):

```
OBSERVATION TASK: You have access to a working directory with the following files:
<list each file by its workdir-relative name, one per line — use the names from the copy output>

Read each file in the working directory. For each file:
1. Summarize what the code does (1-3 sentences)
2. List any potential risks, edge cases, or architectural patterns you notice
3. Note anything that seems fragile, inconsistent, or likely to break under change

Do NOT propose solutions. Do NOT evaluate any plan. Simply report what you observe in the code.
Output your observations as a bulleted list under each filename.
Keep each file summary under 10 lines. Do not echo or dump raw file contents into your output — summarize
what you observe. Produce all observations before reading additional files.
```

Write this prompt to a temp file using the same printf rules as Step 2c. Use the same
`courtroom-` prefix naming pattern (required for cleanup allowlist compatibility):

```bash
TEMP_DIR="${TEMP:-${TMP:-/tmp}}"
# Normalize Windows backslashes to forward slashes
TEMP_DIR="${TEMP_DIR//\\//}"
# Resolve to absolute path if relative (e.g., $TEMP='tmp' on some Windows setups)
if [[ "$TEMP_DIR" != /* ]]; then
  TEMP_DIR="$(cd "$TEMP_DIR" 2>/dev/null && pwd)" || TEMP_DIR="/tmp"
fi

OBS_PROMPT_FILE=$(mktemp "${TEMP_DIR}/courtroom-XXXXXX.md" 2>/dev/null)
if [ -z "$OBS_PROMPT_FILE" ] || [ ! -f "$OBS_PROMPT_FILE" ]; then
  OBS_PROMPT_FILE="${TEMP_DIR}/courtroom-obs-$$-${RANDOM}.md"
  (set -o noclobber; > "$OBS_PROMPT_FILE") 2>/dev/null \
    || { echo "ERROR: Cannot create observation prompt file safely"; exit 1; }
fi
# Codex's final message lands here (-o), separate from the stdout transcript
OBS_OUT_FILE=$(mktemp "${TEMP_DIR}/courtroom-XXXXXX.out" 2>/dev/null)
if [ -z "$OBS_OUT_FILE" ] || [ ! -f "$OBS_OUT_FILE" ]; then
  OBS_OUT_FILE="${TEMP_DIR}/courtroom-obs-$$-${RANDOM}.out"
  (set -o noclobber; > "$OBS_OUT_FILE") 2>/dev/null \
    || { echo "ERROR: Cannot create observation output file safely"; exit 1; }
fi
# Re-declare MANIFEST from conversation context -- append, do NOT recreate
MANIFEST="<value from conversation context>"
echo "$OBS_PROMPT_FILE" >> "$MANIFEST" \
  || { echo "ERROR: Failed to track observation prompt in manifest"; exit 1; }
echo "$OBS_OUT_FILE" >> "$MANIFEST" \
  || { echo "ERROR: Failed to track observation output file in manifest"; exit 1; }
```

Store OBS_PROMPT_FILE and OBS_OUT_FILE in conversation context as soon as this block
returns — a fresh shell keeps nothing, and the Codex invocation below re-declares both from
conversation context (an unstored value makes it run with `-o ""`).

The `courtroom-` prefix is REQUIRED — the stale cleanup allowlist in Step 2a and the
session cleanup in `${CLAUDE_PLUGIN_ROOT}/skills/courtroom/references/error-handling.md`
only remove files matching `${TEMP_DIR}/courtroom-*`.

Invoke Codex the same way as Step 2d:

```bash
# Re-declare from conversation context (fresh shell -- no state persists)
OBS_PROMPT_FILE="<value from conversation context>"
OBS_OUT_FILE="<value from conversation context>"
COURTROOM_WORKDIR="<value from conversation context>"
test -r "$OBS_PROMPT_FILE" || { echo "ERROR: Not readable: $OBS_PROMPT_FILE"; exit 1; }
cat "$OBS_PROMPT_FILE" | timeout 150 codex exec --skip-git-repo-check --sandbox read-only -C "$COURTROOM_WORKDIR" -o "$OBS_OUT_FILE" - 2>&1
```

Set the Claude Code Bash tool timeout above the inner `timeout 150` (for example 155,000ms),
so `timeout` terminates Codex first and the block still returns.

**On timeout or error:** set CODEX_INDEPENDENT_OBSERVATIONS to the string
`"INDEPENDENT SCAN SKIPPED: <reason>"` and continue. This makes degraded runs
visible in the prompt and transcript — never silently empty.

Capture CODEX_INDEPENDENT_OBSERVATIONS in conversation context from the model's final
message — the file passed to `-o` (`$OBS_OUT_FILE`), not the stdout transcript, which
carries the version banner, speaker labels and token counts instead of the answer.
Clean up the observation prompt and output files immediately after capture.

### Step 2b-post: Final Substitution + Size Recheck

Substitute `{{CODEX_INDEPENDENT_OBSERVATIONS}}` into the partially-assembled prompt
(from Step 1) using the value captured in Step 2b-pre.

Then recheck total assembled prompt size:
- If <= 60,000 chars: proceed to Step 2c (single prompt).
- If > 60,000 chars: truncate CODEX_INDEPENDENT_OBSERVATIONS to the first 20,000
  characters and append `\n[...observations truncated to fit context budget...]`.
  Recheck again. If still > 60,000 after truncation: discard the assembled prompt.
  Re-run Step 1b chunking from scratch, omitting CODEX_INDEPENDENT_OBSERVATIONS from
  each chunk (set to "INDEPENDENT SCAN SKIPPED: prompt too large for single-pass with
  observations"). Per-file chunks do not include observations but are still subject to
  the per-chunk size check in Step 1b — apply the same truncation and failure-gating
  rules if any chunk exceeds 60K.

Store the final assembled prompt in conversation context.

### Step 2c: Write the prompt to a temp file via bash

CRITICAL: Do NOT use the Claude Write tool, Python, or any non-bash tool to create
temp files that bash will read. On Windows, the Write tool and Windows Python both
resolve /tmp to a different path space than Git Bash / MSYS2. Files will appear empty
or missing when bash reads them. Always use bash printf for temp file creation.
If a bash command reports "No such file or directory" for a temp file another tool just
created, see the two path-mismatch entries in
`${CLAUDE_PLUGIN_ROOT}/skills/courtroom/references/error-handling.md` — "Write Tool / Bash
Path Mismatch (Windows)" and "Python / Bash Path Mismatch (Windows)".

```bash
TEMP_DIR="${TEMP:-${TMP:-/tmp}}"
# Normalize Windows backslashes to forward slashes
TEMP_DIR="${TEMP_DIR//\\//}"
# Resolve to absolute path if relative (e.g., $TEMP='tmp' on some Windows setups)
if [[ "$TEMP_DIR" != /* ]]; then
  TEMP_DIR="$(cd "$TEMP_DIR" 2>/dev/null && pwd)" || TEMP_DIR="/tmp"
fi

# Create temp file (mktemp with PID+RANDOM fallback)
COURTROOM_PROMPT_FILE=$(mktemp "${TEMP_DIR}/courtroom-XXXXXX.md" 2>/dev/null)
if [ -z "$COURTROOM_PROMPT_FILE" ] || [ ! -f "$COURTROOM_PROMPT_FILE" ]; then
  COURTROOM_PROMPT_FILE="${TEMP_DIR}/courtroom-$$-${RANDOM}.md"
  (set -o noclobber; > "$COURTROOM_PROMPT_FILE") 2>/dev/null \
    || { echo "ERROR: Cannot create temp file safely at $COURTROOM_PROMPT_FILE"; exit 1; }
fi

# Re-declare MANIFEST from conversation context (created in Step 2-init -- do NOT recreate here)
MANIFEST="<value from conversation context>"
echo "$COURTROOM_PROMPT_FILE" >> "$MANIFEST" \
  || { echo "ERROR: Failed to append prompt file to manifest at $MANIFEST"; exit 1; }
```

Write prompt content using printf (validated method for Claude Code Bash tool):

```bash
# Re-declare COURTROOM_PROMPT_FILE from conversation context (fresh shell -- no state persists)
COURTROOM_PROMPT_FILE="<value from conversation context>"
printf '%s\n' \
'First line of prompt content' \
'Second line -- dollar signs $VAR and backticks `cmd` are safe' \
'Single quotes in content escaped as '"'"'this'"'"' pattern' \
> "$COURTROOM_PROMPT_FILE" \
  || { echo "ERROR: Failed to write prompt to $COURTROOM_PROMPT_FILE"; exit 1; }
[ -s "$COURTROOM_PROMPT_FILE" ] \
  || { echo "ERROR: Prompt file is empty after write"; exit 1; }
echo "Prompt: $COURTROOM_PROMPT_FILE ($(wc -c < "$COURTROOM_PROMPT_FILE") bytes)"
```

printf rules:
- MANDATORY format string: '%s\n' always. NEVER use prompt text as the format string.
  Using prompt content as the format string causes silent corruption when it contains %.
- Each logical line of the prompt is one single-quoted argument.
- Single quotes in content: escape as '\'' (end quote, literal quote, reopen quote).
  Claude generates printf calls mechanically so this escaping is applied to all occurrences.
- Empty lines: use '' as the argument (empty single-quoted string).
- For prompts over ~200 lines: chain with >> for subsequent blocks (first call uses >,
  subsequent calls use >>).
- NUL byte safety: replace NUL bytes in any file content with the string <NUL> before
  inclusion. printf cannot emit NUL bytes.

Store COURTROOM_PROMPT_FILE and MANIFEST in conversation context; Step 2d stores
COURTROOM_CODEX_OUT when it creates that file.

Reference: Heredoc (raw terminal only -- NOT supported in Claude Code Bash tool):
Heredocs work correctly in raw terminal shells but fail in the Claude Code Bash tool
when content contains single quotes, backticks, or inner heredoc patterns. Do NOT
use heredoc as a fallback for prompt writing inside this workflow.

    # Raw terminal only:
    cat > "$FILE" << 'COURTROOM_PROMPT_EOF'
    Content here
    COURTROOM_PROMPT_EOF

### Step 2d: Invoke Codex

Use pipe from prompt file as the SOLE invocation method. Always pass -C to set workdir.
Never pass the prompt as a shell argument or via command substitution.

```bash
# Re-declare from conversation context (fresh shell -- no state persists)
TEMP_DIR="${TEMP:-${TMP:-/tmp}}"
TEMP_DIR="${TEMP_DIR//\\//}"
if [[ "$TEMP_DIR" != /* ]]; then
  TEMP_DIR="$(cd "$TEMP_DIR" 2>/dev/null && pwd)" || TEMP_DIR="/tmp"
fi
COURTROOM_PROMPT_FILE="<value from conversation context>"
COURTROOM_WORKDIR="<value from conversation context>"
MANIFEST="<value from conversation context>"

# Codex's final message lands here (-o); stdout is only a transcript
COURTROOM_CODEX_OUT=$(mktemp "${TEMP_DIR}/courtroom-XXXXXX.out" 2>/dev/null)
if [ -z "$COURTROOM_CODEX_OUT" ] || [ ! -f "$COURTROOM_CODEX_OUT" ]; then
  COURTROOM_CODEX_OUT="${TEMP_DIR}/courtroom-codex-$$-${RANDOM}.out"
  (set -o noclobber; > "$COURTROOM_CODEX_OUT") 2>/dev/null \
    || { echo "ERROR: Cannot create Codex output file safely"; exit 1; }
fi
echo "$COURTROOM_CODEX_OUT" >> "$MANIFEST" \
  || { echo "ERROR: Failed to track Codex output file in manifest"; exit 1; }

test -r "$COURTROOM_PROMPT_FILE" || { echo "ERROR: Not readable: $COURTROOM_PROMPT_FILE"; exit 1; }
cat "$COURTROOM_PROMPT_FILE" | timeout 150 codex exec --skip-git-repo-check --sandbox read-only -C "$COURTROOM_WORKDIR" -o "$COURTROOM_CODEX_OUT" - 2>&1
```

Set the Claude Code Bash tool timeout above the inner `timeout 150` (for example 155,000ms),
so `timeout` terminates Codex first and the block still returns.
Never pass the prompt as a shell argument using command substitution -- it hits OS arg
length limits (~32KB on Windows) and strips trailing newlines.
Never place --sandbox before --skip-git-repo-check -- argument order matters on some
codex versions and causes "No prompt provided via stdin" error.
Capture in conversation context: the exit code; stdout/stderr (diagnostics only); and the
contents of `$COURTROOM_CODEX_OUT`, which is the model's message and the only thing Step 3
parses. Codex stdout is a transcript (version banner, speaker labels, token counts), not
the answer.

### Step 2e: Handle failures and retry

- Timeout (the `timeout 150` bound kills Codex, or the call returns no message): Retry
  once, wrapped in `timeout 150`. If it fails again: offer proceed without
  cross-examination / retry manually / abort.
- Empty output: No retry. Run diagnostic: (1) display exit code and stderr;
  (2) only if exit code = 0 and stderr empty, check `codex login status`, OPENAI_API_KEY
  and prompt file size (wc -c). Then check `$COURTROOM_CODEX_OUT` -- an empty `-o` file with
  non-empty stdout means Codex answered without a final message. Offer: proceed without
  cross-examination / retry manually.
- Malformed output (no OBJECTION: blocks): Apply Tier 2 re-prompt in Step 3. No original retry.
- Non-zero exit: Display full stderr. Ask user how to proceed.
- Codex scans workdir and times out (context exhaustion): re-running Step 2b unchanged
  re-selects the same repository root in repository mode, reproducing the condition. Set
  `REPO_ACCESS=false` (reason: context exhaustion), rebuild Step 1's substitutions with the
  copy-mode REPO_ACCESS text, then re-run Step 2b (it copies the affected files), Step
  2b-pre, and retry from Step 2d. Do NOT retry from Step 2d directly — the workdir
  cleanup removed the copied files, so the copy and observation setup must be rebuilt first.
  The Phase 6 verdict carries the degraded-access marker.

### Step 2f: Cleanup prompt file

```bash
# Re-declare COURTROOM_PROMPT_FILE from conversation context (fresh shell -- no state persists)
COURTROOM_PROMPT_FILE="<value from conversation context>"
rm -f "$COURTROOM_PROMPT_FILE" 2>/dev/null
```

Delete only the prompt file: Step 3 and the Tier 2 re-prompt still need the `-o` message
file, which the manifest's session cleanup removes at the end.

---

## Step 3: Parse Objections (JSON Fast-Path + Three-Tier)

Special case: "NO OBJECTIONS" / "the plan is sound" / "no issues found" -> set the verdict in
conversation context to `approved`, skip Phases 4 and 5 (no rebuttal, no deliberation), and
go to Phase 6. The Debate Log and Filtered Objections sections each print `No objections
raised.`

Pre-processing: Strip ANSI escape codes and control characters (except newlines and tabs)
from the model's message (`$COURTROOM_CODEX_OUT` from Step 2d) before any parsing. Parse
that file, never the stdout transcript.

JSON Fast-Path (Tier 0): Check if output contains `---BEGIN CROSS-EXAMINATION---` /
`---END CROSS-EXAMINATION---` markers AND the content between them starts with `[`
(JSON array) once whitespace is trimmed and any Markdown code-fence delimiter lines are
stripped. The prompt template shows the array inside a fence, so strip fence lines before
the `[` test -- a fenced emission must not fall through to Tier 1, where it has no
OBJECTION: blocks and would burn a Tier 2 re-prompt. If so:
- Attempt to parse the content between the markers, fence lines stripped, as a JSON array.
- If parse succeeds AND each element contains all 6 required fields (severity, target,
  objection, evidence, alternative, confidence) with correct types (severity is a string,
  confidence is a number): use the parsed objects directly, skip Tier 1/2.
- Validate: severity must be one of `critical`, `major`, `minor`; confidence must be
  a number 0-100. Any element failing validation is treated as MALFORMED (route to Tier 1
  individually for that element).
- If JSON parse fails or no elements pass validation: fall through to Tier 1.

Tier 1 -- Structured extraction: If output has ---BEGIN CROSS-EXAMINATION--- /
---END CROSS-EXAMINATION--- markers, extract between them. Strip code fences.
Extract each OBJECTION: block using these rules:
- An OBJECTION: line starts a new block.
- Text before the first OBJECTION: is preamble (ignored).
- An empty line followed by non-field text ends the current block.
- Required fields: severity, target, objection, evidence, alternative, confidence.
- Missing required field -> block is MALFORMED. Do NOT invent field values.
- Duplicate required field within one block -> block is MALFORMED.
- Non-numeric confidence value -> block is MALFORMED.
- Severity value not in {critical, major, minor} -> block is MALFORMED.
- Duplicate optional fields -> keep the first occurrence.
MALFORMED blocks: route to Tier 2 individually (never accept with fabricated values).
Valid blocks (all 6 fields, no duplicates, numeric confidence):
- If all blocks valid -> Step 4 directly.
- If mix of valid + malformed -> process valid, run Tier 2 for malformed, merge, Step 4.
- If zero valid blocks but non-empty output -> Tier 2.

Tier 2 -- Re-prompt for reformatting: If zero valid blocks but non-empty (>50 chars),
OR for each individually MALFORMED block:
Build reformatting prompt: "Reformat into OBJECTION: schema. Do NOT add, remove, or
change the meaning of any finding. Only restructure format. All 6 fields are required:
severity, target, objection, evidence, alternative, confidence (numeric 0-100). If you
cannot determine confidence, write your best estimate as a number. Output must contain
the same number of OBJECTION blocks as the number of concerns in the input." + the
model's message captured from Step 2d (or the single malformed block text).
Invoke Codex once (same Step 2d; read its result from the new `-o` file). Apply Tier 1 to
the result.
Validation: estimate concern count in raw output by counting sentences containing
"should", "must", "risk", "missing", "fail", or "break". If parsed count differs
from estimated count by >1, flag: "Parsed N objections but estimated M in raw output
-- review raw output manually."
If still zero valid blocks -> Tier 3.

Tier 3 -- Manual review: Show raw output. Ask: "Do any points represent valid concerns?"
The option labels and `AskUserQuestion` wording for this step are in
`${CLAUDE_PLUGIN_ROOT}/skills/courtroom/references/error-handling.md`
("Codex Returns Unstructured Output").

---

## Step 4: Evidence Check, Then Filter Weak Objections

**Evidence check first.** For each objection, verify the `evidence` field against the file
it names — the real path in repository mode, the copy in copy mode:

- Evidence asserts that something exists in the current tree and it does not (file, symbol,
  function): the reference is fabricated -> FILTERED with the catalog ID `WO-WRONG-01`.
  No rebuttal is spent.
- The named file does not exist yet because the plan proposes creating it, or the file is
  not available in copy mode: nonexistence proves nothing -> keep, annotate
  `evidence-not-verifiable`. Show the annotation in the Step 5 display.
- The file exists but does not support the claim -> keep, annotate
  `evidence-corrected: <what the file actually says>`. The rebuttal must acknowledge the
  correction.
- Annotations never change the confidence score — the confidence filter below runs on
  Codex's original number, so nothing kept here can be silently filtered later.

Then filter:

Read `${CLAUDE_PLUGIN_ROOT}/skills/courtroom/references/objection-catalog.md`.
Catalog match -> check whether a concrete technical failure mode remains beyond the catalog pattern.
If yes: SURVIVES (note catalog partial-match in the display). If no concrete technical core remains: FILTERED + catalog ID.
Confidence < 50 (< 30 when `--strict` is set, including a `--quick --strict` run) -> FILTERED: low-confidence (the `low-confidence` bucket in
the filter breakdown).
Filtered objections excluded from the rebuttal phase.

---

## Step 5: Display Results

```
========================================
  CROSS-EXAMINATION COMPLETE
========================================
Raw objections: <N> | Filtered: <N> | Surviving: <N>

--- SURVIVING OBJECTIONS ---
[1] [SEVERITY] <target>
    Objection: <text>
    Evidence: <evidence>
    Alternative: <alternative>

--- FILTERED ---
<N> auto-filtered: <style: N, yagni: N, validation: N, scope: N, framework: N, wrong: N,
                 low-confidence: N>
========================================
Claude is preparing the rebuttal...
```
