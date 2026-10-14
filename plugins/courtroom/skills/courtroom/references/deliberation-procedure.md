# Deliberation Procedure

Phase 5 instructions for the Courtroom plugin. Referenced from SKILL.md Phase 5.

---

## Step 1: Build the Deliberation Prompt

Read template from `${CLAUDE_PLUGIN_ROOT}/skills/courtroom/references/deliberation-prompt.md`.

Replace all placeholders: PROJECT_TYPE, LANGUAGE_FRAMEWORK, ORIGINAL_PLAN,
OBJECTIONS, REBUTTALS, REVISED_PLAN, SKILL_CONTEXT.

For SKILL_CONTEXT: use the value built in Phase 2 Step 0 of SKILL.md ("Load Domain Skill
Context") — the domain-skill block when a skill was named, the empty string when none was.
Never leave the {{SKILL_CONTEXT}} token in the prompt.

Store assembled prompt text in conversation context.

## Step 2: Invoke Codex

Write the prompt to a temp file via bash (printf -- see Step 2c in `${CLAUDE_PLUGIN_ROOT}/skills/courtroom/references/cross-examination-procedure.md`):

```bash
TEMP_DIR="${TEMP:-${TMP:-/tmp}}"; TEMP_DIR="${TEMP_DIR//\\//}"
if [[ "$TEMP_DIR" != /* ]]; then TEMP_DIR="$(cd "$TEMP_DIR" 2>/dev/null && pwd)" || TEMP_DIR="/tmp"; fi
COURTROOM_DELIB_FILE=$(mktemp "${TEMP_DIR}/courtroom-XXXXXX.md") \
  || { echo "ERROR: mktemp failed under $TEMP_DIR"; exit 1; }
# Codex's final message lands here (-o); stdout is only a transcript
COURTROOM_DELIB_OUT=$(mktemp "${TEMP_DIR}/courtroom-XXXXXX.out") \
  || { echo "ERROR: mktemp failed under $TEMP_DIR"; exit 1; }
MANIFEST="<value from conversation context>"
echo "$COURTROOM_DELIB_FILE" >> "$MANIFEST" \
  || { echo "ERROR: Failed to track deliberation prompt in manifest"; exit 1; }
echo "$COURTROOM_DELIB_OUT" >> "$MANIFEST" \
  || { echo "ERROR: Failed to track deliberation output in manifest"; exit 1; }
```

Write content via printf (mandatory format string is `'%s\n'`, one single-quoted argument
per logical line — never `\n` as an argument, which writes the letters, not a newline):

```bash
# Re-declare COURTROOM_DELIB_FILE from conversation context (fresh shell -- no state persists)
COURTROOM_DELIB_FILE="<value from conversation context>"
printf '%s\n' \
'First line of deliberation prompt content' \
'Additional lines ...' \
> "$COURTROOM_DELIB_FILE" \
  || { echo "ERROR: Failed to write deliberation prompt"; exit 1; }
[ -s "$COURTROOM_DELIB_FILE" ] \
  || { echo "ERROR: Deliberation prompt file is empty"; exit 1; }
echo "Deliberation prompt: $COURTROOM_DELIB_FILE"
```


Invoke Codex using input redirection from the same workdir as Phase 3 (COURTROOM_WORKDIR):

```bash
# Re-declare from conversation context (fresh shell -- no state persists)
COURTROOM_DELIB_FILE="<value from conversation context>"
COURTROOM_DELIB_OUT="<value from conversation context>"
COURTROOM_WORKDIR="<value from conversation context>"
test -r "$COURTROOM_DELIB_FILE" || { echo "ERROR: Not readable: $COURTROOM_DELIB_FILE"; exit 1; }
cat "$COURTROOM_DELIB_FILE" | timeout 150 codex exec --skip-git-repo-check --sandbox read-only -C "$COURTROOM_WORKDIR" -o "$COURTROOM_DELIB_OUT" - 2>&1
```

Set the Claude Code Bash tool timeout above the inner `timeout 150` (for example 155,000ms).
Read the verdict from `$COURTROOM_DELIB_OUT` (the model's final message) — Codex stdout is
a transcript (version banner, speaker labels, token counts), not the answer.
Never use "$(cat file)" as argument to codex exec.
Never place --sandbox before --skip-git-repo-check -- see `${CLAUDE_PLUGIN_ROOT}/skills/courtroom/references/cross-examination-procedure.md` Step 2d.

Handle failures same as Phase 3 Step 2e.
If deliberation is skipped (timeout, empty output, user choice):
- Use the rebuttal-revised plan as the final plan.
- Set deliberation to "skipped" (distinct from null used when cross-exam was skipped).
- Codex Verdict in Phase 6: approved-without-deliberation

Delete the deliberation prompt file immediately after capturing output:

```bash
# Re-declare COURTROOM_DELIB_FILE from conversation context (fresh shell -- no state persists)
COURTROOM_DELIB_FILE="<value from conversation context>"
rm -f "$COURTROOM_DELIB_FILE" 2>/dev/null
```

The re-declaration is required: in a fresh shell an unset `$COURTROOM_DELIB_FILE` expands
to an empty string, `rm -f ""` succeeds silently, and the file holding the user's source
is never deleted.

## Step 3: Parse Deliberation Verdict

Parse the model's final message — `$COURTROOM_DELIB_OUT` from Step 2, not the stdout
transcript — for:
- Accepted objection review: properly-addressed | insufficiently-addressed | introduced-new-issue
- Rejected objection review: concede | sustain
- Compromise review: workable | problematic
- New issues: list or "none"
- Final assessment: approved | approved-with-concerns | needs-further-revision
- REMAINING RISKS: list or "none"
- RECOMMENDATION: 1-2 sentences of final guidance

Store the final assessment, REMAINING RISKS and RECOMMENDATION in conversation context --
the Phase 6 verdict displays them.

## Step 4: Handle Additional Rounds

**Initialize once**, at the end of Round 1 (after `ROUNDS_COMPLETED` is incremented) and
only if `remaining rounds` is not already in conversation context:
`remaining rounds = rounds - ROUNDS_COMPLETED`, where `rounds` is the `--rounds` value from
Phase 1 (default 1) and `ROUNDS_COMPLETED` is the counter from Phase 1 Step 1. Every later
round reads the decremented value from conversation context — it is never recomputed.

The forced-focus set for the next round is: sustain objections, insufficiently-addressed
items, accepted objections marked `introduced-new-issue`, and compromises marked
`problematic`. The last two both mean the revision itself introduced the problem, so the
next round must re-examine them rather than run a fresh review.

If remaining rounds > 0 AND verdict is needs-further-revision:
- Set FORCED_FOCUS_VALUE in conversation context to the forced-focus set; cross-examination
  Step 1 substitutes it for {{FORCED_FOCUS}} in the next round
- Return to Phase 3 with these as forced focus areas
- Decrement remaining rounds
- Display round counter: "Round N of M"

If remaining rounds > 0 AND verdict is approved-with-concerns:
- Still run the next round to see if concerns can be resolved
- Set FORCED_FOCUS_VALUE to the `introduced-new-issue` and `problematic` items in the
  forced-focus set (the empty string when there are none), so the round targets what the
  revision broke
- Decrement remaining rounds

If remaining rounds = 0, OR verdict is approved (no concerns):
- Proceed to Phase 6.

## Step 5: Display Deliberation Results

```
========================================
  DELIBERATION COMPLETE
========================================

Codex Assessment: <approved | approved-with-concerns | needs-further-revision>

Accepted Objections:
  [1] <target> -> <properly-addressed | insufficiently-addressed | introduced-new-issue>

Rejected Objections:
  [2] <target> -> <concede | sustain>

Compromises:
  [3] <target> -> <workable | problematic>

New Issues: <none | list>
Remaining Risks: <none | list>
Recommendation: <1-2 sentences>
========================================
```

If any rejected objections received "sustain", incorporate into the final verdict as
Dissenting Opinions.

If any compromise received "problematic", add it to the forced-focus set for the next round
(Step 4) -- a middle ground worse than either extreme must be re-examined, not just printed.

If verdict is needs-further-revision and no rounds remain, note outstanding concerns
but proceed to Phase 6 -- the user will decide.
