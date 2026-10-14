# Error Handling and Behavioral Notes

This file contains the error handling reference and behavioral guidelines for the
Courtroom plugin. Referenced from SKILL.md.

---

## Error Handling

Every offered option list and `Ask:` prompt below is delivered via `AskUserQuestion`, one option per label.

### Codex CLI Not Found

```
COURTROOM ADJOURNED -- Codex CLI not found.
Install it: npm install -g @openai/codex
Set API key: export OPENAI_API_KEY=your-key
```

### Codex Not Authenticated

`codex --version` succeeds on an installed-but-signed-out CLI, and the failure then surfaces
at Phase 3 -- after the plan exists. That is why Phase 1 Step 2 runs
`codex --version && codex login status`.

If `codex login status` does not report a signed-in account:

```
COURTROOM ADJOURNED -- Codex CLI is not signed in.
Sign in with a ChatGPT plan:      codex login
Or export an API key:             export OPENAI_API_KEY=your-key
Or store the key with the CLI:    codex login --with-api-key
Then re-run the session.
```

### Codex Invocation Fails

One implementation, in Step 2e ("Handle failures and retry") of
`${CLAUDE_PLUGIN_ROOT}/skills/courtroom/references/cross-examination-procedure.md`: the
timeout (retry once with the same `timeout 150` invocation, then offer proceed without
cross-examination / retry manually / abort), empty output, malformed output, non-zero
exit, and the workdir-scan timeout all follow the rules there. A chunk FAILED for plan
size is never retried -- it routes to the Phase 2 Step 2 plan-size gate in SKILL.md.

Choosing to continue without cross-examination: see "Proceed Without Cross-Examination"
below.

### Truncated Cross-Examination Output

A token-limit cut can land on a block boundary: every OBJECTION block parses, the reply
looks finished, and the verdict then presents a complete review over ground Codex never
reached. The Concluding Assessment block is the completeness signal.

1. Every cross-examination reply must carry the Concluding Assessment block. Missing it means
   the output was cut off.
2. Re-prompt once: ask Codex to list the objections it did not reach, in the same OBJECTION
   schema, and append those to the parsed set.
3. If the Concluding Assessment is still absent after the re-prompt, set `TRUNCATED=true` and
   continue with what parsed. Print `Cross-examination partial: output truncated at N
   objections` -- N is the number of objections parsed -- in the Phase 6 verdict header and
   in the debate log.
4. `TRUNCATED=true` never blocks the session; the label is what keeps the gap visible.

### Workdir Contains Many Files (Codex Context Exhaustion)

If Codex output is mostly file listings with no objection content, it burned its context
budget scanning the workdir. Fix:

```bash
TEMP_DIR="${TEMP:-${TMP:-/tmp}}"
# Normalize Windows backslashes to forward slashes
TEMP_DIR="${TEMP_DIR//\\//}"
# Resolve to absolute path if relative (e.g., $TEMP='tmp' on some Windows setups)
if [[ "$TEMP_DIR" != /* ]]; then
  TEMP_DIR="$(cd "$TEMP_DIR" 2>/dev/null && pwd)" || TEMP_DIR="/tmp"
fi
# Re-declare from conversation context (fresh shell -- no state persists)
COURTROOM_WORKDIR="<value from conversation context>"
# Delete only a workflow-owned $TEMP_DIR/courtroom-* directory -- never a user-supplied one.
case "$COURTROOM_WORKDIR" in
  "${TEMP_DIR}"/courtroom-*)
    if [ -d "$COURTROOM_WORKDIR" ]; then
      find "$COURTROOM_WORKDIR" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + 2>/dev/null
    fi
    mkdir -p "$COURTROOM_WORKDIR"
    ;;
  *) echo "WARNING: Skipping unexpected workdir: $COURTROOM_WORKDIR" ;;
esac
```

Re-run Step 2b (it clears and repopulates the workdir, re-copying the affected files), then
retry from Step 2d. Do NOT retry from Step 2d without it: the cleanup above emptied the
workdir, so Codex would otherwise read no files.

