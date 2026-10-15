#!/usr/bin/env python3
"""cint 0.2.0 MCP (Model Context Protocol) Server.

Provides AI coding agents (Claude Code, Claude Desktop, Cursor, Windsurf, etc.)
with direct access to cint 0.2.0 specifications, diagnostic definitions,
recipes, curriculum, and execution tools.

The execution tools need a local `cint`: CINT_PATH, PATH, or the newest build
under CINT_BUILD/boot/<leg>. CINT_MCP_TIMEOUT sets their time limit in seconds
(default 120).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

SERVER_NAME = "cint-mcp"
SERVER_VERSION = "0.2.0"
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

SCRIPT_DIR = Path(__file__).resolve().parent
# Beside this file in a checkout or bundle; under sys.prefix when installed with pip or uvx
# (pyproject.toml installs the corpus as a data file).
CORPUS_PATH = next((p for p in (SCRIPT_DIR / "corpus.json", Path(sys.prefix) / "corpus.json") if p.exists()),
                   SCRIPT_DIR / "corpus.json")

# Load corpus
if not CORPUS_PATH.exists():
    sys.stderr.write(f"Error: corpus.json not found at {CORPUS_PATH}\n")
    sys.exit(1)

with open(CORPUS_PATH, "r", encoding="utf-8") as f:
    CORPUS = json.load(f)

MANIFEST = CORPUS.get("manifest", {})
CHUNKS = CORPUS.get("chunks", [])
RECIPES_LIST = CORPUS.get("recipes", [])
DIAGNOSTICS_LIST = CORPUS.get("diagnostics", [])
LESSONS_LIST = CORPUS.get("lessons", [])
RESOURCES = CORPUS.get("resources", {})
RESOURCES_META = CORPUS.get("resources_meta", [])

# Build indexes for O(1) lookup
CHUNK_BY_ID = {c.get("id", ""): c for c in CHUNKS}
DIAG_BY_CODE = {d.get("code", "").upper(): d for d in DIAGNOSTICS_LIST}
RECIPE_BY_ID = {r.get("id", ""): r for r in RECIPES_LIST}


class ToolError(Exception):
    """A failure returned to the client as an error result (isError true)."""


def find_cint_binary() -> Optional[str]:
    """Locate cint: CINT_PATH, then PATH, then the newest build under CINT_BUILD/boot/<leg>."""
    env_cint = os.environ.get("CINT_PATH")
    if env_cint and os.path.isfile(env_cint) and os.access(env_cint, os.X_OK):
        return env_cint

    for name in ("cint", "cint.exe"):
        found = shutil.which(name)
        if found:
            return found

    roots = [Path(os.environ["CINT_BUILD"])] if os.environ.get("CINT_BUILD") else []
    roots.append(Path(tempfile.gettempdir()) / "cint-build")
    builds = [root / "boot" / leg / name for root in roots for leg in ("msvc", "clang", "gcc")
              for name in ("cint", "cint.exe")]
    builds = [p for p in builds if p.is_file() and os.access(str(p), os.X_OK)]
    if builds:
        return str(max(builds, key=lambda p: p.stat().st_mtime))
    return None


def compact_text(text: str, max_chars: int = 1500) -> str:
    """Compact text if it exceeds maximum character budget."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n... (truncated; pass verbose=true for full text)"


def score_chunk(c: Dict[str, Any], terms: List[str]) -> int:
    cid = c.get("id", "").lower()
    ctitle = c.get("title", "").lower()
    cclauses = c.get("clauses", "").lower()
    ccontent = c.get("content", "").lower()
    s = 0
    for t in terms:
        if not t:
            continue
        if t in cid:
            s += 8
        if t in ctitle:
            s += 5
        if t in cclauses:
            s += 6
        if t in ccontent:
            s += 2
    return s


