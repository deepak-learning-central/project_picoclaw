#!/usr/bin/env python3
#
# setup.py
# Automated, security-conscious PicoClaw installer (Python rewrite).
#
# Builds the "full" image from source (docker/Dockerfile.full) since the
# pre-built :latest image on Docker Hub lags behind the source and silently
# fails to initialize non-Telegram channels (Discord, DingTalk, etc.) even
# when correctly configured. Building from source takes 20-40+ minutes on a
# Raspberry Pi — this is a one-time cost.
#
# Usage:
#   python3 setup.py
#   ./setup.sh          # thin bash wrapper invoking the same logic
#
# Safe to re-run (idempotent where possible): it will resume or skip
# already-completed steps.
#
# Run this from the project root directory (where docker-compose.yml lives).
#
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Import PyYAML with a friendly error if missing.
try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write("ERROR: PyYAML is not installed. Please install it with: pip install pyyaml\n")
    sys.exit(1)

# Import rich with a friendly error if missing.
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt
    from rich.status import Status
except ImportError:  # pragma: no cover
    sys.stderr.write("ERROR: Rich is not installed. Please install it with: pip install rich\n")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REPO_URL = "https://github.com/sipeed/picoclaw.git"
REPO_DIR = Path("picoclaw")
COMPOSE_FILE = Path("docker-compose.yml")
CONFIG_DIR = Path("config")
CONFIG_FILE = CONFIG_DIR / "config.json"
SECURITY_FILE = CONFIG_DIR / ".security.yml"
GATEWAY_SERVICE = "picoclaw-gateway"
ENV_FILE = Path(".env")

CONSOLE = Console()

# ANSI helpers (rich handles most rendering, these are for manual escape sequences)
GREEN = "#4ade80"
YELLOW = "#fbbf24"
RED = "#f87171"
BLUE = "#60a5fa"


# ---------------------------------------------------------------------------
# Rich-printing helpers
# ---------------------------------------------------------------------------
def step(title: str) -> None:
    """Print a section header (1/10, 2/10, ...)."""
    CONSOLE.print(f"\n[bold blue]==> {title}[/bold blue]")


def info(text: str) -> None:
    """Print an indented info line."""
    CONSOLE.print(f"    {text}")


def ok(text: str) -> None:
    """Print a success line."""
    CONSOLE.print(f"    [green]✔ {text}[/green]")


def warn(text: str) -> None:
    """Print a warning line."""
    CONSOLE.print(f"    [yellow]⚠ {text}[/yellow]")


def fail(text: str) -> None:
    """Print a fatal error and exit."""
    CONSOLE.print(f"\n[bold red]✘ {text}[/bold red]")
    sys.exit(1)


def run(cmd: list[str], *, check: bool = True, capture: bool = False, text: bool = False) -> subprocess.CompletedProcess:
    """Run a command. When *capture* is True, stdout+stderr are captured;
    otherwise they stream to the terminal so long operations (docker build)
    stay visible."""
    if capture:
        proc = subprocess.run(cmd, capture_output=True, text=text, check=False)
        if check and proc.returncode != 0:
            stderr = proc.stderr if text else proc.stderr.decode(errors="replace")
            fail(f"Command failed: {' '.join(cmd)}\n{stderr}")
        return proc
    proc = subprocess.run(cmd, check=check)
    return proc


def command_exists(name: str) -> bool:
    """Check whether an executable is available on PATH."""
    return shutil.which(name) is not None


def docker_cmd() -> list[str]:
    """Return ['docker'] or ['sudo', 'docker'] depending on group permissions.
    The container runs as root and the host user must be in the 'docker'
    group; until they re-login, sudo bridges the gap."""
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        warn("Current shell session doesn't have docker group permissions yet — using sudo for this run")
        return ["sudo", "docker"]
    return ["docker"]