### Write Tool / Bash Path Mismatch (Windows)

If a bash command reports "No such file or directory" for a temp file that was supposedly
just created, the file was written by Claude Write tool (different path space than bash on
Windows). Recreate using bash:

```bash
# Re-declare from conversation context (fresh shell -- no state persists)
COURTROOM_PROMPT_FILE="<value from conversation context>"
printf '%s\n' \
'<prompt content line 1>' \
'<prompt content line 2>' \
> "$COURTROOM_PROMPT_FILE"
```

Note: Do NOT use heredoc here — see cross-examination-procedure.md Step 2c.
Heredocs fail in the Claude Code Bash tool when content contains single quotes
or backticks. Always use bash printf with literal `'%s\n'` format string.


### Python / Bash Path Mismatch (Windows)

If bash reads 0 bytes from a file Python just wrote, the paths diverge.
Windows Python (CPython/CRT) resolves /tmp differently than Git Bash/MSYS2.

Symptoms: Python write succeeds but bash reads 0 bytes from same path.
Root cause: Interpreter-level path translation. Different from the Write tool
issue (tool-boundary problem) -- distinct mechanisms, distinct mitigations.

Fix: Use bash printf for all temp file creation in this workflow.
If Python must be used, write to the Windows-native absolute path directly
(e.g. C:/Users/.../AppData/Local/Temp/) and access via the MSYS2 equivalent.
Preferred: avoid Python for temp file creation entirely.

Never use the Write tool to create files that bash will read. Always use bash for temp
file creation in this workflow.

### No Task Provided

With no `--task` value and no argument string to fall back on, ask via `AskUserQuestion`:
"What task should the courtroom deliberate?" The answer becomes the session's task, and
Phase 1 proceeds normally from there.

### Quick Mode Eligibility Refused

When `--quick` is used for a task that fails the eligibility gate (>3 files, security/migration keywords):

```
Quick mode refused: this task does not meet quick-mode eligibility criteria.
Reason: <>3 files | security keyword detected | migration keyword detected>
Options:
  (a) Remove --quick to run the full session.
  (b) Add --force (--quick --force) to override. WARNING: Lower evidence quality.
```

If the user adds `--force`: display this warning prominently in the Opening Statement and
in the Verdict header. `--quick --force` is an **expert-facing escape hatch** for users who
understand the trade-off and intentionally accept reduced evidence quality.
The verdict header MUST show `[QUICK MODE / FORCE OVERRIDE]` so the reduced scrutiny is
visible in any downstream review of the verdict document.

### Codex Returns Unstructured Output

Apply Tier 2 re-prompt strategy (Phase 3 Step 3).
If Tier 2 also fails, apply Tier 3: display the raw output to the user, then ask via
`AskUserQuestion` "Do any points represent valid concerns?" with the options
**List the valid concerns** / **None — proceed with no objections** / **Abort session**.

### Atomic Append Pattern for Session Logging

Build the JSON line and append it inside ONE Bash block. A variable built in an earlier Bash
call does not survive into a later one, so a deferred build appends an empty line. The
canonical block — salt, task hash, field values, append — is session-logging.md's
"Append Section". It follows these rules:

1. Write to a unique temp file (`${LOG_FILE}.tmp.$$`) — never directly to the log.
2. `cat "$TEMP_LOG" >> "$LOG_FILE"` is atomic enough for single-line appends on local filesystems.
3. If the temp write or the append fails (permissions, disk full): warn and skip. Never fail
   the session.
4. The temp file is always cleaned up, even on failure.
5. Log rotation happens ONLY when `--stats` is invoked. Never rotate during a session.
   Rotation: read all lines, keep newest 500, write back atomically to a temp file, then
   `mv` over the original (mv is atomic on same filesystem).

### Proceed Without Cross-Examination

When the user chooses to skip cross-examination (timeout, error, or manual choice):
- Set contract state: objections=[], rebuttals=[], deliberation=null
- Skip Phases 3, 4, and 5 entirely.
- Phase 6 checks these empty-state values and renders the SKIPPED verdict:
  - Codex Verdict: SKIPPED (<reason>)
  - Add warning: This plan was NOT cross-examined. Proceed with additional caution.
  - Debate Log section: Cross-examination skipped: <reason>
  - Filtered Objections section: N/A -- no cross-examination performed.

