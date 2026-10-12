# pico-docker-setup

Minimal Dockerized PicoClaw setup project — **zero configuration** deployment
using Docker Compose with the full source build.

## Overview

This project provides a self-contained setup that:

- **Builds the full PicoClaw image from source** (not the outdated `:latest`
  image on Docker Hub — see Notes.md for why)
- **Clones the official PicoClaw repo** at setup time (`git clone` into
  `./picoclaw/`) so this repo stays source-free
- **Mounts both `config.json` and `.security.yml`** into the container with the
  correct paths for nested-settings channels (Telegram flat, Discord nested)
- **Provides idempotent setup** — re-running is safe
- **Handles file ownership** across the container/host boundary
- **Supports interactive credential configuration** for Telegram and Discord
- **Includes clear startup/shutdown commands**

This project contains **ONLY** Docker orchestration files and automation scripts.
The actual PicoClaw source code is cloned from GitHub at runtime into
`./picoclaw/` and excluded from git via `.gitignore`.

## Project Layout

```text
pico-docker-setup/
├── .gitignore                  # Prevents committing secrets
├── docker-compose.yml          # Main compose (builds from source)
├── pyproject.toml              # uv project metadata (dependencies, entry points)
├── requirements.txt            # Plain-text dependency list
├── setup.py                    # Full automated setup script (python)
├── scripts/
│   ├── __init__.py
│   ├── initialize.py           # First-time setup helper
│   └── update.py               # Update source + rebuild Gateway
└── README.md                   # This file
```

## Prerequisites

- Docker + Docker Compose v2 plugin installed
- [uv](https://docs.astral.sh/uv/) — a fast Python package installer/manager
- Python 3.8+ (comes preinstalled with uv)
- `curl`, `git`, `sudo` (installed automatically where possible)

Install uv on Linux/macOS:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Raspberry Pi / ARM systems, `curl`, `git`, and Docker will be installed
automatically during setup if missing.

## Quick Start

### 1) Full setup (one command)

```bash
cd /Users/deepaksama/Documents/Development/Repositories/project_picoclaw
uv run setup.py
```

This will:
1. Install the project's Python dependencies (`rich`, `pyyaml`) with uv
2. Install Docker if needed, add your user to the docker group
3. Clone/picoclaw/ from GitHub
4. Seed `config/config.json` and `config/.security.yml` from example templates
5. Prompt you for Telegram / Discord tokens and API keys
6. Build the full Docker image from PicoClaw source (20–40+ min on Pi, one-time)
7. Start the Gateway container in detached mode (restart: unless-stopped)
8. Verify channels are initialized

### 2) First-time helper only (clone + seed config, no Docker)

```bash
uv run initialize.py
```

Run this when you've just cloned the repo and want to prepare the config
directories before running the full setup.

### 3) Start / restart Gateway only (after setup)

```bash
docker compose --profile gateway up -d
```

### 4) One-off agent query

```bash
docker compose --profile agent run --rm picoclaw-agent -m "hello"
```

### 5) View logs

```bash
docker compose --profile gateway logs -f
```

### 6) Stop Gateway

```bash
docker compose --profile gateway down
```

### 7) Update source and rebuild

```bash
uv run update.py
```

This pulls the latest PicoClaw source, rebuilds the Gateway image, and
restarting the Gateway automatically.

## Security

- **Secrets live in `config/.security.yml`** (chmod 600, gitignored)
- **Non-sensitive config lives in `config/config.json`**
- **`.gitignore` ensures secrets are never committed**
- Gateway defaults to `127.0.0.1` (localhost only). Set
  `PICOCLAW_GATEWAY_HOST=0.0.0.0` in `.env` only if you understand the risk
  and have firewall/VPN protection.

## Configuration

### Nested-settings channels (Telegram / Discord)

The project uses the correct nested-settings schema:

**`config/config.json`** (channel_list section):
```json
{
  "channel_list": {
    "telegram": {
      "enabled": true,
      "type": "telegram",
      "allow_from": ["123456789"]
    },
    "discord": {
      "enabled": true,
      "type": "discord",
      "allow_from": ["123456789"],
      "settings": { "token": "..." }
    }
  }
}
```

**`config/.security.yml`** (channel_list section — mirror config.json):
```yaml
channel_list:
  telegram:
    settings:
      token: "..."
  discord:
    settings:
      token: "..."
```

> **Key point**: Discord's token must go under `channel_list.discord.settings.token`
> — the flat `channels:` shorthand does NOT merge into nested settings objects
> in the current codebase. Telegram works with both flat and nested, but we
> always use the nested form here to match config.json's exact path.

### Environment variables

- `PICOCLAW_GATEWAY_HOST` — defaults to `127.0.0.1`. Set to `0.0.0.0` to expose
  on LAN (not recommended without firewall/VPN).
- Added to `.env` during setup if you choose to expose on LAN.

## Known Issues & Troubleshooting

See **docs/UPSTREAM_PICOCLAW_README.md** in this repo for the upstream
PicoClaw project's full troubleshooting guide, including:

- `:latest` Docker image silently fails non-Telegram channels
- Nested `settings` schema for secrets
- `docker-compose.full.yml` gotchas (missing `.security.yml` mount)
- `config.json` directory vs file gotcha
- OpenRouter model notes
- File ownership after container restarts

If you hit specific issues not covered there, check the logs:

```bash
docker compose --profile gateway logs -f picoclaw-gateway
```

Look for lines containing:
- `attempting to initialize channel`
- `channels enabled`
- `no channels`

## Contributing

Pull requests welcome! This project aims to keep setup minimal and
well-documented. See the upstream PicoClaw CONTRIBUTING.md for guidelines.

## License

MIT — same as PicoClaw.
