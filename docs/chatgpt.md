# ChatGPT App Setup

This repository is prepared as a tool-only ChatGPT app: it exposes an MCP
server, no widget UI, and a read-only `search` / `fetch` surface for
company-knowledge and deep-research style clients.

Official references:

- <https://developers.openai.com/apps-sdk/build/mcp-server#company-knowledge-compatibility>
- <https://developers.openai.com/api/docs/mcp#create-an-mcp-server>
- <https://developers.openai.com/api/docs/guides/tools-connectors-mcp>

## Tool Profile

Use the ChatGPT profile for a narrow, read-only app surface:

```bash
SCIHUB_MCP_LOCAL_TOOLS=chatgpt
SCIHUB_MCP_TOOLS=chatgpt
SCIHUB_MCP_ENABLE_SCIHUB_FALLBACK=0
```

That exposes only:

- `search(query: str)`
- `fetch(id: str)`

Both tools are marked read-only. `search` returns result objects with `id`,
`title`, and `url`; `fetch` returns `id`, `title`, `text`, `url`, and `metadata`.
The `url` fields are absolute HTTP(S) URLs suitable for citations when the
resolver finds a user-openable paper page.

## Local Development

Install the package:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Run the MCP server locally:

```bash
SCIHUB_MCP_LOCAL_TOOLS=chatgpt \
SCIHUB_MCP_TOOLS=chatgpt \
SCIHUB_MCP_ENABLE_SCIHUB_FALLBACK=0 \
SCIHUB_MCP_DOWNLOAD_DIR="$PWD/downloads" \
sci-hub-mcp \
  --transport streamable-http \
  --host 127.0.0.1 \
  --port 8000 \
  --streamable-http-path /mcp \
  --allowed-host localhost:8000 \
  --allowed-origin https://chatgpt.com \
  --allowed-origin https://chat.openai.com
```

Expose `http://127.0.0.1:8000/mcp` through an HTTPS tunnel, then add the tunneled
`https://.../mcp` URL in ChatGPT Developer Mode.

## Production Notes

- Keep HTTPS in front of `/mcp`.
- Prefer `SCIHUB_MCP_ENABLE_SCIHUB_FALLBACK=0` for ChatGPT deployments.
- Add authentication before exposing the endpoint beyond a private test setup.
- Prepare privacy, data-use, and test-account details before any public app
  submission.
- Keep the app tool-only unless a real UI workflow is needed.