# Tools definition
TOOLS: List[Dict[str, Any]] = [
    {
        "name": "cint_search_docs",
        "description": "Search across cint 0.2.0 specifications (SPEC-00P to SPEC-09P), GLOSSARY, ERRATA, and University curriculum (CU-000 to CU-401). Compact output by default.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords, clause names, or error codes (e.g. 'muldiv', 'overflow', 'C1001')"},
                "scope": {"type": "string", "description": "Optional scope filter: 'spec' (specifications, glossary, references, errata), 'curriculum', or 'diagnostic' (the diagnostic and fault catalogue)"},
                "limit": {"type": "integer", "description": "Max results to return (1-20, default: 5)"},
                "verbose": {"type": "boolean", "description": "If true, return extended chunk content rather than compact summaries"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "cint_get_doc",
        "description": "Retrieve one self-contained specification or curriculum chunk by the ID cint_search_docs returns (e.g. 'spec-04p:scope', 'cu-201-04:muldiv').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Exact chunk ID as returned by cint_search_docs"},
                "verbose": {"type": "boolean", "description": "If true, return unabridged chunk text"}
            },
            "required": ["id"]
        }
    },
    {
        "name": "cint_lookup_diagnostic",
        "description": "Explain any compile diagnostic (C1001 to C9102) or runtime fault (E_OVERFLOW to E_ASSERT) with before/after fixes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Diagnostic or fault code (e.g. 'C1001', 'C3005', 'C9102', 'E_OVERFLOW')"},
                "verbose": {"type": "boolean", "description": "Accepted for compatibility; the answer is always complete"}
            },
            "required": ["code"]
        }
    },
    {
        "name": "cint_get_recipe",
        "description": "Fetch a verified cint 0.2.0 code recipe (fixed-point-trig, fixed-point-ln-sqrt, wide-i1024-scaling, svg-generator, fnv1a-digest, money-ledger, kernel-double-buffer) with digest.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Recipe name or keyword (e.g. 'fixed-point-trig', 'money-ledger')"},
                "verbose": {"type": "boolean", "description": "If true, include the recipe's explanation"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "cint_list_curriculum",
        "description": "List available cint University lessons (CU-000.2 to CU-401.2).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "course": {"type": "string", "description": "Course ID filter (e.g. 'CU-000', 'CU-101', 'CU-201', 'CU-301', 'CU-401')"},
                "verbose": {"type": "boolean", "description": "If true, include detailed lesson objectives"}
            }
        }
    },
    {
        "name": "cint_check",
        "description": "Compile cint (.ci) source without running it (`cint emit-c`) and return its CINT-DIAG-1 diagnostics, or 'compiles'. Needs a local cint (PATH or CINT_PATH); look codes up with cint_lookup_diagnostic.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Complete .ci source code string to check"}
            },
            "required": ["source"]
        }
    },
    {
        "name": "cint_eval",
        "description": "Compile and run a cint (.ci) program (`cint run`) and return its output, or its CINT-DIAG-1 diagnostic or CINT-FAULT-1 fault record. A program is `void main() { ... }` or top-level statements. Needs a local cint (PATH or CINT_PATH).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Complete .ci source code string"}
            },
            "required": ["source"]
        }
    },
    {
        "name": "cint_test",
        "description": "Run the `test \"name\" { ... }` blocks of cint (.ci) source (`cint test`) and return one CINT-TEST-1 line per test, with the fault record of each failure. Needs a local cint (PATH or CINT_PATH).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Complete .ci source code containing test blocks"}
            },
            "required": ["source"]
        }
    }
]


def handle_search_docs(params: Dict[str, Any]) -> str:
    query = params.get("query", "").strip()
    scope = params.get("scope", "").strip().lower()
    limit = min(max(int(params.get("limit", 5)), 1), 20)
    verbose = bool(params.get("verbose", False))

    if not query:
        raise ToolError("Please provide a search query.")

    terms = query.lower().split()
    scored = []
    for c in CHUNKS:
        cid = c.get("id", "").lower()
        if scope == "spec" and not cid.startswith(("spec-", "glossary", "references", "errata")):
            continue
        if scope == "curriculum" and not cid.startswith("cu-"):
            continue
        if scope == "diagnostic":
            continue
        s = score_chunk(c, terms)
        if s > 0:
            scored.append((s, c))
    if scope == "diagnostic":
        for d in DIAGNOSTICS_LIST:
            hay = " ".join(str(d.get(k, "")) for k in ("code", "meaning", "ai_cause", "spec")).lower()
            s = sum(2 for t in terms if t in hay)
            if s:
                scored.append((s, {"id": d.get("code", ""), "title": d.get("meaning", ""),
                                   "clauses": d.get("spec", ""), "content": d.get("ai_cause", "")}))

    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return f"No results found for query '{query}'."

    out = [f"Found {len(scored)} results for '{query}' (showing top {min(limit, len(scored))}):"]
    for s, c in scored[:limit]:
        cid = c.get("id", "")
        title = c.get("title", "")
        clauses = c.get("clauses", "")
        content = c.get("content", "").strip()
        preview = content if verbose else (content[:200] + "..." if len(content) > 200 else content)
        out.append(f"\n### {cid} - {title}\n*Clause:* {clauses}\n{preview}")

    return "\n".join(out)