### Proceed Without Deliberation

When Phase 5 (deliberation) is skipped but Phase 3/4 succeeded:
- Only substitute the rebuttal-revised plan if Phase 4 completed fully AND
  the revised plan section is non-empty.
- If Phase 4 was incomplete: use the Phase 2 plan.
- Set deliberation to "skipped" (distinct from null which means cross-exam skipped).
- Phase 6 Codex Verdict: approved-without-deliberation

---

## Cleanup After Session

Delete all remaining courtroom temp files using the manifest from conversation context:

```bash
TEMP_DIR="${TEMP:-${TMP:-/tmp}}"
TEMP_DIR="${TEMP_DIR//\\//}"
# Resolve to absolute path if relative (e.g., $TEMP='tmp' on some Windows setups)
if [[ "$TEMP_DIR" != /* ]]; then
  TEMP_DIR="$(cd "$TEMP_DIR" 2>/dev/null && pwd)" || TEMP_DIR="/tmp"
fi
# Re-declare from conversation context (fresh shell -- no state persists)
MANIFEST="<value from conversation context>"
COURTROOM_WORKDIR="<value from conversation context>"
set +e
if [ -f "$MANIFEST" ]; then
  while IFS= read -r temp_file || [ -n "$temp_file" ]; do
    case "$temp_file" in
      "${TEMP_DIR}/courtroom-"*) rm -f "$temp_file" 2>/dev/null ;;
      *) echo "WARNING: Skipping unexpected path: $temp_file" ;;
    esac
  done < "$MANIFEST"
  rm -f "$MANIFEST"
fi
# Clean the workdir (only a workflow-owned $TEMP_DIR/courtroom-* path)
case "$COURTROOM_WORKDIR" in
  "${TEMP_DIR}"/courtroom-*)
    if [ -d "$COURTROOM_WORKDIR" ]; then
      find "$COURTROOM_WORKDIR" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + 2>/dev/null
    fi
    ;;
  *) echo "WARNING: Skipping unexpected workdir: $COURTROOM_WORKDIR" ;;
esac
set -e
echo "Courtroom temp files cleaned up."
```

---

## Phase 7: File Patching Methodology

When Write/Edit tools are restricted, implement plans by writing Python
scripts via bash printf and executing them. Follow these rules to avoid
empirically-discovered failure patterns.

### Rule 1: Windows Path Literals

Prefer r-prefix for Windows paths that do NOT end in a backslash:

```python
# CORRECT
path = r"C:\Users\admin\.claude"
# WRONG -- \U is a unicode escape, SyntaxError
path = "C:\Users\admin\.claude"
```

For paths ending in `\`, r-prefix is a SyntaxError (`r"C:\\"` is invalid).
Use forward slashes or `os.path.join()` instead:

```python
import os
path = "C:/Users/admin/"
path = os.path.join(r"C:\Users\admin", "subdir", "")
```

### Rule 2: Anchored String Replacement

The root cause of replacement failures is incorrect Python string literal
construction -- not the API. `str.replace()` fails silently (returns unchanged
string) when the search literal Python builds differs from file content due to
escape processing. `str.find()` makes this explicit.

**Required pattern:**

```python
with open(target, "r", encoding="utf-8") as f:
    src = f.read()
before_hash = hash(src)
# Use raw string or read anchor from file to avoid escape divergence
anchor = "## Some Section Header"  # simple string, no backslashes
idx = src.find(anchor)
assert idx >= 0, f"Anchor not found: {anchor!r}"
assert src.count(anchor) == 1, f"Anchor not unique: {anchor!r}"
new_src = src[:idx] + replacement + src[idx + len(anchor):]
with open(target, "w", encoding="utf-8") as f:
    f.write(new_src)
# Verify: content changed and is different from before
with open(target, "r", encoding="utf-8") as f:
    result = f.read()
