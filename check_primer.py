#!/usr/bin/env python3
"""Check PRIMER.md against a `cint`: every fenced block of the page is compiled or run.

The block forms:

    ```ci run [-- WORD...]   cint run exits 0; stdout equals the `output` block that follows
    ```ci error CODE         cint run exits 2; its first diagnostic has CODE
    ```ci fault E_NAME       cint run exits 1 with that fault; stdout equals a following `output` block
    ```ci test               cint test exits 0
    ```ci module PATH        one more module of the next checked block
    ```names                 each name is a compile error as the name of a local variable
    ```output                the exact stdout of the checked block before it
    ```text, ```sh           not checked

A `ci` block with no mode fails the check, so the page holds no unchecked example.

    python check_primer.py --cint PATH [--page FILE] [--verbose]

Exit status 0 when every block holds, 1 when one does not, 2 on a usage error.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PAGE = Path(__file__).resolve().parent / "PRIMER.md"
FENCE = re.compile(r"^```(.*)$")
CODE = re.compile(r"^C\d{4}$")
FAULT = re.compile(r"^E_[A-Z0-9_]+$")
MODULE = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*/)*[A-Za-z_][A-Za-z0-9_]*\.ci$")
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
UNCHECKED = ("text", "sh")
TIMEOUT = 300


class PageError(Exception):
    """The page itself is malformed: a block the check cannot read."""


def blocks(text):
    """The fenced blocks of the page, in order: (line of the opening fence, info string, body)."""
    found = []
    opened = None
    for number, line in enumerate(text.split("\n"), 1):
        fence = FENCE.match(line)
        if opened is None:
            if fence:
                opened = (number, fence.group(1).strip(), [])
        elif fence and not fence.group(1).strip():
            found.append((opened[0], opened[1], "\n".join(opened[2]) + "\n"))
            opened = None
        else:
            opened[2].append(line)
    if opened is not None:
        raise PageError("line %d: a fenced block is not closed" % opened[0])
    return found


def cases(text):
    """The checks of the page: dictionaries with line, mode, the mode's argument, source, modules,
    program arguments and the expected stdout (None when no `output` block follows)."""
    found = []
    modules = {}
    last = None
    for line, info, body in blocks(text):
        words = info.split()
        kind = words[0] if words else ""
        if kind == "output":
            if last is None or last["output"] is not None or last["mode"] not in ("run", "fault"):
                raise PageError("line %d: an `output` block follows no `ci run` or `ci fault` block" % line)
            last["output"] = body
            last = None
            continue
        last = None
        if kind in UNCHECKED:
            continue
        if kind == "names":
            names = body.split()
            bad = [name for name in names if not NAME.match(name)]
            if bad or not names:
                raise PageError("line %d: a `names` block holds identifiers; found %r" % (line, bad[:3]))
            found.append({"line": line, "mode": "names", "names": names})
            continue
        if kind != "ci":
            raise PageError("line %d: unknown block `%s`; the forms are ci, names, output, text and sh" % (line, info))
        mode = words[1] if len(words) > 1 else ""
        rest = words[2:]
        if mode == "module":
            if len(rest) != 1 or not MODULE.match(rest[0]):
                raise PageError("line %d: `ci module` takes one module path such as geo/vec.ci" % line)
            modules[rest[0]] = body
            continue
        case = {"line": line, "mode": mode, "want": None, "source": body, "modules": modules, "args": [],
                "output": None}
        modules = {}
        if mode == "run":
            if rest and rest[0] != "--":
                raise PageError("line %d: `ci run` takes nothing, or `--` and the program arguments" % line)
            case["args"] = rest[1:]
        elif mode == "error":
            if len(rest) != 1 or not CODE.match(rest[0]):
                raise PageError("line %d: `ci error` takes one code such as C3001" % line)
            case["want"] = rest[0]
        elif mode == "fault":
            if len(rest) != 1 or not FAULT.match(rest[0]):
                raise PageError("line %d: `ci fault` takes one fault name such as E_OVERFLOW" % line)
            case["want"] = rest[0]
        elif mode == "test":
            if rest:
                raise PageError("line %d: `ci test` takes nothing" % line)
        else:
            raise PageError("line %d: a `ci` block needs a mode: run, error CODE, fault E_NAME, test or module PATH"
                            % line)
        found.append(case)
        last = case if mode in ("run", "fault") else None
    if modules:
        raise PageError("a `ci module` block is followed by no checked block")
    for case in found:
        if case["mode"] == "run" and case["output"] is None:
            raise PageError("line %d: a `ci run` block needs the `output` block of what it prints" % case["line"])
    return found


def records(stderr):
    """The JSON Lines of a `cint --json` stderr."""
    found = []
    for line in stderr.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            found.append(record)
    return found


def invoke(cint, command, directory, cache, arguments=()):
    words = [str(cint), "--json", command, "--cache", str(cache), "main.ci"]
    if arguments:
        words += ["--", *arguments]
    done = subprocess.run(words, cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=TIMEOUT,
                          stdin=subprocess.DEVNULL)
    return done.returncode, done.stdout.decode("utf-8", "replace"), done.stderr.decode("utf-8", "replace")


def first_code(stderr, schema):
    return next((r.get("code") for r in records(stderr) if r.get("schema") == schema), None)


def check_case(cint, case, work, cache):
    """None when the case holds, else one sentence saying how it does not."""
    directory = Path(tempfile.mkdtemp(prefix="case-", dir=work))
    if case["mode"] == "names":
        refused = []
        for name in case["names"]:
            (directory / "main.ci").write_text('void main() {\n    I64 %s = 1;\n    "{%s}\\n";\n}\n' % (name, name),
                                               encoding="utf-8", newline="\n")
            status, _out, _err = invoke(cint, "run", directory, cache)
            if status != 2:
                refused.append(name)
        return "these names are accepted as a variable's name: %s" % " ".join(refused) if refused else None
    (directory / "main.ci").write_text(case["source"], encoding="utf-8", newline="\n")
    for path, source in case["modules"].items():
        target = directory / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8", newline="\n")
    command = "test" if case["mode"] == "test" else "run"
    status, out, err = invoke(cint, command, directory, cache, case["args"])
    said = err.strip().splitlines()[0][:300] if err.strip() else "nothing on stderr"
    if case["mode"] == "test":
        return None if status == 0 else "cint test exited %d: %s" % (status, said)
    if case["mode"] == "error":
        code = first_code(err, "CINT-DIAG-1")
        if status == 2 and code == case["want"]:
            return None
        return "wanted the compile error %s; exit status %d, first diagnostic %s: %s" % (case["want"], status, code, said)
    if case["mode"] == "fault":
        code = first_code(err, "CINT-FAULT-1")
        if status != 1 or code != case["want"]:
            return "wanted the fault %s; exit status %d, fault %s: %s" % (case["want"], status, code, said)
    elif status != 0:
        return "cint run exited %d: %s" % (status, said)
    if case["output"] is not None and out != case["output"]:
        return "stdout differs from the `output` block: wanted %r, got %r" % (case["output"][:400], out[:400])
    return None


def check(cint, page, verbose=False):
    text = page.read_text(encoding="utf-8")
    todo = cases(text)
    failures = []
    work = tempfile.mkdtemp(prefix="cint-primer-")
    try:
        cache = Path(work) / "cache"
        for case in todo:
            why = check_case(cint, case, work, cache)
            label = "%s:%d `%s`" % (page.name, case["line"], case["mode"] + (" " + case["want"] if case.get("want") else ""))
            if why is not None:
                failures.append("%s: %s" % (label, why))
            if verbose or why is not None:
                print(("FAIL " if why else "ok   ") + label + (": " + why if why else ""), flush=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    counts = {}
    for case in todo:
        counts[case["mode"]] = counts.get(case["mode"], 0) + 1
    names = sum(len(case["names"]) for case in todo if case["mode"] == "names")
    summary = ", ".join("%d %s" % (counts[mode], mode) for mode in ("run", "error", "fault", "test") if mode in counts)
    print("%s cint primer: %d blocks (%s) and %d reserved names, %d failed"
          % ("fail" if failures else "pass", len(todo) - counts.get("names", 0), summary, names, len(failures)))
    return not failures


def main():
    parser = argparse.ArgumentParser(description="Check every example of PRIMER.md against a cint.")
    parser.add_argument("--cint", default=os.environ.get("CINT_PATH"), help="the cint executable (default: CINT_PATH)")
    parser.add_argument("--page", default=str(PAGE), help="the page to check (default: PRIMER.md beside this file)")
    parser.add_argument("--verbose", action="store_true", help="print every block, not only the failures")
    arguments = parser.parse_args()
    if not arguments.cint or not Path(arguments.cint).is_file():
        print("usage: give --cint PATH (or set CINT_PATH) to a built cint; "
              "`python3 tools/cint_bootstrap.py --leg gcc` in cint-public-build builds one", file=sys.stderr)
        return 2
    try:
        return 0 if check(Path(arguments.cint).resolve(), Path(arguments.page), arguments.verbose) else 1
    except PageError as error:
        print("fail cint primer: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
