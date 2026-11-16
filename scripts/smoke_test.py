"""Smoke test for the Couch Owl Docker image: does the built container actually work?

Starts the image with a minimal configuration and checks what unit tests can't see:
health check, migrations on start, static files, non-root user, cron jobs, backups.

    uv run python scripts/smoke_test.py                       # build the image, then test it
    uv run python scripts/smoke_test.py --image couchowl:ci   # test an existing image
    uv run python scripts/smoke_test.py --image couchowl:ci --platform linux/arm64

Needs only Docker and the Python standard library. Used by CI (.github/workflows/ci.yml).
"""

import argparse
import json
import re
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTAINER = "couchowl-smoke-test"


class SmokeTestError(Exception):
    pass


def docker(*args: str, check: bool = True) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise SmokeTestError(f"docker {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def succeeds(*command: str) -> bool:
    """Run a command inside the container; True if it exits with 0."""
    result = subprocess.run(["docker", "exec", CONTAINER, *command], capture_output=True)
    return result.returncode == 0


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # report redirects as they are instead of following them


def get(url: str) -> tuple[int, dict[str, str], str]:
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(url, timeout=10) as response:
            return response.status, dict(response.headers), response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read().decode(errors="replace")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeTestError(message)
    print(f"  ok  {message}")


def wait_until_healthy(timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = json.loads(docker("inspect", "--format", "{{json .State}}", CONTAINER))
        if not state["Running"]:
            raise SmokeTestError(f"container stopped (exit code {state['ExitCode']})")
        if state.get("Health", {}).get("Status") == "healthy":
            return
        time.sleep(2)
    raise SmokeTestError(f"container not healthy after {timeout} s")


def run_checks(base_url: str, version: str) -> None:
    status, _, body = get(f"{base_url}/healthz/")
    health = json.loads(body)
    check(status == 200 and health["status"] == "ok", "/healthz/ reports ok")
    check(
        health["version"] == version,
        f"version {health['version']!r} matches pyproject.toml ({version!r})",
    )

    status, headers, _ = get(f"{base_url}/")
    check(
        status == 302 and "/accounts/login/" in headers.get("Location", ""),
        "/ redirects to the login page",
    )

    status, _, body = get(f"{base_url}/accounts/login/")
    check(status == 200, "login page loads (templates, database, migrations)")
    stylesheet = re.search(r'href="(/static/[^"]+\.css)"', body)
    check(stylesheet is not None, "login page links a stylesheet")
    status, _, _ = get(base_url + stylesheet.group(1))
    check(status == 200, f"static file {stylesheet.group(1)} is served")

    check(docker("exec", CONTAINER, "id", "-u") == "1000", "runs as uid 1000")
    check(not succeeds("touch", "/app/write-test"), "/app is read-only for the app user")
    check(succeeds("supercronic", "-test", "/app/docker/crontab"), "crontab is valid")
    check(succeeds("python", "manage.py", "backup"), "manage.py backup runs")
    backups = docker("exec", CONTAINER, "ls", "/data/backups").split()
    check(
        any(re.fullmatch(r"couchowl-\d{8}-\d{6}\.sqlite3", name) for name in backups),
        "backup file is in /data/backups",
    )

    state = json.loads(docker("inspect", "--format", "{{json .State}}", CONTAINER))
    check(state["Running"], "container still running (web and cron alive)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--image", help="image to test (default: build couchowl:smoke-test)")
    parser.add_argument("--platform", help="e.g. linux/arm64 (runs emulated via QEMU)")
    parser.add_argument("--timeout", type=int, default=180, help="seconds to become healthy")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # keep our output in order with Docker's

    with (ROOT / "pyproject.toml").open("rb") as f:
        version = tomllib.load(f)["project"]["version"]

    image = args.image
    platform = ["--platform", args.platform] if args.platform else []
    if not image:
        image = "couchowl:smoke-test"
        print(f"Building {image} …")
        subprocess.run(["docker", "build", *platform, "-t", image, str(ROOT)], check=True)

    health = ["--health-start-interval", "2s"]  # every 2 s while starting, not 30 s (Docker 25+)
    host_arch = docker("version", "--format", "{{.Server.Arch}}")
    if args.platform and args.platform.split("/")[1] != host_arch:
        # Emulated CPU (QEMU): Python alone needs several seconds to start the health check
        # (importing urllib.request takes ~6 s), more than the image's 5 s limit
        print(f"{args.platform} is emulated on {host_arch}: allowing 60 s per health check")
        health += ["--health-timeout", "60s"]

    docker("rm", "--force", CONTAINER, check=False)
    print(f"Starting {image} …")
    try:
        docker(
            "run", "--detach", "--name", CONTAINER, *platform, *health,
            "--publish", "127.0.0.1::8000",
            "--env", "SECRET_KEY=smoke-test-secret-key-not-for-production",
            "--env", "SITE_URL=http://localhost:8000",
            "--env", "TMDB_API_TOKEN=not-used",
            image,
        )  # fmt: skip
        port = docker("port", CONTAINER, "8000/tcp").splitlines()[0].rsplit(":", 1)[1]
        wait_until_healthy(args.timeout)
        print("Container is healthy, checking:")
        run_checks(f"http://127.0.0.1:{port}", version)
    except SmokeTestError as error:
        print(f"\nSMOKE TEST FAILED: {error}\n\nContainer logs:", file=sys.stderr)
        # The container writes its logs to stdout and stderr; show both
        subprocess.run(["docker", "logs", CONTAINER], stdout=sys.stderr, stderr=sys.stderr)
        return 1
    finally:
        docker("rm", "--force", "--volumes", CONTAINER, check=False)
    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
