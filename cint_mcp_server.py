#!/usr/bin/env python3
"""cint 0.2.0 MCP (Model Context Protocol) Server.

Provides AI coding agents (Claude Code, Claude Desktop, Cursor, Windsurf, etc.)
with direct access to cint 0.2.0 specifications, diagnostic definitions,
recipes, curriculum, and execution tools.
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
PROTOCOL_VERSION = "2024-11-05"

SCRIPT_DIR = Path(__file__).resolve().parent
CORPUS_PATH = SCRIPT_DIR / "corpus.json"

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



def find_cint_binary() -> Optional[str]:
    """Locate cint binary via CINT_PATH, PATH, or common default paths."""
    env_cint = os.environ.get("CINT_PATH")
    if env_cint and os.path.isfile(env_cint) and os.access(env_cint, os.X_OK):
        return env_cint

    which_cint = shutil.which("cint")
    if which_cint:
        return which_cint

    which_cinte = shutil.which("cint.exe")
    if which_cinte:
        return which_cinte

    # Common local Windows path
    win_path = Path("F:/cint-build/rc1/boot/msvc/cint.exe")
    if win_path.exists() and os.access(str(win_path), os.X_OK):
        return str(win_path)

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
                "scope": {"type": "string", "description": "Optional scope filter: 'spec', 'curriculum', or 'diagnostic'"},
                "limit": {"type": "integer", "description": "Max results to return (1-20, default: 5)"},
                "verbose": {"type": "boolean", "description": "If true, return extended chunk content rather than compact summaries"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "cint_get_doc",
        "description": "Retrieve one self-contained specification or curriculum chunk by ID (e.g. 'SPEC-04P.2:clause-7.2', 'CU-101.2:lesson-101-01').",
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
                "verbose": {"type": "boolean", "description": "If true, include all sample repairs and specification citations"}
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
                "verbose": {"type": "boolean", "description": "If true, include full receipt, fuel counts, and explanation"}
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
        "description": "Validate cint (.ci) source code and enrich diagnostics with spec citations and fix examples.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Complete .ci source code string to check"},
                "verbose": {"type": "boolean", "description": "If true, include full JSON AST and lowering diagnostics"}
            },
            "required": ["source"]
        }
    },
    {
        "name": "cint_eval",
        "description": "Compile cint (.ci) source and execute immediately on cpu-sir-interp, returning stdout, fuel consumed, or fault record.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Complete .ci source code string with void main() entry"},
                "fuel_limit": {"type": "integer", "description": "Optional execution fuel budget in units (default: 1000000)"},
                "verbose": {"type": "boolean", "description": "If true, include step counts and receipt digest"}
            },
            "required": ["source"]
        }
    },
    {
        "name": "cint_test",
        "description": "Run test and expect_fault blocks in .ci source via the cint test runner.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Complete .ci source code containing test blocks"},
                "verbose": {"type": "boolean", "description": "If true, include per-assertion trace"}
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
        return "Please provide a search query."

    terms = query.lower().split()
    scored = []
    for c in CHUNKS:
        cid = c.get("id", "")
        if scope == "spec" and not cid.startswith("SPEC-"):
            continue
        if scope == "curriculum" and not cid.startswith("CU-"):
            continue
        s = score_chunk(c, terms)
        if s > 0:
            scored.append((s, c))

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
        return "Please specify chunk id."

    c = CHUNK_BY_ID.get(doc_id)
    if not c:
        # Case-insensitive / partial prefix lookup fallback
        for k, v in CHUNK_BY_ID.items():
            if k.lower() == doc_id.lower() or doc_id.lower() in k.lower():
                c = v
                break

    if not c:
        return f"Document chunk '{doc_id}' not found. Use cint_search_docs to locate valid chunk IDs."

    content = c.get("content", "")
    if not verbose:
        content = compact_text(content, 1200)

    return f"# {c.get('id')} - {c.get('title')}\n*Clauses:* {c.get('clauses')}\n*Edition:* {c.get('edition')}\n\n{content}"


def handle_lookup_diagnostic(params: Dict[str, Any]) -> str:
    code = params.get("code", "").strip().upper()
    verbose = bool(params.get("verbose", False))
    if not code:
        return "Please specify a diagnostic or fault code (e.g. 'C1001', 'E_OVERFLOW')."

    diag = DIAG_BY_CODE.get(code)
    if not diag:
        for k, v in DIAG_BY_CODE.items():
            if code in k:
                diag = v
                code = k
                break

    if not diag:
        return f"Diagnostic code '{code}' not recognized in cint 0.2.0 diagnostic catalogue."

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
        return f"Please specify a recipe name. Available recipes: {available}"

    matched = RECIPE_BY_ID.get(name)
    if not matched:
        for k, v in RECIPE_BY_ID.items():
            if name in k.lower():
                matched = v
                name = k
                break

    if not matched:
        return f"Recipe '{name}' not found. Available recipes: {available}"

    title = matched.get("title", name)
    code = matched.get("code", "")
    digest = matched.get("stdout_sha256", "")
    summary = matched.get("summary", "")
    specs = matched.get("specs", "")
    fuel = matched.get("fuel_consumed", "")

    out = [
        f"# Recipe: {name} - {title}",
        f"*Specs:* {specs} | *Fuel:* {fuel} | *Digest:* `{digest}`",
        f"\n{summary}",
        f"\n```cint\n{code}\n```"
    ]
    return "\n".join(out)


def handle_list_curriculum(params: Dict[str, Any]) -> str:
    course_filter = params.get("course", "").strip().upper()
    verbose = bool(params.get("verbose", False))

    lessons = LESSONS_LIST
    if course_filter:
        lessons = [l for l in lessons if course_filter in l.get("edition", "").upper() or course_filter in l.get("id", "").upper()]

    if not lessons:
        return f"No lessons found matching '{course_filter}'."

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



def run_local_cint(cmd_args: List[str], source: str) -> Dict[str, Any]:
    cint_bin = find_cint_binary()
    if not cint_bin:
        return {
            "error": True,
            "text": "Local cint toolchain (cint.exe / cint) not found on PATH or CINT_PATH. To run code execution tools locally, install the cint toolchain or set CINT_PATH."
        }

    with tempfile.NamedTemporaryFile("w", suffix=".ci", delete=False, encoding="utf-8") as tf:
        tf.write(source)
        tf_name = tf.name

    try:
        res = subprocess.run(
            [cint_bin] + cmd_args + [tf_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        output = res.stdout if res.stdout else res.stderr
        return {"error": res.returncode != 0, "text": output}
    except subprocess.TimeoutExpired:
        return {"error": True, "text": "Execution timed out (10s limit exceeded)."}
    except Exception as e:
        return {"error": True, "text": f"Execution failed: {e}"}
    finally:
        try:
            os.remove(tf_name)
        except OSError:
            pass


def handle_check(params: Dict[str, Any]) -> str:
    source = params.get("source", "")
    if not source:
        return "Please provide .ci source code to check."
    res = run_local_cint(["emit-c", "--json"], source)
    return res["text"]


def handle_eval(params: Dict[str, Any]) -> str:
    source = params.get("source", "")
    if not source:
        return "Please provide .ci source code to evaluate."
    res = run_local_cint(["eval"], source)
    return res["text"]


def handle_test(params: Dict[str, Any]) -> str:
    source = params.get("source", "")
    if not source:
        return "Please provide .ci source code with test blocks."
    res = run_local_cint(["test", "--json"], source)
    return res["text"]


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
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Internal tool execution error: {e}"}], "isError": True}


def main():
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"listChanged": False},
                        "prompts": {"listChanged": False}
                    },
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION
                    },
                    "instructions": MANIFEST.get("instructions", "cint 0.2.0 deterministic integer language MCP server.")
                }
            }
        elif method == "notifications/initialized" or method == "ping":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOLS}
            }
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            tool_res = execute_tool(tool_name, tool_args)
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": tool_res
            }
        elif method == "resources/list":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"resources": RESOURCES_META}
            }
        elif method == "resources/read":
            uri = params.get("uri", "")
            text = RESOURCES.get(uri)
            if text is None:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": f"Resource URI not found: {uri}"}
                }
            else:
                mime_type = "application/json" if uri == "cint://manifest" else "text/markdown"
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "contents": [{"uri": uri, "mimeType": mime_type, "text": text}]
                    }
                }
        elif method == "prompts/list":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"prompts": []}
            }
        else:
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            }

        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
