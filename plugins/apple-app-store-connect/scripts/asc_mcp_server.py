#!/usr/bin/env python3
"""Minimal stdio MCP server for App Store Connect release workflows."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "asc_cli.py"
SCREENSHOTS = ROOT / "scripts" / "generate_screenshots.py"


TOOLS = [
    {
        "name": "asc_doctor",
        "description": "Check local App Store Connect plugin prerequisites and configured credential environment variables.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "asc_field_map",
        "description": "Return the researched App Store Connect field map and automation coverage.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "asc_validate_submission_config",
        "description": "Validate an App Store submission JSON config against App Store metadata constraints.",
        "inputSchema": {
            "type": "object",
            "properties": {"configPath": {"type": "string"}},
            "required": ["configPath"],
        },
    },
    {
        "name": "asc_plan_submission_config",
        "description": "Show the App Store Connect API operations implied by a submission config without credentials.",
        "inputSchema": {
            "type": "object",
            "properties": {"configPath": {"type": "string"}},
            "required": ["configPath"],
        },
    },
    {
        "name": "asc_apply_metadata",
        "description": "Apply metadata from a submission config. Requires confirm=true and App Store Connect API credentials.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "configPath": {"type": "string"},
                "confirm": {"type": "boolean", "default": False},
            },
            "required": ["configPath"],
        },
    },
    {
        "name": "asc_list_apps",
        "description": "List apps visible to the configured App Store Connect API key.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "bundleId": {"type": "string"},
                "name": {"type": "string"},
            },
        },
    },
    {
        "name": "asc_upload_build_api",
        "description": "Upload an .ipa or .pkg through the App Store Connect Build Uploads API. Requires confirm=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "appId": {"type": "string"},
                "file": {"type": "string"},
                "versionString": {"type": "string"},
                "buildNumber": {"type": "string"},
                "platform": {"type": "string", "default": "IOS"},
                "waitSeconds": {"type": "integer", "default": 0},
                "confirm": {"type": "boolean", "default": False},
            },
            "required": ["appId", "file", "versionString", "buildNumber"],
        },
    },
    {
        "name": "asc_generate_screenshots",
        "description": "Render App Store screenshot composites from a screenshot-template JSON file.",
        "inputSchema": {
            "type": "object",
            "properties": {"configPath": {"type": "string"}},
            "required": ["configPath"],
        },
    },
]


def read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        line = line.decode("utf-8").strip()
        if not line:
            break
        key, value = line.split(":", 1)
        headers[key.lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


def write_message(message: dict[str, Any]) -> None:
    raw = json.dumps(message, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def run_command(args: list[str]) -> str:
    proc = subprocess.run(
        args,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    output = proc.stdout
    if proc.stderr:
        output += ("\n" if output else "") + proc.stderr
    if proc.returncode != 0:
        raise RuntimeError(output.strip() or f"Command failed with exit code {proc.returncode}")
    return output.strip()


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "asc_doctor":
        text = run_command(["python3", str(CLI), "doctor"])
    elif name == "asc_field_map":
        text = run_command(["python3", str(CLI), "field-map"])
    elif name == "asc_validate_submission_config":
        text = run_command(["python3", str(CLI), "validate", "--config", arguments["configPath"]])
    elif name == "asc_plan_submission_config":
        text = run_command(["python3", str(CLI), "plan", "--config", arguments["configPath"]])
    elif name == "asc_apply_metadata":
        command = ["python3", str(CLI), "apply-metadata", "--config", arguments["configPath"]]
        if arguments.get("confirm"):
            command.append("--yes")
        text = run_command(command)
    elif name == "asc_list_apps":
        command = ["python3", str(CLI), "list-apps"]
        if arguments.get("bundleId"):
            command += ["--bundle-id", arguments["bundleId"]]
        if arguments.get("name"):
            command += ["--name", arguments["name"]]
        text = run_command(command)
    elif name == "asc_upload_build_api":
        command = [
            "python3",
            str(CLI),
            "upload-build-api",
            "--app-id",
            arguments["appId"],
            "--file",
            arguments["file"],
            "--version-string",
            arguments["versionString"],
            "--build-number",
            arguments["buildNumber"],
            "--platform",
            arguments.get("platform", "IOS"),
            "--wait",
            str(arguments.get("waitSeconds", 0)),
        ]
        if arguments.get("confirm"):
            command.append("--yes")
        text = run_command(command)
    elif name == "asc_generate_screenshots":
        text = run_command(["python3", str(SCREENSHOTS), "--config", arguments["configPath"]])
    else:
        raise RuntimeError(f"Unknown tool: {name}")
    return {"content": [{"type": "text", "text": text}]}


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "apple-app-store-connect", "version": "1.0.0"},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = message.get("params", {})
            result = call_tool(params["name"], params.get("arguments", {}))
        elif method in {"notifications/initialized", "$/cancelRequest"}:
            return None
        else:
            raise RuntimeError(f"Unsupported MCP method: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32000, "message": str(exc)},
        }


def main() -> int:
    while True:
        message = read_message()
        if message is None:
            break
        response = handle(message)
        if response is not None and response.get("id") is not None:
            write_message(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