# ---------------------------------------------------------------------------
# 1. Hardware / OS sanity check
# ---------------------------------------------------------------------------
def check_hardware() -> None:
    step("1/10  Checking hardware and OS")
    arch = os.uname().machine
    info(f"Detected architecture: {arch}")
    if arch in ("aarch64", "arm64"):
        ok("ARM64 detected — matches Raspberry Pi 3/4/5, Zero 2 W")
    elif arch in ("armv6l", "armv7l"):
        ok("ARMv6/v7 detected — matches Raspberry Pi 1 / Zero (older, still supported)")
    elif arch == "x86_64":
        warn("x86_64 detected — this doesn't look like a Pi, but PicoClaw supports it too")
    else:
        warn(f"Unrecognized architecture ({arch}) — PicoClaw may still work, proceeding")

    if Path("/etc/os-release").exists():
        release: dict[str, str] = {}
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                release[key.strip()] = value.strip().strip('"')
        info(f"OS: {release.get('PRETTY_NAME', 'unknown')}")


# ---------------------------------------------------------------------------
# 2. Docker installation
# ---------------------------------------------------------------------------
def ensure_docker() -> None:
    step("2/10  Checking for Docker")
    if command_exists("docker"):
        version = run(["docker", "--version"], capture=True, text=True).stdout.strip()
        ok(f"Docker already installed: {version}")
    else:
        info("Docker not found. Installing via get.docker.com (official convenience script)...")
        run(["curl", "-fsSL", "https://get.docker.com"], check=True)
        ok("Docker installed: " + run(["docker", "--version"], capture=True, text=True).stdout.strip())

    # Verify Compose v2 plugin.
    compose_check = run(["docker", "compose", "version"], capture=True)
    if compose_check.returncode != 0:
        fail("Docker Compose v2 plugin not found. Please install it and re-run this script.")
    version = compose_check.stdout.decode().strip()
    ok(f"Docker Compose available: {version}")

    # Ensure user is in the docker group.
    user = os.environ.get("USER", "")
    group_out = subprocess.run(["id", "-nG", user], capture_output=True, text=True).stdout.split()
    if "docker" not in group_out:
        info(f"Adding {user} to the 'docker' group so you don't need sudo for docker commands...")
        run(["sudo", "usermod", "-aG", "docker", user], check=True)
        warn("Group membership updated. You must log out and back in (or run 'newgrp docker')")
        warn("for this to take effect before re-running this script without sudo.")
    else:
        ok(f"{user} is already in the docker group")


# ---------------------------------------------------------------------------
# 3. Clone / update the repo
# ---------------------------------------------------------------------------
def ensure_repo() -> None:
    step("3/10  Fetching PicoClaw source")
    if REPO_DIR.exists() and (REPO_DIR / ".git").exists():
        info(f"Repo already exists at ./{REPO_DIR} — pulling latest changes...")
        run(["git", "-C", str(REPO_DIR), "pull", "--ff-only"], check=True)
        ok("Repository updated")
    else:
        info(f"Cloning {REPO_URL} ...")
        run(["git", "clone", REPO_URL, str(REPO_DIR)], check=True)
        ok(f"Repository cloned into ./{REPO_DIR}")


def verify_compose_security_mount() -> None:
    step("4/10  Verifying .security.yml is mounted in compose")
    if not COMPOSE_FILE.exists():
        fail(f"{COMPOSE_FILE} not found — run this script from the project root directory.")
    if ".security.yml:/root/.picoclaw/.security.yml" in COMPOSE_FILE.read_text():
        ok(f"{COMPOSE_FILE} mounts .security.yml")
    else:
        fail(f"{COMPOSE_FILE} does not mount .security.yml — expected configuration is missing.")


# ---------------------------------------------------------------------------
# 5. Config seeding
# ---------------------------------------------------------------------------
def fix_data_ownership(dir_path: str) -> None:
    """Ensure a directory (and everything inside it) is owned by the current user,
    not root. The container runs as root, so anything it writes into a bind-mounted
    folder can be root-owned even if the folder itself already belongs to you —
    so this always does a full recursive chown rather than checking the folder."""
    if not Path(dir_path).exists():
        return
    try:
        subprocess.run(
            ["sudo", "chown", "-R", f"{os.getuid()}:{os.getgid()}", dir_path],
            check=True, capture_output=True,
        )
        ok(f"{dir_path} (and contents) owned by {os.environ.get('USER', 'user')}")
    except subprocess.CalledProcessError:
        warn(f"Could not chown {dir_path} — following steps may need sudo")


