#!/usr/bin/env python3
"""Static checks for the courtroom plugin. Run from the repo root:

    python3 scripts/check-plugin.py [root]

Exits non-zero on any failure. See scripts/run-blocks.py for the execution half."""
import re, subprocess, sys, pathlib

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
fails, warns = [], []

refs = sorted(p for p in root.rglob("*.md") if ".git" not in p.parts)
if not refs:
    print("FATAL: no markdown found under", root); sys.exit(2)

# 1. every fenced bash block parses
blocks = 0
for md in refs:
    for i, blk in enumerate(re.findall(r"```(?:bash|sh)[ \t]*\n(.*?)```", md.read_text(), re.S), 1):
        blocks += 1
        r = subprocess.run(["bash", "-n"], input=blk, text=True, capture_output=True)
        if r.returncode:
            fails.append(f"{md.relative_to(root)}: bash block {i} does not parse: {r.stderr.strip().splitlines()[0]}")

# 2. ${CLAUDE_PLUGIN_ROOT}/... targets exist
hits = 0
for md in refs:
    for p in set(re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9._/-]+)", md.read_text())):
        hits += 1
        if not (root / p).exists():
            fails.append(f"{md.relative_to(root)}: ${{CLAUDE_PLUGIN_ROOT}}/{p} does not exist")

# 3. no unprefixed repo-root-relative reference pointers
for md in refs:
    txt = md.read_text()
    for m in set(re.findall(r"(?<!\$\{CLAUDE_PLUGIN_ROOT\}/)(?<!\w)skills/courtroom/references/[A-Za-z0-9_./-]*\.md", txt)):
        fails.append(f"{md.relative_to(root)}: unprefixed path {m}")

# 4. every reference file is cited by SKILL.md or commands/courtroom.md
others = "\n".join(m.read_text() for m in refs)
for f in sorted((root / "skills/courtroom/references").glob("*.md")):
    if f.name not in others.replace(f.read_text(), ""):
        warns.append(f"orphan reference (cited by no other file): {f.relative_to(root)}")

# 5. flag surface
EXPECTED = ["--task", "--files", "--rounds", "--auto-execute", "--strict",
            "--quick", "--force", "--dual-plan", "--log", "--stats", "--dry-run"]
REMOVED = ["--auto-skill", "--codex-skill"]
for md in refs:
    txt = md.read_text()
    for fl in REMOVED:
        if fl in txt:
            fails.append(f"{md.relative_to(root)}: removed flag {fl} still documented")
cmdtext = (root / "commands/courtroom.md").read_text() if (root / "commands/courtroom.md").exists() else ""
cmdflags = {f for f in re.findall(r"--[a-z][a-z-]+", cmdtext) if f in EXPECTED or f in REMOVED}
missing = [f for f in EXPECTED if f not in cmdflags]
if missing:
    fails.append(f"commands/courtroom.md: flag list missing {missing}")

# 6. verdict enum
skilltext = (root / "skills/courtroom/SKILL.md").read_text() if (root / "skills/courtroom/SKILL.md").exists() else ""
for tok in ["approved-without-deliberation", "needs-further-revision", "SKIPPED"]:
    if tok not in skilltext:
        fails.append(f"SKILL.md: verdict enum missing token {tok}")

# 7. fresh-shell rule: a bash block may only use variables it assigns itself
SH_OK = {"PATH", "HOME", "TEMP", "TMP", "TMPDIR", "RANDOM", "PWD", "IFS", "LANG",
         "LC_ALL", "SHELL", "USER", "HOSTNAME", "LINENO", "SECONDS", "UID", "EUID", "PPID", "OSTYPE"}
def is_example(blk: str) -> bool:
    """Illustrative CORRECT/WRONG blocks teach syntax and are not run."""
    first = next((ln.strip() for ln in blk.splitlines() if ln.strip()), "")
    return first.startswith("#") and re.search(r"CORRECT|WRONG|EXAMPLE|ILLUSTRAT", first)


