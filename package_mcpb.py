#!/usr/bin/env python3
"""Build cint.mcpb bundle for Claude Desktop / MCP clients."""

import json
import os
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

manifest = {
    "$schema": "https://raw.githubusercontent.com/modelcontextprotocol/mcpb/main/schemas/mcpb-manifest-latest.schema.json",
    "manifest_version": "0.3",
    "name": "cint",
    "display_name": "cint 0.2.0",
    "version": "0.2.0",
    "description": "Deterministic integer programming language specifications, diagnostics, recipes, and execution tools for cint 0.2.0.",
    "author": {"name": "pennyleans"},
    "icon": "icon.png",
    "server": {
        "type": "python",
        "entry_point": "cint_mcp_server.py",
        "mcp_config": {
            "command": "python",
            "args": ["${__dirname}/cint_mcp_server.py"]
        }
    }
}

out_path = SCRIPT_DIR / "cint.mcpb"
with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("manifest.json", json.dumps(manifest, indent=2))
    z.write(SCRIPT_DIR / "cint_mcp_server.py", "cint_mcp_server.py")
    z.write(SCRIPT_DIR / "corpus.json", "corpus.json")
    z.write(SCRIPT_DIR / "icon.png", "icon.png")

print(f"Packaged {out_path} ({os.path.getsize(out_path)/1024:.1f} KB)")
