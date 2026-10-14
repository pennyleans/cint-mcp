#!/usr/bin/env python3
"""Reliable MCPB packager - writes clean manifest without shell interpolation."""

import json
import os
import shutil
import zipfile
from pathlib import Path


def build_bundle(repo_dir: Path, output_file: Path, name: str, display_name: str, desc: str, server_file: str, corpus_file: str):
    manifest = {
        "manifest_version": "0.3",
        "name": name,
        "display_name": display_name,
        "version": "0.2.0",
        "description": desc,
        "author": {
            "name": "pennyleans"
        },
        "icon": "icon.png",
        "server": {
            "type": "python",
            "entry_point": server_file,
            "mcp_config": {
                "command": "python",
                "args": [
                    f"${{__dirname}}/{server_file}"
                ]
            }
        }
    }

    with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
        z.write(repo_dir / server_file, server_file)
        z.write(repo_dir / corpus_file, corpus_file)
        icon_path = Path("c:/Users/dhwli/Documents/antigravity/busy-hertz/apple-touch-icon.png")
        if icon_path.exists():
            z.write(icon_path, "icon.png")

    print(f"Built {output_file} ({os.path.getsize(output_file)/1024:.1f} KB)")


def main():
    downloads = Path("C:/Users/dhwli/Downloads")

    # 1. Public
    pub_dir = Path("F:/cint-mcp")
    pub_mcpb = pub_dir / "cint.mcpb"
    build_bundle(
        repo_dir=pub_dir,
        output_file=pub_mcpb,
        name="cint",
        display_name="cint 0.2.0",
        desc="Deterministic integer programming language specifications, diagnostics, recipes, and execution tools for cint 0.2.0.",
        server_file="cint_mcp_server.py",
        corpus_file="corpus.json"
    )
    shutil.copy(pub_mcpb, downloads / "cint.mcpb")

    # 2. Private
    priv_dir = Path("F:/cint-mcp-priv")
    priv_mcpb = priv_dir / "cint-priv.mcpb"
    build_bundle(
        repo_dir=priv_dir,
        output_file=priv_mcpb,
        name="cint-internal",
        display_name="cint Internal Engineering",
        desc="Internal cint engineering MCP tools: U-edition specifications, architecture decisions (ADRs), roadmap, open questions, and execution tools.",
        server_file="cint_mcp_priv_server.py",
        corpus_file="corpus_internal.json"
    )
    shutil.copy(priv_mcpb, downloads / "cint-priv.mcpb")

    print("Copied both clean bundles to C:/Users/dhwli/Downloads/")


if __name__ == "__main__":
    main()