def handle_get_doc(params: Dict[str, Any]) -> str:
    doc_id = params.get("id", "").strip()
    verbose = bool(params.get("verbose", False))
    if not doc_id:
        raise ToolError("Please specify a chunk id.")

    c = CHUNK_BY_ID.get(doc_id)
    if not c:
        # Case-insensitive / partial prefix lookup fallback
        for k, v in CHUNK_BY_ID.items():
            if k.lower() == doc_id.lower() or doc_id.lower() in k.lower():
                c = v
                break

    if not c:
        raise ToolError(f"Document chunk '{doc_id}' not found. Use cint_search_docs to locate valid chunk IDs.")

    content = c.get("content", "")
    if not verbose:
        content = compact_text(content, 1200)

    return f"# {c.get('id')} - {c.get('title')}\n*Clauses:* {c.get('clauses')}\n*Edition:* {c.get('edition')}\n\n{content}"


def handle_lookup_diagnostic(params: Dict[str, Any]) -> str:
    code = params.get("code", "").strip().upper()
    verbose = bool(params.get("verbose", False))
    if not code:
        raise ToolError("Please specify a diagnostic or fault code (e.g. 'C1001', 'E_OVERFLOW').")

    diag = DIAG_BY_CODE.get(code)
    if not diag:
        for k, v in DIAG_BY_CODE.items():
            if code in k:
                diag = v
                code = k
                break

    if not diag:
        raise ToolError(f"Diagnostic code '{code}' not recognized in cint 0.2.0 diagnostic catalogue.")

    meaning = diag.get("meaning", "")
    spec = diag.get("spec", "")
    ai_cause = diag.get("ai_cause", "")
    bad_ex = diag.get("bad_example", "")
    good_ex = diag.get("good_example", "")

    out = [f"**{code}**\n*Meaning:* {meaning}\n*Specification Citation:* {spec}"]
    if ai_cause:
        out.append(f"*Cause:* {ai_cause}")
    if bad_ex:
        out.append(f"*Incorrect:* `{bad_ex}`")
    if good_ex:
        out.append(f"*Repair:* `{good_ex}`")

    return "\n".join(out)


def handle_get_recipe(params: Dict[str, Any]) -> str:
    name = params.get("name", "").strip().lower()
    verbose = bool(params.get("verbose", False))
    available = ", ".join(RECIPE_BY_ID.keys())
    if not name:
        raise ToolError(f"Please specify a recipe name. Available recipes: {available}")

    matched = RECIPE_BY_ID.get(name)
    if not matched:
        for k, v in RECIPE_BY_ID.items():
            if name in k.lower():
                matched = v
                name = k
                break

    if not matched:
        raise ToolError(f"Recipe '{name}' not found. Available recipes: {available}")

    title = matched.get("title", name)
    code = matched.get("code", "")
    digest = matched.get("stdout_sha256", "")
    summary = matched.get("summary", "")
    specs = matched.get("specs", "")
    fuel = matched.get("fuel_consumed", "")

    out = [
        f"# Recipe: {name} - {title}",
        f"*Specs:* {specs} | *Fuel:* {fuel} | *Digest:* `{digest}`",
    ]
    if verbose and summary:
        out.append(f"\n{summary}")
    out.append(f"\n```cint\n{code}\n```")
    return "\n".join(out)


def handle_list_curriculum(params: Dict[str, Any]) -> str:
    course_filter = params.get("course", "").strip().upper()
    verbose = bool(params.get("verbose", False))

    lessons = LESSONS_LIST
    if course_filter:
        lessons = [l for l in lessons if course_filter in l.get("edition", "").upper() or course_filter in l.get("id", "").upper()]

    if not lessons:
        raise ToolError(f"No lessons found matching '{course_filter}'.")

    out = [f"### cint University Curriculum ({len(lessons)} lessons):"]
    for l in lessons:
        lid = l.get("id", "")
        title = l.get("title", "")
        edition = l.get("edition", "")
        builds = l.get("builds", "")
        line = f"- **{lid}** [{edition}]: {title}"
        if verbose and builds:
            line += f"\n  *Builds:* {builds}"
        out.append(line)
    return "\n".join(out)



CLI_EXIT = {0: "ok", 1: "runtime fault", 2: "compile error", 3: "test failed", 4: "usage error",
            5: "environment failure"}


