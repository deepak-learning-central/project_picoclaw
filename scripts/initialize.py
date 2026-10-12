#!/usr/bin/env python3
#
# scripts/initialize.py
# First-time setup helper for pico-docker-setup.
#
# Performs the initial clone of the PicoClaw source, seeds the config
# directory from example templates, and prepares the project for the
# full setup.py execution.
#
# Usage:
#   python3 scripts/initialize.py
#   ./scripts/initialize.sh   # thin bash wrapper
#
import shutil
import subprocess
import sys
from pathlib import Path

REPO_URL = "https://github.com/sipeed/picoclaw.git"
REPO_DIR = Path("picoclaw")
CONFIG_DIR = Path("config")
CONFIG_FILE = CONFIG_DIR / "config.json"
SECURITY_FILE = CONFIG_DIR / ".security.yml"

SECURITY_TEMPLATE = """# PicoClaw secrets file.
#
# IMPORTANT — two different merge rules depending on the channel:
#   - Legacy/flat channels (e.g. telegram) accept a flat token:
#       channels:
#         telegram:
#           token: "..."
#   - Newer nested-settings channels (e.g. discord) do NOT merge correctly
#     under "channels:" — they must mirror config.json's exact path under
#     "channel_list:" instead:
#       channel_list:
#         discord:
#           settings:
#             token: "..."
# This inconsistency is a known quirk in the current codebase, not a typo.
#
# model_list secrets:
#   model_list:
#     <model_name>:0:
#       api_keys:
#         - "sk-..."
"""


def main() -> None:
    print("Initializing pico-docker-setup...")

    # 1. Clone PicoClaw if not present.
    if REPO_DIR.exists() and (REPO_DIR / ".git").exists():
        print("PicoClaw source already exists, updating...")
        subprocess.run(["git", "-C", str(REPO_DIR), "pull", "--ff-only"], check=True)
    else:
        print("Cloning PicoClaw source...")
        subprocess.run(["git", "clone", REPO_URL, str(REPO_DIR)], check=True)

    # 2. Ensure config directory exists.
    CONFIG_DIR.mkdir(exist_ok=True)

    # 3. Seed config.json if missing.
    if not CONFIG_FILE.exists():
        example = REPO_DIR / "config" / "config.example.json"
        if example.exists():
            shutil.copy2(example, CONFIG_FILE)
            print("Seeded config.json from example")
        else:
            print("ERROR: Cannot find config.example.json in cloned repo")
            sys.exit(1)

    # 4. Create .security.yml template if missing.
    if not SECURITY_FILE.exists():
        SECURITY_FILE.write_text(SECURITY_TEMPLATE)
        SECURITY_FILE.chmod(0o600)
        print("Created .security.yml template")

    print("Initialization complete. Next steps:")
    print("  1. Review and edit config/.security.yml to add your API keys")
    print("  2. Run ./setup.sh (or python3 setup.py) to complete Docker setup")


if __name__ == "__main__":
    main()