for md in refs:
    for i, blk in enumerate(re.findall(r"```(?:bash|sh)[ \t]*\n(.*?)```", md.read_text(), re.S), 1):
        if is_example(blk):
            continue
        # a $NAME inside single quotes is literal text, not a variable use
        scan = re.sub(r"'[^'\n]*'", "''", blk)
        used = set(re.findall(r"\$\{?([A-Z][A-Z0-9_]*)\}?", scan))
        assigned = set(re.findall(r"([A-Z][A-Z0-9_]*)=", blk))
        for v in sorted(used - assigned - SH_OK):
            fails.append(f"{md.relative_to(root)}: bash block {i} uses ${v} without assigning it in the same block")

# 8. every {{TOKEN}} in a prompt template is filled by a substitution list elsewhere
TEMPLATES = {"cross-examination-prompt.md", "deliberation-prompt.md", "dual-plan-prompt.md"}
body = "\n".join(m.read_text() for m in refs if m.name not in TEMPLATES)
for md in refs:
    if md.name not in TEMPLATES:
        continue
    for tok in sorted(set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", md.read_text()))):
        if tok == "PLACEHOLDER":  # prose: "replace all {{PLACEHOLDER}} values"
            continue
        if tok not in body:
            fails.append(f"{md.relative_to(root)}: {{{{{tok}}}}} is filled by no substitution list")

# 9. contracts fixed in the dead-code pass must not regress
alltext = "\n".join(m.read_text() for m in refs)
if "PARTIALLY-REVIEWED" in alltext:
    fails.append("PARTIALLY-REVIEWED is still referenced somewhere (contract: deleted)")
sktext = (root / "skills/courtroom/SKILL.md").read_text() if (root / "skills/courtroom/SKILL.md").exists() else ""
for bucket in ["style:", "yagni:", "validation:", "scope:", "framework:", "wrong:", "low-confidence:"]:
    if bucket not in sktext:
        fails.append(f"SKILL.md filter breakdown is missing the '{bucket[:-1]}' bucket")
for v in ["FILE_COUNT", "RAW_OBJECTIONS", "FILTERED_OBJECTIONS", "SURVIVING_OBJECTIONS",
          "ACCEPTED_COUNT", "REJECTED_COUNT", "COMPROMISED_COUNT", "CODEX_VERDICT",
          "DURATION_SECONDS", "QUICK_BOOL", "DUAL_PLAN_BOOL", "REPO_ACCESS", "CODEX_PLAN_OUT"]:
    if not re.search(rf"{v}`?\s*=", alltext):
        fails.append(f"{v} is read but never assigned anywhere")

# 10. Codex call bound is the one declared value: 150s
for md in refs:
    for t in sorted(set(re.findall(r"timeout\s+(\d+)", md.read_text()))):
        if t != "150":
            fails.append(f"{md.relative_to(root)}: unexpected timeout bound {t}s (the declared bound is 150)")

# 11. never invoke bare `python` -- absent on modern Linux and macOS
for md in refs:
    for ln in md.read_text().splitlines():
        if re.match(r"\s*python\s+\S", ln):
            fails.append(f"{md.relative_to(root)}: invokes bare `python`; use python3 (or a python3-else-python fallback)")

# 12. plugin validates
r = subprocess.run(["claude", "plugin", "validate", "."], cwd=root, capture_output=True, text=True)
if r.returncode:
    fails.append(f"claude plugin validate failed: {(r.stdout + r.stderr).strip()[:300]}")

# 13. every Codex invocation inside a bash block carries the read-only sandbox, in the
# order the CLI requires (skip-git-repo-check first, or it errors "No prompt provided
# via stdin"). Prose that merely mentions "codex exec" is not an invocation.
INVOCATION = "--skip-git-repo-check --sandbox read-only -C"
for md in refs:
    for i, blk in enumerate(re.findall(r"```(?:bash|sh)[ \t]*\n(.*?)```", md.read_text(), re.S), 1):
        for ln in blk.splitlines():
            if "codex exec" in ln and INVOCATION not in ln:
                fails.append(f"{md.relative_to(root)}: bash block {i} invokes codex exec without '{INVOCATION}'")

print(f"checked {len(refs)} markdown files, {blocks} bash blocks, {hits} plugin-root paths")
for w in warns: print("WARN:", w)
for f in fails: print("FAIL:", f)
print(f"\n{'PASS' if not fails else 'FAIL'} — {len(fails)} failure(s), {len(warns)} warning(s)")
sys.exit(1 if fails else 0)
