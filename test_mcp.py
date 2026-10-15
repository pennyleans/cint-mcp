#!/usr/bin/env python3
"""Tests of cint-mcp over its stdio transport.

    python -m unittest test_mcp -v

The execution tests run a local cint only when CINT_PATH names one; otherwise they
check that the tools report that no cint was found.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parent / "cint_mcp_server.py"


class Server:
    def __init__(self, env):
        self.proc = subprocess.Popen([sys.executable, str(SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, env=env)
        self.next_id = 0

    def send(self, obj):
        self.proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def request(self, method, params=None):
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}})
        resp = json.loads(self.proc.stdout.readline())
        assert resp.get("id") == self.next_id, resp
        return resp

    def call(self, tool, **arguments):
        res = self.request("tools/call", {"name": tool, "arguments": arguments})["result"]
        return res["content"][0]["text"], bool(res.get("isError"))

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=20)
        self.proc.stdout.close()
        self.proc.stderr.close()


def start(cint_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CINT_")}
    env["CINT_BUILD"] = tempfile.gettempdir() + "/cint-mcp-test-no-build"
    if cint_path:
        env["CINT_PATH"] = cint_path
    else:
        env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep)
                                      if not (Path(p) / "cint").exists() and not (Path(p) / "cint.exe").exists())
    return Server(env)


class ProtocolAndCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = start(None)
        cls.init = cls.server.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                                     "clientInfo": {"name": "test", "version": "1"}})["result"]
        cls.server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def test_initialize(self):
        self.assertEqual(self.init["serverInfo"]["name"], "cint-mcp")
        self.assertEqual(self.init["protocolVersion"], "2024-11-05")

    def test_notification_gets_no_reply(self):
        self.server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual(self.server.request("ping")["result"], {})

    def test_tools_list(self):
        tools = {t["name"] for t in self.server.request("tools/list")["result"]["tools"]}
        self.assertEqual(tools, {"cint_search_docs", "cint_get_doc", "cint_lookup_diagnostic", "cint_get_recipe",
                                 "cint_list_curriculum", "cint_check", "cint_eval", "cint_test"})

    def test_search_scopes(self):
        text, err = self.server.call("cint_search_docs", query="muldiv", limit=2)
        self.assertFalse(err)
        self.assertIn("muldiv", text.lower())
        text, err = self.server.call("cint_search_docs", query="muldiv", scope="spec", limit=3)
        self.assertNotIn("No results", text)
        self.assertNotIn("### cu-", text)
        text, err = self.server.call("cint_search_docs", query="muldiv", scope="curriculum", limit=3)
        self.assertIn("### cu-", text)
        text, err = self.server.call("cint_search_docs", query="overflow", scope="diagnostic", limit=3)
        self.assertIn("E_OVERFLOW", text)

    def test_get_doc(self):
        text, err = self.server.call("cint_get_doc", id="spec-04p:scope")
        self.assertFalse(err)
        text, err = self.server.call("cint_get_doc", id="no-such-chunk")
        self.assertTrue(err)

    def test_diagnostic_and_recipe(self):
        text, err = self.server.call("cint_lookup_diagnostic", code="C1001")
        self.assertFalse(err)
        self.assertIn("C1001", text)
        text, err = self.server.call("cint_lookup_diagnostic", code="C0000")
        self.assertTrue(err)
        text, err = self.server.call("cint_get_recipe", name="fixed-point-trig")
        self.assertFalse(err)
        self.assertIn("```cint", text)
        text, err = self.server.call("cint_get_recipe", name="no-such-recipe")
        self.assertTrue(err)

    def test_resources(self):
        uris = {r["uri"] for r in self.server.request("resources/list")["result"]["resources"]}
        self.assertIn("cint://cheat-sheet", uris)
        text = self.server.request("resources/read", {"uri": "cint://cheat-sheet"})["result"]["contents"][0]["text"]
        self.assertIn("cint", text.lower())
        self.assertEqual(self.server.request("resources/read", {"uri": "cint://none"})["error"]["code"], -32602)

    def test_unknown(self):
        self.assertEqual(self.server.request("no/such")["error"]["code"], -32601)
        text, err = self.server.call("no_such_tool")
        self.assertTrue(err)

    def test_execution_without_cint(self):
        for tool in ("cint_check", "cint_eval", "cint_test"):
            text, err = self.server.call(tool, source="void main() { }")
            self.assertTrue(err, tool)
            self.assertIn("No local cint", text)


@unittest.skipUnless(os.environ.get("CINT_PATH"), "CINT_PATH names no cint")
class ExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = start(os.environ["CINT_PATH"])
        cls.server.request("initialize", {"protocolVersion": "2025-06-18"})

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def test_check(self):
        text, err = self.server.call("cint_check", source='void main() {\n    I64 x = 2;\n    "{x}\\n";\n}\n')
        self.assertFalse(err, text)
        self.assertIn("compiles", text)
        text, err = self.server.call("cint_check", source="void main() {\n    I64 x = 2\n}\n")
        self.assertFalse(err)
        self.assertIn("compile error (exit 2)", text)
        self.assertIn('"code":"C1050"', text)

    def test_eval(self):
        text, err = self.server.call("cint_eval", source='void main() {\n    I64 x = 6 * 7;\n    "answer={x}\\n";\n}\n')
        self.assertIn("ok (exit 0)", text)
        self.assertIn("answer=42", text)
        text, err = self.server.call("cint_eval", source='void main() {\n    I8 x = 100;\n    I8 y = x + x;\n    "{y}\\n";\n}\n')
        self.assertIn("runtime fault (exit 1)", text)
        self.assertIn('"code":"E_OVERFLOW"', text)

    def test_test(self):
        text, err = self.server.call("cint_test", source='I64 add(I64 a, I64 b) { return a + b; }\n'
                                     'test "adds" { assert(add(2, 3) == 5); }\n'
                                     'test "bad" { assert(add(2, 2) == 5); }\n')
        self.assertIn("test failed (exit 3)", text)
        self.assertIn('"passed":true', text)
        self.assertIn('"code":"E_ASSERT"', text)


if __name__ == "__main__":
    unittest.main()