def safe_chmod(path: str, mode: int) -> None:
    """chmod that tolerates files owned by root by falling back to sudo."""
    try:
        os.chmod(path, mode)
        ok(f"Permissions set to {oct(mode)} on {path}")
    except OSError:
        info("Direct chmod failed (likely root-owned) — retrying with sudo...")
        try:
            subprocess.run(
                ["sudo", "chmod", oct(mode), path], check=True, capture_output=True
            )
            ok(f"Permissions set to {oct(mode)} on {path} (via sudo)")
        except subprocess.CalledProcessError:
            warn(f"Could not set permissions on {path}. Fix manually with:")
            warn(f"  sudo chown $USER:$USER {path} && chmod {oct(mode)} {path}")


def ensure_config() -> None:
    step("5/10  Generating default configuration")
    CONFIG_DIR.mkdir(exist_ok=True)
    # A previous failed Docker mount can leave config.json as a root-owned
    # directory instead of a file — clean that up first if present.
    if CONFIG_FILE.exists() and CONFIG_FILE.is_dir():
        warn(f"{CONFIG_FILE} exists as a directory (leftover from a failed mount) — removing it")
        shutil.rmtree(CONFIG_FILE)

    if CONFIG_FILE.exists():
        ok(f"{CONFIG_FILE} already exists — skipping")
    else:
        example = REPO_DIR / "config" / "config.example.json"
        if example.exists():
            shutil.copy2(example, CONFIG_FILE)
            ok(f"Created {CONFIG_FILE} from config.example.json")
        else:
            fail(f"{example} not found — cannot generate a starting config.json.")
    fix_data_ownership(str(CONFIG_DIR))


