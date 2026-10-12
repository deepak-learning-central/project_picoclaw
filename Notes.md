# PicoClaw on Raspberry Pi — Setup Notes

These are hard-won findings from getting PicoClaw running reliably with
Telegram + Discord on a Raspberry Pi via Docker. Read this before you
re-run `setup.sh` or debug a similar issue from scratch.

## The core problem: `:latest` Docker image is out of sync with GitHub source

The pre-built `docker.io/sipeed/picoclaw:latest` image (and pinned tags like
`:v0.2.7`) **silently fails to initialize any channel except Telegram** —
even with a fully correct `config.json` and `.security.yml`. No error, no
warning beyond a generic "No channels enabled" if Telegram is also disabled.
This was confirmed empirically:
- Discord, DingTalk — both showed `enabled: true` in config, byte-identical
  between host and container, yet the channel manager never even logged an
  "Attempting to initialize channel" line for them.
- Same symptom on `:latest` (v0.3.1) and pinned `:v0.2.7` — not a regression,
  just a permanently out-of-sync pre-built image.

**Fix: build the `full` image from source instead of using the pre-built one.**
```bash
docker compose -f docker/docker-compose.full.yml build picoclaw-gateway
docker compose -f docker/docker-compose.full.yml --profile gateway up -d
```
This takes 20-40+ minutes on a Pi but only needs doing once (or after a
`git pull` of the upstream repo).

## The second problem: nested `settings` schema for secrets

PicoClaw's channel config has migrated to a per-channel `Settings` struct
(e.g. `DiscordSettings`, `TelegramSettings`) registered in
`pkg/config/config_channel.go`. This means:

- **`config.json`**: a channel's specific fields (like a bot token) must be
  nested under `settings`, not flat:
  ```json
  "discord": {
    "enabled": true,
    "settings": { "token": "..." }
  }
  ```
  A flat `"token": "..."` at the top level is rejected as an "unknown field"
  in strict builds (the `full` build validates this; `:latest` seems to
  silently drop it instead, which is *why* Discord never worked there even
  after fixing the token: the field was silently discarded).

- **`.security.yml`**: this is the counterintuitive part. The documented
  shorthand (`channels: <type>: <field>: ...`) **only works for legacy flat
  fields** — and even Telegram, despite being treated as "the legacy
  channel" in official docs, actually turned out to need the nested form
  too, once we dug into it. The reliable pattern, confirmed working for both
  Telegram and Discord, is to **mirror `config.json`'s exact path** under a
  `channel_list:` top-level key:
  ```yaml
  channel_list:
    telegram:
      settings:
        token: "..."
    discord:
      settings:
        token: "..."
  ```
  The flat `channels: telegram: token: ...` shorthand from the docs may
  appear to work if a real token happens to already be sitting in the
  nested location from an earlier onboarding run — don't trust it as the
  actual source of truth. Always verify with:
  ```bash
  docker compose -f docker/docker-compose.full.yml exec picoclaw-gateway \
    sh -c "grep -A2 'telegram:' /root/.picoclaw/.security.yml"
  ```
  to see what the container itself is actually reading.

## `docker-compose.full.yml` gotchas

- It only mounts `config.json` by default — **not** `.security.yml`. You
  must add this line yourself (once) right after each `config.json` mount:
  ```yaml
  - ../config/.security.yml:/root/.picoclaw/.security.yml
  ```
- The `config.json` mount is `:ro` (read-only) intentionally.
- If `../config/config.json` doesn't exist on the host when you first bring
  the container up, Docker will silently create it **as a directory**
  instead of erroring — leading to a confusing
  `cannot mkdir ... not a directory` error on the next attempt. Always seed
  the file first: `cp config/config.example.json config/config.json`.
  If you hit this, clean up with `sudo rm -rf config/config.json` and retry.

## OpenRouter model notes

- `openrouter/auto` requires actual account credits — a $0-balance key gets
  a `402 Insufficient credits` error even though "auto" sounds like it
  should be able to pick a free option.
- **`openrouter/free`** is the correct model ID for genuinely free routing.
  Rate limits: 20 req/min always; 50 req/day with no credits ever
  purchased, or 1,000 req/day once you've added at least $10 (one-time,
  doesn't need to be spent — the higher limit persists even after balance
  hits $0 again).
- Model config setup lives in `config.json`'s `model_list` (public fields)
  + `.security.yml`'s matching `model_list.<name>:0.api_keys` (the secret).

## Docker/file ownership gotcha (applies to any bind-mounted config)

The container runs as **root**, so anything it writes into a bind-mounted
host folder (including on first-run config generation) comes out
root-owned. If you can't `chmod`/edit a config file afterward:
```bash
sudo chown -R $(id -u):$(id -g) config/
```
This can recur any time the container restarts and touches the folder —
don't assume a one-time fix sticks.

## Running setup

Use `setup.sh` in this repo (kept out of git is only `picoclaw/`, the
cloned+built project itself — `setup.sh` is the one durable, checked-in
artifact). Re-running it from scratch:
```bash
chmod +x setup.sh
./setup.sh
```
walks through Docker install, cloning, building the full image, and
interactive Telegram/Discord configuration using the correct nested-settings
paths described above. You'll need your bot tokens and OpenRouter API key
on hand again since secrets are never committed to git.