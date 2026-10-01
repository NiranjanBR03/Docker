
import os
import hmac
import hashlib
import subprocess
import threading

from flask import Flask, request, jsonify, abort

app = Flask(__name__)

# Dedicated deployment checkout, NOT your development folder
REPO_DIR = r"D:\deploy\docker-pr-demo-deploy"
BRANCH = "main"

IMAGE_NAME = "docker-pr-demo:latest"
CONTAINER_NAME = "docker-pr-demo-local"

HOST_PORT = "5001"
CONTAINER_PORT = "5000"

WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
deploy_lock = threading.Lock()


def run_command(command):
    print("Running:", " ".join(command), flush=True)

    result = subprocess.run(
        command,
        cwd=REPO_DIR,
        capture_output=True,
        text=True
    )

    if result.stdout:
        print(result.stdout, flush=True)

    if result.stderr:
        print(result.stderr, flush=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )


def deploy():
    if not deploy_lock.acquire(blocking=False):
        print("Deployment already running; skipping.", flush=True)
        return

    try:
        print("Starting deployment...", flush=True)

        # Fetch the latest main branch
        run_command(["git", "fetch", "origin", BRANCH])
        run_command(["git", "reset", "--hard", f"origin/{BRANCH}"])

        # Build the new image BEFORE stopping the old container
        run_command([
            "docker", "build",
            "-t", IMAGE_NAME,
            "."
        ])

        # Replace only this demo container
        subprocess.run(
            ["docker", "rm", "-f", CONTAINER_NAME],
            capture_output=True,
            text=True
        )

        run_command([
            "docker", "run", "-d",
            "--name", CONTAINER_NAME,
            "--restart", "unless-stopped",
            "-p", f"{HOST_PORT}:{CONTAINER_PORT}",
            IMAGE_NAME
        ])

        print("Deployment completed.", flush=True)
        print("Demo URL: http://localhost:5001", flush=True)

    except Exception as error:
        print(f"DEPLOYMENT FAILED: {error}", flush=True)

    finally:
        deploy_lock.release()


@app.route("/health", methods=["GET"])
def health():
    return jsonify(status="ok"), 200


@app.route("/webhook", methods=["POST"])
def webhook():
    if not WEBHOOK_SECRET:
        abort(500, "Webhook secret is not configured.")

    signature = request.headers.get("X-Hub-Signature-256", "")
    body = request.get_data(cache=True)

    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        abort(403, "Invalid webhook signature.")

    event = request.headers.get("X-GitHub-Event", "")

    # GitHub sends this when the webhook is first created
    if event == "ping":
        return jsonify(status="pong"), 200

    if event != "push":
        return jsonify(status="ignored", reason="Unsupported event"), 200

    payload = request.get_json(silent=True) or {}

    # Deploy only pushes to main; this includes merges into main
    if payload.get("ref") != f"refs/heads/{BRANCH}":
        return jsonify(status="ignored", reason="Not main"), 200

    threading.Thread(target=deploy, daemon=True).start()

    return jsonify(status="accepted"), 202


if __name__ == "__main__":
    if not WEBHOOK_SECRET:
        raise SystemExit(
            "ERROR: Set GITHUB_WEBHOOK_SECRET before starting deploy.py"
        )

    app.run(
        host="127.0.0.1",
        port=9000,
        debug=False
    )