"""One-off migration: convert old `asyncio.get_event_loop().run_until_complete(run())`
pattern to native `async def test_xxx` (pytest-asyncio auto mode is now enabled
in pytest.ini, so async test functions are picked up automatically).

Pattern in:
    def test_foo():
        \"\"\"docstring\"\"\"
        async def run():
            <body>
        asyncio.get_event_loop().run_until_complete(run())

Pattern out:
    async def test_foo():
        \"\"\"docstring\"\"\"
        <body dedented one level>

Run from /app/backend:
    python scripts/migrate_async_tests.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent.parent / "tests"

# Match: `    async def run():`
RUN_DEF_RE = re.compile(r"^(\s*)async def run\(\)\s*:\s*$")
# Match: `    asyncio.get_event_loop().run_until_complete(run())`
# or:    `    asyncio.run(run())`
RUN_CALL_RE = re.compile(
    r"^(\s*)(?:asyncio\.get_event_loop\(\)\.run_until_complete\(run\(\)\)|asyncio\.run\(run\(\)\))\s*$"
)
# Match: top-level `def test_xxx(...)` or method `    def test_xxx(self, ...)`
# We only need to convert the ones that contain a nested `async def run():`
# so we look for the enclosing function header in a second pass.
DEF_TEST_RE = re.compile(r"^(\s*)def (test_\w+)\((.*?)\)\s*:\s*$")


def migrate_file(path: Path) -> int:
    """Return number of test functions migrated in this file."""
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

        # Look ahead inside this function (until next same-indent def/class)
        indent, test_name, args = m_def.group(1), m_def.group(2), m_def.group(3)
        body_indent = indent + "    "
        # Find the function body extent
        j = i + 1
        run_start = None
        while j < len(lines):
            ln = lines[j]
            stripped = ln.strip()
            # Empty / pure comment lines don't terminate
            if stripped == "" or stripped.startswith("#"):
                j += 1
                continue
            # If we hit a line at or below the function's own indent that's
            # NOT inside our function (i.e. dedented), stop.
            cur_indent = len(ln) - len(ln.lstrip())
            if cur_indent <= len(indent) and stripped != "":
                break
            # Detect the nested `async def run():`
            m_run = RUN_DEF_RE.match(ln)
            if m_run and m_run.group(1) == body_indent:
                run_start = j
                break
            j += 1

        if run_start is None:
            out.append(line)
            i += 1
            continue

        # Find the matching run_until_complete call after the `async def run`.
        run_call = None
        k = run_start + 1
        while k < len(lines):
            ln = lines[k]
            m_call = RUN_CALL_RE.match(ln)
            if m_call and m_call.group(1) == body_indent:
                run_call = k
                break
            k += 1
        if run_call is None:
            # Pattern broken — bail out for this function.
            out.append(line)
            i += 1
            continue

        # Lines BEFORE the `async def run():` (typically the docstring or
        # setup statements at body_indent) stay as-is. Lines INSIDE the run
        # function (between run_start+1 and run_call-1) get dedented by 4.
        # Lines AFTER run_call are after the function body and we just skip
        # the run_call line itself.

        # 1) Emit the converted def line: `def test_foo(args):` -> `async def test_foo(args):`
        out.append(f"{indent}async def {test_name}({args}):")
        # 2) Emit lines i+1 .. run_start-1 unchanged (anything before `async def run():`)
        for src_idx in range(i + 1, run_start):
            out.append(lines[src_idx])
        # 3) Skip the `async def run():` line entirely
        # 4) Dedent body lines [run_start+1 .. run_call-1] by 4 spaces (strip body_indent's last 4)
        for src_idx in range(run_start + 1, run_call):
            ln = lines[src_idx]
            if ln.startswith("    "):
                out.append(ln[4:])
            else:
                out.append(ln)
        # 5) Skip the run_call line
        # Continue scanning from after the run_call line
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
