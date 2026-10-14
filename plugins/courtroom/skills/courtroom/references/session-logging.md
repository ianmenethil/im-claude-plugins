# Session Logging Reference

Specification for the `--log` and `--stats` features. Referenced from SKILL.md Phase 1
Step 1 (flag parsing), Phase 1 Step 1.5 (Display Stats and rotation) and Phase 6 (session
record append, before the approval question).

---

## Log File Location

`~/.claude/courtroom-sessions.jsonl`

One JSON object per line. Each line is one completed courtroom session.

---

## Schema

```json
{
  "ts": 1712345678,
  "task_hash": "a3f8b2c1d4e5",
  "file_count": 3,
  "rounds": 1,
  "raw_objections": 9,
  "filtered_objections": 2,
  "surviving_objections": 7,
  "accepted": 4,
  "rejected": 1,
  "compromised": 2,
  "codex_verdict": "approved-with-concerns",
  "duration_seconds": 312,
  "mode": "strict",
  "quick": false,
  "dual_plan": false,
  "repo_access": true
}
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `ts` | integer | Unix timestamp (seconds) when the verdict was rendered |
| `task_hash` | string | 12-char hex prefix of SHA-256(salt + task_description). Salt is a fixed random string stored in `~/.claude/courtroom-salt.txt` (created on first use). Prevents rainbow-table guessing of common prompts. |
| `file_count` | integer | Number of affected files. Never raw paths. |
| `rounds` | integer | Number of debate rounds completed (`ROUNDS_COMPLETED`) |
| `raw_objections` | integer | Total objections from Codex before filtering |
| `filtered_objections` | integer | Objections auto-filtered (catalog match or low confidence) |
| `surviving_objections` | integer | Objections that reached the rebuttal phase |
| `accepted` | integer | Objections Claude ACCEPTED |
| `rejected` | integer | Objections Claude REJECTED |
| `compromised` | integer | Objections Claude COMPROMISED |
| `codex_verdict` | string | Final Codex verdict enum value |
| `duration_seconds` | integer | Elapsed wall-clock seconds from Opening Statement to Verdict |
| `mode` | string | `"normal"`, `"strict"`, or `"quick"` |
| `quick` | boolean | Whether `--quick` was active |
| `dual_plan` | boolean | Whether `--dual-plan` was active |
| `repo_access` | boolean | Whether Codex read the repository in place (true) or a copy of the affected files (false) |

---

## Append Section

Run this in Phase 6, after the verdict block and before the approval question, when `--log`
is set. Build the JSON line and append it in this ONE block -- a value built in an earlier
Bash call does not survive into a later one, and appending an unset variable writes an empty
line. The append pattern is the one in error-handling.md ("Atomic Append Pattern for Session
Logging"):

```bash
# Compute fields (re-declare all from conversation context)
LOG_FILE="${HOME}/.claude/courtroom-sessions.jsonl"
TASK_DESCRIPTION='<task text from conversation context>'
# Create the salt on first use and never rewrite it: a salt that rotates every session
# defeats the rainbow-table protection task_hash exists for.
SALT_FILE="${HOME}/.claude/courtroom-salt.txt"
if [ ! -f "$SALT_FILE" ]; then
  SALT=$(head -c 16 /dev/urandom 2>/dev/null | od -A n -t x1 | tr -d ' \n' || printf '%s' "$(date +%s)$$")
  printf '%s\n' "$SALT" > "$SALT_FILE"
fi
SALT=$(cat "$SALT_FILE" 2>/dev/null || echo "default-salt")
TASK_HASH=$(printf '%s' "${SALT}${TASK_DESCRIPTION}" | sha256sum 2>/dev/null | cut -c1-12)
if [ -z "$TASK_HASH" ]; then
  TASK_HASH=$(printf '%s' "${SALT}${TASK_DESCRIPTION}" | shasum -a 256 2>/dev/null | cut -c1-12)
fi
if [ -z "$TASK_HASH" ]; then
  # Last-resort fallback: non-cryptographic, but it preserves the 12-char hash format
  # the schema documents.
  TASK_HASH=$(printf '%s' "$(date +%s)$$" | head -c 12)
