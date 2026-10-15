# cint MCP Server (`cint-mcp`)

[![License](https://img.shields.io/badge/License-Apache%202.0%20with%20LLVM%20Exception-blue.svg)](LICENSE)
[![MCP Version](https://img.shields.io/badge/MCP-2024--11--05-green.svg)](https://modelcontextprotocol.io/)
[![cint Edition](https://img.shields.io/badge/cint-0.2.0-orange.svg)](https://integerc.dev)

Official public **Model Context Protocol (MCP)** server for **cint 0.2.0** (checked against compiler identity `d6ebe30d604346afe4a7912c5d6f3ce2b9d401641d361772892b44b9292609ff`).

Gives coding agents (Claude Code, Claude Desktop, Cursor, Windsurf, Copilot, etc.) instant in-memory access to:
* **Public Specifications (`SPEC-00P` through `SPEC-09P`)**
* **Diagnostic & Fault Catalogue (`C1001` through `C9102`, `E_OVERFLOW`, `E_ASSERT`, etc.)**
* **Verified `.ci` Recipes with cryptographic receipts**
* **cint University Curriculum (`CU-000.2` through `CU-401.2`)**
* **Native Toolchain Execution (`cint_check`, `cint_eval`, `cint_test`)** when a local `cint` binary is present

Zero external package dependencies — runs on standard Python 3.8+ on Linux, macOS, and Windows.

---

## Quick Setup

### 1. Claude Code CLI (Local or Cloud Sessions)

You can add this MCP server directly via Git or by cloning the repository:

#### Method A: Run directly from Git (using `uvx`)
```bash
claude mcp add cint -- uvx --from git+https://github.com/pennyleans/cint-mcp cint-mcp
```

#### Method B: In any project using `.mcp.json`
Add to your project's `.mcp.json`:
```json
{
  "mcpServers": {
    "cint": {
      "command": "python",
      "args": ["path/to/cint-mcp/cint_mcp_server.py"]
    }
  }
}
```

#### Method C: Global Claude Code configuration
```bash
claude mcp add cint -- python /path/to/cint-mcp/cint_mcp_server.py
```

---

### 2. Claude Desktop

Add to your `claude_desktop_config.json`:
* **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
* **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "cint": {
      "command": "python",
      "args": ["F:\\cint-mcp\\cint_mcp_server.py"]
    }
  }
}
```

---

### 3. Cursor / Windsurf

Add to `.cursor/mcp.json` or windsurf config:
```json
{
  "mcpServers": {
    "cint": {
      "command": "python",
      "args": ["cint_mcp_server.py"]
    }
  }
}
```

---

## Available Tools

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `cint_search_docs` | `query`, `scope`, `limit`, `verbose` | Search across specifications, glossary, errata, and university lessons |
| `cint_get_doc` | `id`, `verbose` | Retrieve a self-contained specification or lesson chunk |
| `cint_lookup_diagnostic` | `code`, `verbose` | Explain compile error codes (`C1001`–`C9102`) or runtime faults (`E_OVERFLOW`, `E_DIVZERO`) with repairs |
| `cint_get_recipe` | `name`, `verbose` | Fetch verified 0.2.0 `.ci` code recipes (`fixed-point-trig`, `money-ledger`, `fnv1a-digest`, etc.) |
| `cint_list_curriculum` | `course`, `verbose` | List curriculum lessons across `CU-000` to `CU-401` |
| `cint_check` | `source` | Compile `.ci` source without running it (`cint emit-c`) and return its diagnostics |
| `cint_eval` | `source` | Compile and run a program (`cint run`) and return its output or fault record |
| `cint_test` | `source` | Run the program's `test` blocks (`cint test`) |

The three execution tools need a local `cint`: on `PATH`, named by `CINT_PATH`, or the newest build under `CINT_BUILD/boot/<leg>`. `CINT_MCP_TIMEOUT` sets their time limit in seconds (default 120).

---

## Available Resources

| Resource URI | Description |
| :--- | :--- |
| `cint://manifest` | Public edition SHA-256 hashes and compiler source identity |
| `cint://from-c` | Quickstart guide for C programmers |
| `cint://from-python` | Quickstart guide for Python and NumPy developers |
| `cint://cheat-sheet` | Condensed cint 0.2.0 syntax, types, and rules |
| `cint://refusals` | Refused constructs catalogue under SPEC-09P.1 |

---

## License

Licensed under the **Apache License, Version 2.0 with LLVM Exceptions** matching the cint project.
See [LICENSE](LICENSE) for details.
