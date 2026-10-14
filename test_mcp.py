#!/usr/bin/env python3
"""Automated verification suite for cint-mcp server."""

import json
import subprocess
import sys


def test_mcp_server():
    p = subprocess.Popen(
        [sys.executable, "cint_mcp_server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    def send_recv(req):
        p.stdin.write(json.dumps(req) + "\n")
        p.stdin.flush()
        line = p.stdout.readline()
        return json.loads(line)

    # 1. Initialize
    init_res = send_recv({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"}
        }
    })
    assert init_res["result"]["serverInfo"]["name"] == "cint-mcp", f"Init failed: {init_res}"
    print("PASS: initialize")

    # 2. Tools list
    tools_res = send_recv({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tools = {t["name"] for t in tools_res["result"]["tools"]}
    assert "cint_search_docs" in tools
    assert "cint_lookup_diagnostic" in tools
    assert "cint_get_recipe" in tools
    assert "cint_check" in tools
    assert "cint_eval" in tools
    print(f"PASS: tools/list ({len(tools)} tools registered)")

    # 3. Search docs
    search_res = send_recv({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "cint_search_docs", "arguments": {"query": "muldiv", "limit": 2}}
    })
    assert not search_res["result"].get("isError")
    assert "muldiv" in search_res["result"]["content"][0]["text"].lower()
    print("PASS: cint_search_docs")

    # 4. Lookup diagnostic
    diag_res = send_recv({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "cint_lookup_diagnostic", "arguments": {"code": "C1001"}}
    })
    assert not diag_res["result"].get("isError")
    assert "C1001" in diag_res["result"]["content"][0]["text"]
    print("PASS: cint_lookup_diagnostic (C1001)")

    # 5. Get recipe
    rec_res = send_recv({
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "cint_get_recipe", "arguments": {"name": "fixed-point-trig"}}
    })
    assert not rec_res["result"].get("isError")
    assert "recipe" in rec_res["result"]["content"][0]["text"].lower()
    print("PASS: cint_get_recipe (fixed-point-trig)")

    # 6. Resources list and read
    res_list = send_recv({"jsonrpc": "2.0", "id": 6, "method": "resources/list", "params": {}})
    assert len(res_list["result"]["resources"]) >= 5
    print(f"PASS: resources/list ({len(res_list['result']['resources'])} resources)")

    res_read = send_recv({
        "jsonrpc": "2.0",
        "id": 7,
        "method": "resources/read",
        "params": {"uri": "cint://cheat-sheet"}
    })
    assert "cint" in res_read["result"]["contents"][0]["text"].lower()
    print("PASS: resources/read (cint://cheat-sheet)")

    p.stdin.close()
    p.terminate()
    print("\nALL 6 VERIFICATIONS PASSED!")


if __name__ == "__main__":
    test_mcp_server()