fi
TS=$(date +%s)
# Re-declare every field value from conversation context (fresh shell -- nothing is
# "in scope"; an unset variable writes a malformed JSON line).
FILE_COUNT='<number of affected files>'
ROUNDS_COMPLETED='<rounds completed>'
RAW_OBJECTIONS='<objections Codex raised before filtering>'
FILTERED_OBJECTIONS='<objections auto-filtered>'
SURVIVING_OBJECTIONS='<objections that reached the rebuttal>'
ACCEPTED_COUNT='<objections accepted>'
REJECTED_COUNT='<objections rejected>'
COMPROMISED_COUNT='<objections compromised>'
CODEX_VERDICT='<approved | approved-with-concerns | needs-further-revision | approved-without-deliberation | SKIPPED>'
DURATION_SECONDS='<elapsed seconds from opening statement to verdict>'
MODE='<normal | strict | quick>'
QUICK_BOOL='<true | false>'
DUAL_PLAN_BOOL='<true | false>'
REPO_ACCESS='<true | false>'
# Build JSON
JSON_LINE="{\"ts\":${TS},\"task_hash\":\"${TASK_HASH}\",\"file_count\":${FILE_COUNT},\"rounds\":${ROUNDS_COMPLETED},\"raw_objections\":${RAW_OBJECTIONS},\"filtered_objections\":${FILTERED_OBJECTIONS},\"surviving_objections\":${SURVIVING_OBJECTIONS},\"accepted\":${ACCEPTED_COUNT},\"rejected\":${REJECTED_COUNT},\"compromised\":${COMPROMISED_COUNT},\"codex_verdict\":\"${CODEX_VERDICT}\",\"duration_seconds\":${DURATION_SECONDS},\"mode\":\"${MODE}\",\"quick\":${QUICK_BOOL},\"dual_plan\":${DUAL_PLAN_BOOL},\"repo_access\":${REPO_ACCESS}}"
TEMP_LOG="${LOG_FILE}.tmp.$$"
printf '%s\n' "$JSON_LINE" > "$TEMP_LOG" \
  || { echo "WARNING: Failed to write temp log; skipping."; exit 0; }
cat "$TEMP_LOG" >> "$LOG_FILE" \
  || { echo "WARNING: Failed to append to log; skipping."; rm -f "$TEMP_LOG"; exit 0; }
rm -f "$TEMP_LOG"
echo "Session logged: $LOG_FILE"
```

`QUICK_BOOL` and `DUAL_PLAN_BOOL` are `true` or `false`; `MODE` is `"normal"`, `"strict"` or
`"quick"`.

The salt is created on first use and never rewritten, so `task_hash` stays stable for the
same task text across sessions. If neither `sha256sum` nor `shasum` is available, the hash
falls back to the first 12 chars of `printf '%s' "$(date +%s)$$"` -- non-cryptographic, but
it preserves the 12-char hash format.

---

## Display Stats Section

Run this during Phase 1 Step 1.5 when the `--stats` flag is set (rotation below runs first).

```bash
LOG_FILE="${HOME}/.claude/courtroom-sessions.jsonl"
[ -f "$LOG_FILE" ] || { echo "No session log found at $LOG_FILE"; exit 0; }
# Count total sessions
TOTAL=$(wc -l < "$LOG_FILE" 2>/dev/null || echo 0)
echo "========================================"
echo "  COURTROOM SESSION STATISTICS"
echo "========================================"
echo "Total sessions logged: $TOTAL"
echo ""
echo "Log file: $LOG_FILE"
echo "Run 'cat $LOG_FILE | python3 -m json.tool' to inspect raw entries."
echo "========================================"
```

For richer statistics, Claude should read the JSONL file and compute in-context:
- Average surviving objections per session
- Acceptance rate (accepted / surviving_objections across all sessions)
- Most common codex_verdict values
- Session count by mode (normal / strict / quick)

Display as a formatted table. Do not use external tools — read the file and compute in-context.

---

## Rotation

Rotation runs ONLY when `--stats` is invoked AND the log has more than 500 entries.
Keep the newest 500 lines:

```bash
LOG_FILE="${HOME}/.claude/courtroom-sessions.jsonl"
TOTAL=$(wc -l < "$LOG_FILE" 2>/dev/null || echo 0)
if [ "$TOTAL" -gt 500 ]; then
  TEMP_ROT="${LOG_FILE}.rot.$$"
  tail -n 500 "$LOG_FILE" > "$TEMP_ROT" \
    || { echo "WARNING: Rotation temp write failed; skipping rotation."; rm -f "$TEMP_ROT"; exit 0; }
  mv "$TEMP_ROT" "$LOG_FILE" \
    || { echo "WARNING: Rotation mv failed; skipping rotation."; rm -f "$TEMP_ROT"; exit 0; }
  echo "Log rotated: kept newest 500 entries (was $TOTAL)."
fi
```

`mv` is atomic on the same filesystem. If `mv` fails (cross-device): the rotation is skipped
silently — the log continues to grow until the next `--stats` invocation.
