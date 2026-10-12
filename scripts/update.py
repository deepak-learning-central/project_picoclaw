#!/usr/bin/env python3
#
# scripts/update.py
# Update the PicoClaw source clone and rebuild the Gateway image.
#
# Run this whenever you want to pull the latest PicoClaw changes and
# rebuild the full Docker image. The Gateway is restarted automatically.
#
# Usage:
#   python3 scripts/update.py
#   ./scripts/update.sh       # thin bash wrapper
#
import os
import subprocess
import sys
from pathlib import Path

REPO_URL = "https://github.com/sipeed/picoclaw.git"
REPO_DIR = Path("picoclaw")
COMPOSE_FILE = Path("docker-compose.yml")
GATEWAY_SERVICE = "picoclaw-gateway"


def docker_cmd() -> list[str]:
    """Return ['docker'] or ['sudo', 'docker'] depending on group permissions."""
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        print("Current shell session doesn't have docker group permissions yet — using sudo for this run")
        return ["sudo", "docker"]
    return ["docker"]


def main() -> None:
    if not (REPO_DIR / ".git").exists():
        print("ERROR: PicoClaw source not found at ./picoclaw/.")
        print("Run ./scripts/initialize.sh or ./setup.py first.")
        sys.exit(1)

    print("Updating PicoClaw source and rebuilding...")
    subprocess.run(["git", "-C", str(REPO_DIR), "pull", "--ff-only"], check=True)

    compose = docker_cmd()
    print("Rebuilding Gateway image...")
    subprocess.run(compose + ["compose", "build", GATEWAY_SERVICE], check=True)

    print("Restarting Gateway...")
    subprocess.run(compose + ["compose", "--profile", "gateway", "up", "-d", "--force-recreate"], check=True)

    print("Checking status...")
    subprocess.run(compose + ["compose", "--profile", "gateway", "ps"], check=True)
    print("Check logs with: docker compose --profile gateway logs -f")


if __name__ == "__main__":
    main()