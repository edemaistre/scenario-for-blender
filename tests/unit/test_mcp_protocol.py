# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json

from scenario.mcp import protocol

INFO = {"name": "scenario-blender", "version": "0.4.0"}


def _raise(err):
    raise err


def registry():
    reg = protocol.Registry()
    reg.add(protocol.ToolSpec("echo", "Echo arguments", {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}, lambda args: {"echo": args["text"]}))
    reg.add(protocol.ToolSpec("boom", "Always fails", {"type": "object", "properties": {}}, lambda args: _raise(RuntimeError("kaput"))))
    reg.add(protocol.ToolSpec("shot", "Image", {"type": "object", "properties": {}}, lambda args: {"_image": "aGk=", "mimeType": "image/png"}))
    return reg


def test_initialize_echoes_supported_version_and_lists_tools_capability():
    resp = protocol.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}, registry(), INFO)
    assert resp["id"] == 1 and resp["result"]["protocolVersion"] == "2025-03-26"
    assert resp["result"]["serverInfo"] == INFO and "tools" in resp["result"]["capabilities"]
    newer = protocol.handle_message({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "2099-01-01"}}, registry(), INFO)
    assert newer["result"]["protocolVersion"] == protocol.PROTOCOL_VERSIONS[0]


def test_notifications_return_none_and_ping_returns_empty_result():
    assert protocol.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}, registry(), INFO) is None
    assert protocol.handle_message({"jsonrpc": "2.0", "id": 3, "method": "ping"}, registry(), INFO)["result"] == {}


def test_tools_list_and_call_text_result():
    reg = registry()
    listed = protocol.handle_message({"jsonrpc": "2.0", "id": 4, "method": "tools/list"}, reg, INFO)["result"]["tools"]
    assert [t["name"] for t in listed] == ["echo", "boom", "shot"] and listed[0]["inputSchema"]["required"] == ["text"]
    called = protocol.handle_message({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "echo", "arguments": {"text": "hi"}}}, reg, INFO)
    content = called["result"]["content"]
    assert content[0]["type"] == "text" and json.loads(content[0]["text"]) == {"echo": "hi"}
    assert called["result"].get("isError") is not True


def test_tool_errors_and_unknown_tools():
    reg = registry()
    failed = protocol.handle_message({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "boom", "arguments": {}}}, reg, INFO)
    assert failed["result"]["isError"] is True and "kaput" in failed["result"]["content"][0]["text"]
    unknown = protocol.handle_message({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "nope"}}, reg, INFO)
    assert unknown["error"]["code"] == -32602
    missing = protocol.handle_message({"jsonrpc": "2.0", "id": 8, "method": "no/such"}, reg, INFO)
    assert missing["error"]["code"] == -32601
    bad = protocol.handle_message({"id": 9}, reg, INFO)
    assert bad["error"]["code"] == -32600


def test_image_results_and_executor_hook():
    reg = registry()
    shot = protocol.handle_message({"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "shot", "arguments": {}}}, reg, INFO)
    assert shot["result"]["content"][0] == {"type": "image", "data": "aGk=", "mimeType": "image/png"}
    seen = []

    def executor(handler, arguments):
        seen.append(arguments)
        return handler(arguments)

    protocol.handle_message({"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {"name": "echo", "arguments": {"text": "x"}}}, reg, INFO, executor=executor)
    assert seen == [{"text": "x"}]


def test_timeout_error_from_executor():
    def executor(handler, arguments):
        raise protocol.ToolTimeout("main thread busy")

    resp = protocol.handle_message({"jsonrpc": "2.0", "id": 12, "method": "tools/call", "params": {"name": "echo", "arguments": {"text": "x"}}}, registry(), INFO, executor=executor)
    assert resp["error"]["code"] == -32000 and "busy" in resp["error"]["message"]


def test_parse_body_errors():
    message, err = protocol.parse_body(b"{not json")
    assert message is None and err["error"]["code"] == -32700
    assert protocol.parse_body(b'{"jsonrpc":"2.0","id":1,"method":"ping"}')[0]["method"] == "ping"
