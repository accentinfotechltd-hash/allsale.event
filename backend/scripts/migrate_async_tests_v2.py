"""Second-wave migration: convert `def test_xxx(): ... async def _run(): ... asyncio.run(_run())`
pattern to native `async def test_xxx` (so pytest-asyncio's session-scoped
loop is used, avoiding Motor's "Event loop is closed" pollution).

This handles the variant of the pattern that uses `_run` (single underscore
prefix) and `asyncio.run(...)` instead of the older `get_event_loop()`
approach. Tests with multiple inner async helpers (like
test_iter24_email_resend_api / test_iter26_stripe_connect_remind) are left
alone — they need a per-file rewrite.

Run from /app/backend:
    python scripts/migrate_async_tests_v2.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent.parent / "tests"

RUN_DEF_RE = re.compile(r"^(\s*)async def _run\(\)\s*:\s*$")
RUN_CALL_RE = re.compile(r"^(\s*)asyncio\.run\(_run\(\)\)\s*$")
DEF_TEST_RE = re.compile(r"^(\s*)def (test_\w+)\((.*?)\)\s*:\s*$")


def migrate_file(path: Path) -> int:
    src = path.read_text()
    lines = src.split("\n")
    out: list[str] = []
    i = 0
    n_converted = 0
    while i < len(lines):
        line = lines[i]
        m_def = DEF_TEST_RE.match(line)
        if not m_def:
            out.append(line)
            i += 1
            continue

        indent, test_name, args = m_def.group(1), m_def.group(2), m_def.group(3)
        body_indent = indent + "    "

        # Find the nested `async def _run():`
        j = i + 1
        run_start = None
        while j < len(lines):
            ln = lines[j]
            stripped = ln.strip()
            if stripped == "" or stripped.startswith("#"):
                j += 1
                continue
            cur_indent = len(ln) - len(ln.lstrip())
            if cur_indent <= len(indent) and stripped != "":
                break
            m_run = RUN_DEF_RE.match(ln)
            if m_run and m_run.group(1) == body_indent:
                run_start = j
                break
            j += 1

        if run_start is None:
            out.append(line)
            i += 1
            continue

        # Find matching asyncio.run(_run()) call
        run_call = None
        k = run_start + 1
        while k < len(lines):
            m_call = RUN_CALL_RE.match(lines[k])
            if m_call and m_call.group(1) == body_indent:
                run_call = k
                break
            k += 1
        if run_call is None:
            out.append(line)
            i += 1
            continue

        # Convert: `def test_foo(args):` -> `async def test_foo(args):`
        out.append(f"{indent}async def {test_name}({args}):")
        # Emit lines BETWEEN the def and the `async def _run():` unchanged
        for src_idx in range(i + 1, run_start):
            out.append(lines[src_idx])
        # Skip the `async def _run():` line
        # Dedent body lines by 4
        for src_idx in range(run_start + 1, run_call):
            ln = lines[src_idx]
            out.append(ln[4:] if ln.startswith("    ") else ln)
        # Skip the asyncio.run line
        i = run_call + 1
        n_converted += 1

    new_src = "\n".join(out)
    if new_src != src:
        path.write_text(new_src)
    return n_converted


def main():
    total = 0
    files_changed = 0
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        n = migrate_file(path)
        if n:
            total += n
            files_changed += 1
            print(f"  {path.name}: migrated {n} test functions")
    print(f"\nDone — migrated {total} functions across {files_changed} files.")


if __name__ == "__main__":
    main()
