# Codex Setup

This repository can be used from Codex as a local stdio MCP server or as a
remote Streamable HTTP MCP server. The CLI command below follows the official
Codex `codex mcp` flow, which stores MCP entries in `~/.codex/config.toml`.

Official references:

- <https://developers.openai.com/codex/cli/reference#codex-mcp>
- <https://developers.openai.com/codex/config-reference#configtoml>

## Local stdio MCP

Install the server from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Register the compact assistant profile in Codex:

```bash
codex mcp add scihub \
  --env SCIHUB_MCP_LOCAL_TOOLS=all \
  --env SCIHUB_MCP_TOOLS=core \
  --env SCIHUB_MCP_DOWNLOAD_DIR="$PWD/downloads" \
  -- "$PWD/.venv/bin/sci-hub-mcp" --transport stdio
```

Verify:

```bash
codex mcp list
codex mcp get scihub --json
```

## Codex HTTP MCP

Run the server over Streamable HTTP:

```bash
SCIHUB_MCP_LOCAL_TOOLS=all \
SCIHUB_MCP_TOOLS=core \
SCIHUB_MCP_DOWNLOAD_DIR="$PWD/downloads" \
sci-hub-mcp \
  --transport streamable-http \
  --host 127.0.0.1 \
  --port 8000 \
  --streamable-http-path /mcp \
  --allowed-host localhost:8000
```

Register the local endpoint:

```bash
codex mcp add scihub-http --url http://127.0.0.1:8000/mcp
```

For a remote server, put TLS in front of `/mcp` and register the HTTPS URL:

```bash
codex mcp add scihub-remote --url https://your-domain.example/mcp
```

## Codex Plugin Readiness

Codex plugins can bundle MCP servers, but the stable contract this repository
exposes is the MCP server identity:

- stdio command: `sci-hub-mcp --transport stdio`
- HTTP endpoint: `https://your-domain.example/mcp`
- package install: `pip install .` or `pip install -e .`
- safe assistant profile: `SCIHUB_MCP_TOOLS=core`
- repository skills: `.agents/skills/`

For managed or bundled plugin deployments, keep the command/URL identity above
unchanged and apply tool allowlists in Codex configuration when needed.

## Scientific Skills

Codex can use the repository skills in `.agents/skills/`:

- `$scientific-literature-search`
- `$literature-review-synthesis`
- `$research-quality-appraisal`
- `$research-impact-assessment`

See [`docs/skills.md`](skills.md) for the skill boundaries and method anchors.

## Read-Only OA Profile

For review workflows where Codex should only query open-access metadata and not
download files, use the same ChatGPT-compatible profile:

```bash
codex mcp add scihub-oa \
  --env SCIHUB_MCP_LOCAL_TOOLS=chatgpt \
  --env SCIHUB_MCP_TOOLS=chatgpt \
  --env SCIHUB_MCP_ENABLE_SCIHUB_FALLBACK=0 \
  -- "$PWD/.venv/bin/sci-hub-mcp" --transport stdio
```

That exposes only `search` and `fetch`.
