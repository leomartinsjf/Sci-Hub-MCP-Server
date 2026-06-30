# Claude Setup

This repository is ready for Claude Code through the checked-in `.mcp.json` file
and can also be exposed to Claude remote connectors through the `streamable-http`
transport.

## Claude Code

Install the server in a local virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Claude Code reads the project-level `.mcp.json` from this repository. The checked-in
configuration starts `.venv/bin/python sci_hub_server.py --transport stdio`, exposes
the compact `core` tool profile, and writes downloads under `./downloads`.

Then open Claude Code from the repository root and verify the server:

```bash
claude mcp list
```

## Claude Desktop Or Other Local MCP Clients

After `pip install -e .`, a local stdio client can start the server with the console
command:

```json
{
  "mcpServers": {
    "scihub": {
      "command": "/absolute/path/to/Sci-Hub-MCP-Server/.venv/bin/sci-hub-mcp",
      "args": ["--transport", "stdio"],
      "env": {
        "SCIHUB_MCP_TOOLS": "core",
        "SCIHUB_MCP_DOWNLOAD_DIR": "/absolute/path/to/downloads"
      }
    }
  }
}
```

## Claude Remote Connector

Claude remote connectors require an HTTPS-accessible MCP endpoint. Run this server
with `streamable-http` behind a TLS reverse proxy:

```bash
SCIHUB_MCP_TOOLS=core \
SCIHUB_MCP_DOWNLOAD_DIR=/srv/scihub-mcp/downloads \
sci-hub-mcp \
  --transport streamable-http \
  --host 127.0.0.1 \
  --port 8000 \
  --streamable-http-path /mcp \
  --allowed-host your-domain.example
```

Expose `http://127.0.0.1:8000/mcp` as `https://your-domain.example/mcp`, then add
that HTTPS URL as a custom connector in Claude.

## Docker

Build the image:

```bash
docker build -t sci-hub-mcp-server .
```

Local stdio mode:

```bash
mkdir -p downloads
docker run --rm -i \
  -e SCIHUB_MCP_TOOLS=core \
  -e SCIHUB_MCP_DOWNLOAD_DIR=/downloads \
  -v "$PWD/downloads:/downloads" \
  sci-hub-mcp-server
```

Remote `streamable-http` mode:

```bash
mkdir -p downloads
docker run --rm \
  -p 8000:8000 \
  -e SCIHUB_MCP_TOOLS=core \
  -e SCIHUB_MCP_DOWNLOAD_DIR=/downloads \
  -v "$PWD/downloads:/downloads" \
  sci-hub-mcp-server \
  --transport streamable-http \
  --host 0.0.0.0 \
  --port 8000 \
  --streamable-http-path /mcp \
  --allowed-host your-domain.example
```

Put TLS in front of the container before using it as a Claude remote connector.

## Recommended Safety Defaults

- Keep `SCIHUB_MCP_TOOLS=core` for Claude clients to reduce tool-selection noise.
- Set `SCIHUB_MCP_CONTACT_EMAIL` to enable Unpaywall and OpenAlex polite-pool access.
- Set `SCIHUB_MCP_ENABLE_SCIHUB_FALLBACK=0` when you want open-access-only behavior.
- Keep `SCIHUB_MCP_DOWNLOAD_DIR` mounted to a dedicated directory.