def security_template() -> str:
    return """# PicoClaw secrets file.
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


def ensure_security() -> None:
    """Create the .security.yml template if missing."""
    if SECURITY_FILE.exists():
        ok(f"{SECURITY_FILE} already exists")
    else:
        info(f"Creating {SECURITY_FILE} for API keys / tokens (kept separate from config.json)")
        SECURITY_FILE.write_text(security_template())
        safe_chmod(str(SECURITY_FILE), 0o600)
        ok(f"Template written to {SECURITY_FILE}")


def add_to_gitignore() -> None:
    """Make sure .gitignore covers the config directory (which holds secrets)."""
    gitignore = Path(".gitignore")
    if gitignore.exists():
        lines = gitignore.read_text().splitlines()
        if "config/" not in lines and "config/.security.yml" not in lines:
            with gitignore.open("a") as f:
                f.write("config/.security.yml\n")
            ok("Added config/.security.yml to .gitignore")


# ---------------------------------------------------------------------------
# 6. Secure credential handling
# ---------------------------------------------------------------------------
def ask_model_keys_editor() -> None:
    """Prompt the user to open the security file in their editor."""
    if Confirm.ask("Open .security.yml in your editor ($EDITOR) now to add your model API key(s)?", default=True):
        editor = os.environ.get("EDITOR", "nano")
        run([editor, str(SECURITY_FILE)], check=True)
        fix_data_ownership(str(CONFIG_DIR))
        safe_chmod(str(SECURITY_FILE), 0o600)
    else:
        info(f"Remember to edit it before your models will work: {SECURITY_FILE}")


# ---------------------------------------------------------------------------
# 7. Network exposure decision
# ---------------------------------------------------------------------------
def ask_network_exposure() -> None:
    """Ask whether to expose the Gateway on the LAN."""
    info("By default the Gateway binds to 127.0.0.1 (localhost only) — the secure default.")
    if Confirm.ask("Expose the Gateway on your LAN (0.0.0.0)? Only say yes if you understand the risk", default=False):
        warn("Setting PICOCLAW_GATEWAY_HOST=0.0.0.0 — this exposes the Gateway to your network.")
        warn("Recommended: put a firewall, VPN (e.g. Tailscale/WireGuard), or reverse proxy with TLS in front of it.")
        lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
        if "PICOCLAW_GATEWAY_HOST=0.0.0.0" not in lines:
            lines.append("PICOCLAW_GATEWAY_HOST=0.0.0.0")
            ENV_FILE.write_text("\n".join(lines) + "\n")
        ok("Saved to .env for docker compose to pick up")
    else:
        ok("Keeping Gateway on 127.0.0.1 (recommended)")


# ---------------------------------------------------------------------------
# 8. Channel configuration (Telegram / Discord) — automated
# ---------------------------------------------------------------------------
def configure_channels() -> None:
    """Interactive configuration of Telegram and/or Discord, writing both
    config.json (enabled flag, allow_from, settings) and .security.yml
    (tokens) using the correct structure for each channel's schema."""
    step("8/10  Channel configuration")
    info("This can configure Telegram and Discord for you: it edits config.json")
    info("(enabled flag, allow_from, etc.) and .security.yml (tokens) using the")
    info("correct structure for each channel's schema, so you don't have to")
    info("hand-edit JSON/YAML or hit the nested-settings gotcha yourself.")
    info("(WhatsApp is intentionally left out of automation — its native/bridge")
    info("setup varies enough that it's safer to configure by hand afterward.)")

    if not Confirm.ask("Configure Telegram / Discord now?", default=True):
        info(f"Skipping automated channel setup. Edit {CONFIG_FILE} and {SECURITY_FILE}")
        info("manually later if you want to enable any channels.")
        return

    telegram_enabled = Confirm.ask("  Enable Telegram?", default=False)
    telegram_token = ""
    telegram_allow = ""
    if telegram_enabled:
        info("  Create a bot via @BotFather on Telegram, get your user ID from @userinfobot.")
        telegram_token = Prompt.ask("  Telegram bot token", password=True)
        telegram_allow = Prompt.ask("  Your Telegram user ID(s), comma-separated")

    discord_enabled = Confirm.ask("  Enable Discord?", default=False)
    discord_token = ""
    discord_allow = ""
    discord_mention_only = True
    if discord_enabled:
        info("  Create an app+bot at discord.com/developers/applications,")
        info("  enable MESSAGE CONTENT INTENT, and invite it with the 'bot' scope.")
        discord_token = Prompt.ask("  Discord bot token", password=True)
        discord_allow = Prompt.ask("  Your Discord user ID(s), comma-separated")
        discord_mention_only = Confirm.ask("  Only respond when @-mentioned in servers?", default=True)

    fix_data_ownership(str(CONFIG_DIR))

    # ---- config.json ------------------------------------------------
    config = json.loads(CONFIG_FILE.read_text())
    channel_list = config.setdefault("channel_list", {})

    if telegram_enabled:
        tg = channel_list.setdefault("telegram", {})
        tg["enabled"] = True
        tg["type"] = "telegram"
        tg["allow_from"] = [x.strip() for x in telegram_allow.split(",") if x.strip()]
        tg.pop("token", None)  # keep secrets out of config.json

    if discord_enabled:
        dc = channel_list.setdefault("discord", {})
        dc["enabled"] = True
        dc["type"] = "discord"
        dc["allow_from"] = [x.strip() for x in discord_allow.split(",") if x.strip()]
        dc["group_trigger"] = {"mention_only": discord_mention_only}
        dc.pop("token", None)
        dc["settings"] = dc.get("settings", {})

    CONFIG_FILE.write_text(json.dumps(config, indent=2) + "\n")
    ok("config.json updated")

    # ---- .security.yml -----------------------------------------------
    security = yaml.safe_load(SECURITY_FILE.read_text()) or {}

    # Telegram: legacy flat field, merges fine under "channels:"
    if telegram_enabled and telegram_token:
        channels_sec = security.setdefault("channels", {})
        channels_sec.setdefault("telegram", {})["token"] = telegram_token

    # Discord: nested-settings schema. The "channels:" shorthand does NOT merge
    # into nested settings objects in the current codebase — it must mirror
    # config.json's exact path under "channel_list:" instead.
    if discord_enabled and discord_token:
        channel_list_sec = security.setdefault("channel_list", {})
        channel_list_sec["discord"] = {"settings": {"token": discord_token}}

    SECURITY_FILE.write_text(yaml.dump(security, default_flow_style=False, sort_keys=False))
    ok(".security.yml updated")
    fix_data_ownership(str(CONFIG_DIR))
    safe_chmod(str(SECURITY_FILE), 0o600)