def run_local_cint(mode: str, params: Dict[str, Any]) -> str:
    """Run `cint` on the source in a temporary root, by a relative file name, as the CLI requires."""
    source = params.get("source", "")
    if not source:
        raise ToolError("Please provide the complete .ci source code.")
    cint_bin = find_cint_binary()
    if not cint_bin:
        raise ToolError("No local cint found on PATH, in CINT_PATH, or under CINT_BUILD/boot/<leg>. "
                        "Install the cint toolchain or set CINT_PATH to run code.")
    try:
        timeout = max(5, int(os.environ.get("CINT_MCP_TIMEOUT", "120")))
    except ValueError:
        timeout = 120
    with tempfile.TemporaryDirectory(prefix="cint-mcp-") as tmp:
        with open(os.path.join(tmp, "snippet.ci"), "w", encoding="utf-8", newline="\n") as f:
            f.write(source)
        if mode == "check":
            args = ["--json", "emit-c", "--root", ".", "--out", os.path.join(tmp, "_emit"), "snippet.ci"]
        else:
            args = ["--json", mode, "snippet.ci"]
        try:
            res = subprocess.run([cint_bin] + args, cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ToolError(f"Execution timed out ({timeout} s; set CINT_MCP_TIMEOUT to allow longer).")
        except OSError as e:
            raise ToolError(f"Could not start {cint_bin}: {e}")
    code = res.returncode
    out = (res.stdout.decode("utf-8", "replace") + res.stderr.decode("utf-8", "replace")).strip()
    if code in (4, 5) or code not in CLI_EXIT:
        raise ToolError(f"cint failed: exit {code}, {CLI_EXIT.get(code, 'unexpected')}.\n{out}")
    if mode == "check" and code == 0:
        out = "compiles: no diagnostics (nothing was run)."
    return f"outcome: {CLI_EXIT[code]} (exit {code})" + (f"\n\n{out}" if out else "")


def handle_check(params: Dict[str, Any]) -> str:
    return run_local_cint("check", params)


def handle_eval(params: Dict[str, Any]) -> str:
    return run_local_cint("run", params)


def handle_test(params: Dict[str, Any]) -> str:
    return run_local_cint("test", params)


def execute_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if name == "cint_search_docs":
            text = handle_search_docs(args)
        elif name == "cint_get_doc":
            text = handle_get_doc(args)
        elif name == "cint_lookup_diagnostic":
            text = handle_lookup_diagnostic(args)
        elif name == "cint_get_recipe":
            text = handle_get_recipe(args)
        elif name == "cint_list_curriculum":
            text = handle_list_curriculum(args)
        elif name == "cint_check":
            text = handle_check(args)
        elif name == "cint_eval":
            text = handle_eval(args)
        elif name == "cint_test":
            text = handle_test(args)
        else:
            return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}

        return {"content": [{"type": "text", "text": text}], "isError": False}
    except ToolError as e:
        return {"content": [{"type": "text", "text": str(e)}], "isError": True}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Internal tool execution error: {e}"}], "isError": True}


def handle_request(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if "id" not in req:
        return None  # a notification gets no response
    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}

    def ok(result: Dict[str, Any]) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def fail(code: int, message: str) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    if method == "initialize":
        asked = params.get("protocolVersion")
        return ok({
            "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False},
                "prompts": {"listChanged": False}
            },
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": MANIFEST.get("instructions", "cint 0.2.0 deterministic integer language MCP server.")
        })
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        return ok(execute_tool(params.get("name", ""), params.get("arguments") or {}))
    if method == "resources/list":
        return ok({"resources": RESOURCES_META})
    if method == "resources/templates/list":
        return ok({"resourceTemplates": []})
    if method == "resources/read":
        uri = params.get("uri", "")
        text = RESOURCES.get(uri)
        if text is None:
            return fail(-32602, f"Resource URI not found: {uri}")
        mime_type = "application/json" if uri == "cint://manifest" else "text/markdown"
        return ok({"contents": [{"uri": uri, "mimeType": mime_type, "text": text}]})
    if method == "prompts/list":
        return ok({"prompts": []})
    return fail(-32601, f"Method not found: {method}")


def main():
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    while True:
        line = stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            resp = handle_request(req) if isinstance(req, dict) else None
        if resp is not None:
            stdout.write(json.dumps(resp).encode("utf-8") + b"\n")
            stdout.flush()


if __name__ == "__main__":
    main()