assert hash(result) != before_hash, "File unchanged after patch"
assert replacement.split()[0] in result, "Replacement not found in result"
print("Patch applied successfully")
```

Never use `str.replace()` when the old string contains backslashes.
Always assert anchor uniqueness before slicing.
Always verify file hash changed after writing.

### Rule 3: Shell-to-Python Transport (printf)

When writing Python scripts via bash printf, the printf format string MUST
be a literal `'%s\n'`. Script content goes as arguments only:

```bash
# CORRECT -- format string is literal, content is argument
printf '%s\n' \
  'line one of python script' \
  'line two' \
  > "$SCRIPT_FILE"

# WRONG -- %s in format position eats Python code containing %
printf "import sys; print(%s)" "hello"
```

Avoid nesting three quoting levels (printf single-quote -> Python string ->
bash expression inside Python). Keep Python strings simple; use string
concatenation instead of embedded shell commands.

### Rule 4: Bash Syntax in Python Strings

Use `[ ! -f ]` not `[ \! -f ]` in bash fragments inside Python strings.
The backslash before `!` is only needed in interactive bash for history
expansion. Inside scripts and Python string literals it causes:
`SyntaxWarning: invalid escape sequence "\!"`

```python
# CORRECT
check = "[ ! -f \"$FILE\" ]"
# WRONG -- SyntaxWarning
check = "[ \! -f \"$FILE\" ]"
```

### Rule 5: Backslash Sequences in Patch Script Content

When a Python patch script builds a `new_section` string that contains documentation
of shell commands (e.g., examples showing `printf '%s\n'`), Python interprets `\n`
inside regular and triple-quoted strings as actual newlines. The result is silently
split content in the output file.

```python
# WRONG -- \n becomes actual newline; file gets split line
new_section = "printf '%s\n' \\"

# CORRECT -- \\n produces literal \n in the output file
new_section = "printf '%s\\n' \\"
```

Rule: Any backslash sequence that should appear literally in the patched file must
be double-escaped in the Python string: `\n` → `\\n`, `\t` → `\\t`, `\!` → `\\!`.
This applies inside regular strings, f-strings, and triple-quoted strings alike.
Raw strings (`r"""..."""`) do not help here because the target text itself has
backslash sequences that Python would still need to emit correctly.

### General Patch Lifecycle

```bash
# Re-declare TEMP_DIR (fresh shell -- no state persists)
TEMP_DIR="${TEMP:-${TMP:-/tmp}}"
# 1. Write script via printf (format string is literal percent-s-newline)
SCRIPT=$(mktemp "${TEMP_DIR}/courtroom-XXXXXX.py")
printf '%s\n' \
  '...script lines...' \
  > "$SCRIPT" || { echo "ERROR: write failed"; exit 1; }
[ -s "$SCRIPT" ] || { echo "ERROR: script empty"; exit 1; }

# 2. Execute (python3 first -- bare `python` is absent on most modern systems)
PY=$(command -v python3 || command -v python) \
  || { echo "ERROR: neither python3 nor python is on PATH. Script preserved at: $SCRIPT"; exit 1; }
"$PY" "$SCRIPT"
EXIT_CODE=$?

# 3. Delete ONLY on success; preserve for inspection on failure
if [ $EXIT_CODE -eq 0 ]; then
    rm -f "$SCRIPT"
else
    echo "ERROR: Patch script failed (exit $EXIT_CODE). Script preserved at: $SCRIPT"
    exit 1
fi
```

---

## Behavioral Notes

- Tone: Professional but dramatic. Lean into the courtroom metaphor in headers and
  transitions, but keep the actual plan content clear and technical.
- Bias toward action: When in doubt, ACCEPT the objection. A slightly over-cautious plan
  is better than a plan with known holes.
- Transparency: Always show the user what Codex said, even if you disagree. The user is
  the judge -- they should see both sides.
- No ego: If Codex finds a real flaw, acknowledge it clearly and fix it properly.
- Cleanup: All temp files tracked via manifest. Clean at session end or any abort path.
