#!/usr/bin/env python3
"""Execute the plugin's self-contained shell blocks in a sandbox.
Skips anything that would call Codex. Run: python3 /tmp/courtroom-run.py <repo>"""
import re, subprocess, sys, pathlib, os, shutil

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
sand = pathlib.Path("/tmp/ct-run")
if sand.exists():
    shutil.rmtree(sand)
for d in ("home/.claude", "tmp", "work", "work/sub"):
    (sand / d).mkdir(parents=True, exist_ok=True)

# a real file the copy-loop blocks can find
(sand / "work" / "sample.md").write_text("# sample\ncontent\n")
(sand / "work" / "sub" / "nested.md").write_text("# nested\ncontent\n")

ENV = dict(os.environ, HOME=str(sand / "home"), TMPDIR=str(sand / "tmp"),
           TEMP=str(sand / "tmp"), TMP=str(sand / "tmp"))


def fill(blk: str) -> str:
    def rep(m: re.Match[str]) -> str:
        t = m.group(0).lower()
        if "manifest" in t:
            return str(sand / "work" / "manifest.txt")
        if "file" in t or "path" in t:
            return str(sand / "work" / "artifact.txt")
        return "testvalue"
    # only placeholder-looking tokens (must start with a letter); skips shell
    # redirects such as `2>` and `>` that would otherwise be captured
    blk = re.sub(r"<[A-Za-z][^<>\n]*>", rep, blk)
    # the patch-lifecycle block ships a stand-in line; give it real Python so the
    # success path is exercised rather than a syntax error
    return blk.replace("...script lines...", 'print("patch applied")')


skipped_live, skipped_read, ran = 0, 0, []
for md in sorted(p for p in root.rglob("*.md") if ".git" not in p.parts):
    for i, blk in enumerate(re.findall(r"```(?:bash|sh)[ \t]*\n(.*?)```", md.read_text(), re.S), 1):
        if "codex " in blk:
            skipped_live += 1
            continue
        first = next((ln.strip() for ln in blk.splitlines() if ln.strip()), "")
        if first.startswith("#") and re.search(r"CORRECT|WRONG|EXAMPLE|ILLUSTRAT", first):
            skipped_read += 1
            continue
        if not re.search(r"mktemp|printf|>>?\s*\"?\$", blk):
            skipped_read += 1
            continue
        r = subprocess.run(["bash"], input=fill(blk), text=True, capture_output=True,
                           env=ENV, cwd=str(sand / "work"), timeout=25)
        out = (r.stdout + r.stderr).strip().splitlines()
        ran.append((f"{md.relative_to(root)}#{i}", r.returncode, out[:2]))

print(f"ran {len(ran)} blocks, skipped {skipped_live} (call Codex), {skipped_read} (read-only)\n")
for name, rc, out in ran:
    mark = "ok  " if rc == 0 else "FAIL"
    print(f"{mark} {name}  rc={rc}  {' | '.join(out) if out else ''}")

print("\n--- artefacts produced under /tmp/ct-run ---")
for p in sorted(sand.rglob("*")):
    if p.is_file():
        print(f"{p.relative_to(sand)}  {p.stat().st_size}b")
