"""Exact-action text-artifact executor. Only this tool's own effect is gated."""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import time

TOOL = "hermes_artifact_write_v1"
SECRET = "DEADBOLT_HERMES_ADMISSION_TOKEN"
MAX_BYTES = 32768


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _encoded(value):
    data = json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_BYTES:
        raise ValueError("request too large")
    return data


def _relative(value):
    if type(value) is not str or not value or "\\" in value or "\x00" in value:
        raise ValueError("invalid relative path")
    parts = value.split("/")
    if any(p in ("", ".", "..") for p in parts) or PurePosixPath(value).is_absolute():
        raise ValueError("invalid relative path")
    return parts


def _create_file(arguments):
    """Anchor traversal to directory descriptors; refuse symlinks and overwrite."""
    parts = _relative(arguments["path"])
    directory = os.open(arguments["workspace"], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        with os.fdopen(fd, "wb") as output:
            output.write(arguments["content"].encode("utf-8"))
            output.flush()
            os.fsync(output.fileno())
    finally:
        os.close(directory)
    return {"path": arguments["path"], "bytes": len(arguments["content"].encode("utf-8"))}


class ArtifactWriter:
    def __init__(self, get_config):
        self.get_config = get_config

    def _settings(self):
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
            raise ValueError("requires a supported POSIX host")
        workspace = self.get_config("workspace", "")
        run = self.get_config("run_id", "")
        port = self.get_config("sidecar_port", 9782)
        if type(workspace) is not str or not Path(workspace).is_absolute():
            raise ValueError("workspace must be absolute")
        root = Path(workspace).resolve(strict=True)
        if not root.is_dir() or type(run) is not str or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", run):
            raise ValueError("invalid workspace or run")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("invalid port")
        return str(root), run, port

    def _requests(self):
        # Public profile-aware storage API. Files contain review text, not credentials.
        from plugins.plugin_storage import plugin_data_dir
        directory = plugin_data_dir("deadbolt") / "requests"
        directory.mkdir(mode=0o700, exist_ok=True)
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
            raise ValueError("review directory must be private")
        return directory

    def prepare(self, args, **kwargs):
        try:
            if type(args) is not dict or set(args) != {"path", "content"} or type(args["content"]) is not str:
                raise ValueError("expected path and content")
            _relative(args["path"])
            workspace, run, _ = self._settings()
            nonce = secrets.token_hex(16)
            action = {"version": 1, "agent_id": run, "tool": TOOL, "dest": None,
                      "arguments": {"workspace": workspace, **args},
                      "nonce": nonce, "expires_at": int(time.time()) + 300}
            data = _encoded(action)
            path = self._requests() / f"{nonce}.json"
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as output:
                output.write(data)
            return json.dumps({"prepared": True, "request_id": nonce, "review_file": str(path),
                               "expires_at": action["expires_at"], "output_created": False,
                               "next_action": "Operator reviews this exact file with deadbolt action inspect, then approves its displayed fingerprint outside the agent. Preparation is not approval."})
        except Exception:
            return json.dumps({"prepared": False, "error": "invalid_request_or_configuration",
                               "output_created": False})

    def _load(self, request_id, workspace, run):
        if type(request_id) is not str or not re.fullmatch(r"[a-f0-9]{32}", request_id):
            raise ValueError("invalid request ID")
        fd = os.open(self._requests() / f"{request_id}.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ValueError("not a regular review file")
            raw = source.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("request too large")
        action = json.loads(raw, object_pairs_hook=_strict_object)
        if type(action) is not dict or set(action) != {"version", "agent_id", "tool", "dest", "arguments", "nonce", "expires_at"}:
            raise ValueError("invalid envelope")
        a = action["arguments"]
        if action["agent_id"] != run or action["tool"] != TOOL or action["dest"] is not None or action["nonce"] != request_id:
            raise ValueError("wrong execution identity")
        if type(a) is not dict or set(a) != {"workspace", "path", "content"} or a["workspace"] != workspace or type(a["content"]) is not str:
            raise ValueError("invalid effect arguments")
        _relative(a["path"])
        _encoded(action)
        return action

    @staticmethod
    def _admit(action, port):
        # Only the active Hermes profile supplies a scoped admission credential.
        from agent.secret_scope import get_secret
        token = get_secret(SECRET)
        if not token or not token.startswith("dbw1-"):
            return {"decision": "deny", "code": "missing_admission_credential"}
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("POST", "/admit-action", body=_encoded(action),
                               headers={"Content-Type": "application/json", "X-Deadbolt-Admission": token})
            response = connection.getresponse()
            data = response.read(MAX_BYTES + 1)
            if response.status != 200 or len(data) > MAX_BYTES:
                return {"decision": "deny", "code": "sidecar_rejected"}
            result = json.loads(data, object_pairs_hook=_strict_object)
            if type(result) is not dict or result.get("decision") not in ("allow", "deny"):
                raise ValueError("invalid sidecar response")
            return {"decision": result["decision"], "code": str(result.get("code", "unknown"))[:128]}
        finally:
            connection.close()

    def commit(self, args, **kwargs):
        try:
            if type(args) is not dict or set(args) != {"request_id"}:
                raise ValueError("expected request ID")
            workspace, run, port = self._settings()
            action = self._load(args["request_id"], workspace, run)
            decision = self._admit(action, port)
            if decision["decision"] != "allow":
                return json.dumps({"admitted": False, "completed": False, "decision": decision,
                                   "next_action": "Stop. Ask the operator; do not fall back to another file tool."})
        except Exception:
            return json.dumps({"admitted": False, "completed": False, "error": "request_or_sidecar_unavailable"})
        try:
            result = _create_file(action["arguments"])
            return json.dumps({"admitted": True, "completed": True, "result": result})
        except Exception:
            # Admission is consumed. A filesystem error can leave partial output.
            return json.dumps({"admitted": True, "completed": False, "outcome": "unknown",
                               "next_action": "Operator must inspect the destination. Do not retry or recreate this grant automatically."})