# ---------------------------------------------------------------------------
# 9. Build and launch the Gateway (detached, auto-restart)
# ---------------------------------------------------------------------------
def build_and_start_gateway() -> None:
    step("9/10  Building and starting PicoClaw Gateway")
    warn("Building from source — this can take 20-40+ minutes on a Raspberry Pi.")
    warn("This is a one-time cost; rebuilds after this will be much faster.")

    compose = docker_cmd()
    build_cmd = compose + ["compose", "build", GATEWAY_SERVICE]
    info(f"Building the full Gateway image from PicoClaw source: {' '.join(build_cmd)}")
    try:
        with Status("[cyan]Building picoclaw-gateway from source...[/cyan]", spinner="dots"):
            proc = subprocess.run(build_cmd, check=True)
        ok("Image built")
    except subprocess.CalledProcessError as exc:
        # `docker compose build` streams its own progress to stderr/stdout,
        # so by the time we get here the user has already seen the error.
        fail("Docker build failed — see the output above for details.")

    info("Launching with --profile gateway in detached mode (restart: unless-stopped)...")
    up_cmd = compose + ["compose", "--profile", "gateway", "up", "-d", "--force-recreate"]
    try:
        run(up_cmd, check=True)
    except subprocess.CalledProcessError:
        fail("Failed to start the Gateway — see the output above for details.")
    ok("Gateway started")


# ---------------------------------------------------------------------------
# 10. Status check
# ---------------------------------------------------------------------------
def verify_status() -> None:
    step("10/10  Verifying containers are running")
    compose = docker_cmd()
    run(compose + ["compose", "--profile", "gateway", "ps"], check=True)
    info("Channel status from this run's logs:")
    log_proc = run(compose + ["compose", "--profile", "gateway", "logs"], capture=True, text=True, check=False)
    keywords = ("attempting to initialize channel", "channels enabled", "no channels")
    matched = [l for l in log_proc.stdout.splitlines() if any(k in l.lower() for k in keywords)]
    if matched:
        for line in matched:
            CONSOLE.print(f"    {line}")
    else:
        info("  (no channel log lines found yet — check logs manually if needed)")


def print_summary() -> None:
    CONSOLE.print()
    CONSOLE.print("[bold green]Setup complete.[/bold green]")
    CONSOLE.print("[bold]Useful commands (run from the project root):[/bold]")
    CONSOLE.print("    View logs:    docker compose --profile gateway logs -f")
    CONSOLE.print("    Restart:      docker compose --profile gateway up -d --force-recreate")
    CONSOLE.print("    Stop:         docker compose --profile gateway down")
    CONSOLE.print("    Rebuild:      docker compose --profile gateway build")
    CONSOLE.print('    Test agent:   docker compose --profile agent run --rm picoclaw-agent -m "hello"')
    CONSOLE.print()
    CONSOLE.print("[bold]Security reminders:[/bold]")
    CONSOLE.print(f"    - Secrets live in {SECURITY_FILE} (chmod 0600, gitignored)")
    CONSOLE.print("    - Gateway is on 127.0.0.1 unless you chose otherwise")
    CONSOLE.print("    - Set 'allow_from' on any chat channel you enable")
    CONSOLE.print("    - Keep restrict_to_workspace: true in config.json unless you fully trust all inputs")
    CONSOLE.print()
    CONSOLE.print(f"[bold]Known quirk (see comments in {SECURITY_FILE}):[/bold]")
    CONSOLE.print("    - Telegram's token: goes under 'channels:' in .security.yml (flat)")
    CONSOLE.print("    - Discord's token: must go under 'channel_list: discord: settings:'")
    CONSOLE.print("      in .security.yml (mirroring config.json's exact nested path) —")
    CONSOLE.print("      the 'channels:' shorthand does not merge into nested settings.")


def main() -> None:
    """Main entry point — runs the full setup flow."""
    CONSOLE.print(
        Panel(
            "[bold]PicoClaw Dockerized Setup (full build)[/bold]\n\n"
            "This will clone PicoClaw, BUILD the full image from source\n"
            "(needed for reliable Discord/other-channel support — see notes\n"
            "in Notes.md), then configure it securely and start it.\n"
            "The build step alone can take 20-40+ minutes on a Raspberry Pi.",
            title="[bold blue]PicoClaw Setup[/bold blue]",
            border_style="blue",
        )
    )

    check_hardware()
    ensure_docker()
    ensure_repo()
    verify_compose_security_mount()
    ensure_config()
    ensure_security()
    add_to_gitignore()
    ask_model_keys_editor()
    ask_network_exposure()
    configure_channels()
    build_and_start_gateway()
    verify_status()
    print_summary()


if __name__ == "__main__":
    main()
