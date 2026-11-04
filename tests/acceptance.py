"""Real Hermes discovery/dispatch and real DeadBolt, with fictional local effects only.

Run from Hermes's prepared environment. No model/provider calls or real profile.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import contextvars
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time

PLUGIN = Path(__file__).resolve().parents[1]


def acceptance(hermes, binary, work):
    home = work / "hermes-home"
    workspace = work / "workspace"
    workspace.mkdir()
    (home / "plugins").mkdir(parents=True)
    shutil.copytree(PLUGIN, home / "plugins" / "deadbolt", ignore=shutil.ignore_patterns(".git", "__pycache__"))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    os.environ["HERMES_HOME"] = str(home)
    os.environ.pop("HERMES_PROFILE", None)
    config = {"plugins": {"enabled": ["deadbolt"], "entries": {"deadbolt": {"settings": {
        "workspace": str(workspace), "run_id": "hermes-qa", "sidecar_port": port}}}}}
    (home / "config.yaml").write_text(json.dumps(config))
    sys.path.insert(0, str(hermes))
    from agent.secret_scope import set_secret_scope, reset_secret_scope
    from hermes_cli.plugins import discover_plugins
    from model_tools import handle_function_call
    from hermes_cli.version_info import get_version_info

    discover_plugins(force=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEADBOLT_")}
    env.update(DEADBOLT_TOKEN=secrets.token_hex(32), DEADBOLT_DB=str(work / "state.db"),
               DEADBOLT_EVENTS=str(work / "events.jsonl"))

    def operator(*args):
        return subprocess.run([str(binary), *args], env=env, capture_output=True,
                              text=True, timeout=15, check=True).stdout

    operator("ensure", "--agent", "hermes-qa", "--activity-renewal", "--lease-ttl-secs", "3600")
    operator("policy", "--agent", "hermes-qa", "--tools", "hermes_artifact_write_v1")
    operator("action", "require", "--agent", "hermes-qa", "--tool", "hermes_artifact_write_v1")
    credential = work / "admission"
    operator("credential", "issue", "--agent", "hermes-qa", "--id", "qa-dispatcher", "--out", str(credential))
    scope = set_secret_scope({"DEADBOLT_HERMES_ADMISSION_TOKEN": credential.read_text().strip()}, profile_home=str(home))
    process = None
    cases = []

    def start():
        proc = subprocess.Popen([str(binary), "serve", "--bind", f"127.0.0.1:{port}", "--lease-ttl-secs", "3600"],
                                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.1):
                    return proc
            except OSError:
                if proc.poll() is not None:
                    raise RuntimeError("test sidecar exited")
                time.sleep(.03)
        proc.terminate()
        proc.wait(timeout=10)
        raise RuntimeError("test sidecar not ready")

    def call(name, args):
        return json.loads(handle_function_call(name, args, task_id="qa", session_id="qa"))

    def prepare(path, content="Fictional reviewer artifact\n"):
        result = call("deadbolt_prepare_write", {"path": path, "content": content})
        assert result.get("prepared") is True, result
        assert not (workspace / path).exists()
        assert Path(result["review_file"]).stat().st_mode & 0o777 == 0o600
        return result

    def commit(request):
        return call("deadbolt_commit_write", {"request_id": request["request_id"]})

    def approve(request):
        inspection = operator("action", "inspect", "--file", request["review_file"])
        digest = re.search(r"sha256:[0-9a-f]{64}", inspection).group()
        operator("action", "approve", "--file", request["review_file"], "--fingerprint", digest)

    def denied(request, name):
        result = commit(request)
        assert result.get("admitted") is False and result.get("completed") is False, result
        cases.append({"case": name, "admitted": False, "output_created": False})

    try:
        process = start()
        first = prepare("approved.txt")
        cases.append({"case": "prepare_does_not_write", "output_created": False})
        denied(first, "no_operator_approval")
        approve(first)
        path = Path(first["review_file"])
        original = path.read_text()
        changed = json.loads(original)
        changed["arguments"]["path"] = "changed.txt"
        path.write_text(json.dumps(changed))
        denied(first, "changed_path_after_review")
        assert not (workspace / "changed.txt").exists()
        changed["arguments"]["path"] = "approved.txt"
        changed["arguments"]["content"] = "changed after review"
        path.write_text(json.dumps(changed))
        denied(first, "changed_content_after_review")
        path.write_text(original)
        result = commit(first)
        assert result.get("completed") is True, result
        assert (workspace / "approved.txt").read_text() == "Fictional reviewer artifact\n"
        cases.append({"case": "exact_reviewed_write", "admitted": True, "output_created": True})
        denied(first, "one_use_replay")

        second = prepare("outage.txt")
        approve(second)
        process.terminate()
        process.wait(timeout=10)
        process = None
        denied(second, "sidecar_outage")
        assert not (workspace / "outage.txt").exists()
        process = start()
        assert commit(second).get("completed") is True
        cases.append({"case": "operator_restart_preserves_pending_grant", "admitted": True, "output_created": True})

        third = prepare("missing-token.txt")
        approve(third)
        absent = set_secret_scope({}, profile_home=str(home))
        try:
            denied(third, "missing_profile_admission_secret")
        finally:
            reset_secret_scope(absent)
        invalid = set_secret_scope({"DEADBOLT_HERMES_ADMISSION_TOKEN": "dbw1-invalid"}, profile_home=str(home))
        try:
            denied(third, "invalid_admission_credential")
        finally:
            reset_secret_scope(invalid)
        assert not (workspace / "missing-token.txt").exists()

        parallel = prepare("parallel.txt")
        approve(parallel)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(contextvars.copy_context().run, commit, parallel) for _ in range(2)]
            results = [f.result(timeout=15) for f in futures]
        assert sum(r.get("completed") is True for r in results) == 1, results
        assert sum(r.get("admitted") is False for r in results) == 1, results
        cases.append({"case": "concurrent_commit_consumes_once", "completed_writes": 1})

        expiry = prepare("expired.txt")
        review = Path(expiry["review_file"])
        envelope = json.loads(review.read_text())
        envelope["expires_at"] = int(time.time()) + 2
        review.write_text(json.dumps(envelope))
        approve(expiry)
        time.sleep(2.1)
        denied(expiry, "expired_exact_action")
        assert not (workspace / "expired.txt").exists()

        existing = workspace / "existing.txt"
        existing.write_text("preserve this fictional original")
        overwrite = call("deadbolt_prepare_write", {"path": "existing.txt", "content": "replacement"})
        approve(overwrite)
        result = commit(overwrite)
        assert result == {"admitted": True, "completed": False, "outcome": "unknown",
                          "next_action": "Operator must inspect the destination. Do not retry or recreate this grant automatically."}, result
        assert existing.read_text() == "preserve this fictional original"
        cases.append({"case": "exclusive_create_refuses_overwrite", "admitted": True, "output_created": False})

        outside = work / "outside"
        outside.mkdir()
        (workspace / "link").symlink_to(outside, target_is_directory=True)
        symlink = prepare("link/escape.txt")
        approve(symlink)
        assert commit(symlink).get("completed") is False
        assert not list(outside.iterdir())
        cases.append({"case": "symlink_parent_refused", "output_created": False})

        killed = prepare("killed.txt")
        approve(killed)
        operator("kill", "--agent", "hermes-qa")
        denied(killed, "kill_blocks_already_approved_write")
        assert not (workspace / "killed.txt").exists()
        operator("ensure", "--agent", "hermes-qa")
        denied(killed, "ensure_does_not_resurrect_killed_run")
        incident = json.loads(operator("incident", "--agent", "hermes-qa", "--json"))
        assert incident
        return {"hermes_revision": subprocess.check_output(["git", "-C", str(hermes), "rev-parse", "HEAD"], text=True).strip(),
                "hermes_release": get_version_info().display_version,
                "python_version": platform.python_version(),
                "deadbolt_version": operator("--version").strip(),
                "deadbolt_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                "cases": cases, "model_calls": 0, "scope": "Real Hermes discovery and handle_function_call dispatch; no model conversation or whole-agent containment"}
    finally:
        reset_secret_scope(scope)
        if process is not None:
            process.terminate()
            process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="deadbolt-hermes-plugin-") as directory:
        print(json.dumps(acceptance(args.hermes.resolve(), args.binary.resolve(), Path(directory).resolve()), indent=2))


if __name__ == "__main__":
    main()
