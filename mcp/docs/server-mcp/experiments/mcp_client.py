"""
Minimal MCP client for the experiments: calls tools of the mcp-verify MCP
server over streamable HTTP, as an AI client would.

    import mcp_client
    client = mcp_client.Client(token=mcpv.token("editor", "mcp"), executor="server")
    result = client.execute_code("return 1 + 1", fileId=...)

`executor="server"` asks for server-side execution (PEN-22); `"plugin"` for
the browser plugin path; None for the server's default.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request


class ToolError(Exception):
    """A tool call that came back as `Tool execution failed: ...`."""


class Client:
    def __init__(self, token, executor="server", base="http://localhost:4501/mcp"):
        query = {"userToken": token}
        if executor:
            query["executor"] = executor
        self.url = base + "?" + urllib.parse.urlencode(query)
        self.next_id = 1
        self.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "mcp-verify-experiment", "version": "0"}})

    def call(self, method, params, timeout=300):
        body = {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params}
        self.next_id += 1
        request = urllib.request.Request(self.url, data=json.dumps(body).encode(), method="POST",
                                         headers={"content-type": "application/json",
                                                  "accept": "application/json, text/event-stream"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode()
        # SSE: the JSON-RPC response is the data of the last message event
        payloads = [line[len("data: "):] for line in raw.splitlines() if line.startswith("data: ")]
        message = json.loads(payloads[-1] if payloads else raw)
        if "error" in message:
            raise RuntimeError(f"{method} failed: {message['error']}")
        return message["result"]

    def tool(self, name, **arguments):
        """Calls a tool; returns (text, seconds). Raises ToolError for a failed execution."""
        started = time.monotonic()
        result = self.call("tools/call", {"name": name, "arguments": arguments})
        elapsed = time.monotonic() - started
        text = "".join(item.get("text", "") for item in result.get("content", []))
        if text.startswith("Tool execution failed:"):
            raise ToolError(text)
        return text, elapsed

    def execute_code(self, code, **arguments):
        """Runs `execute_code`; returns (parsed JSON response, seconds)."""
        text, elapsed = self.tool("execute_code", code=code, **arguments)
        try:
            return json.loads(text), elapsed
        except ValueError:
            return text, elapsed
