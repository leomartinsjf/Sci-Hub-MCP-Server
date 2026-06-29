# Sci-Hub MCP Server

[![smithery badge](https://smithery.ai/badge/@JackKuo666/sci-hub-mcp-server)](https://smithery.ai/server/@JackKuo666/sci-hub-mcp-server)

Sci-Hub MCP Server exposes a Model Context Protocol interface for looking up academic
papers by DOI, title, keyword, and across many academic repositories.

The DOI, title, and keyword tools resolve full text through a chain of **legal
open-access providers first** — arXiv, Unpaywall, OpenAlex, Europe PMC, DOAJ, and CORE
(when an API key is configured). **Sci-Hub is consulted only as a last resort**, when no
open-access copy is found and the fallback is enabled. The server also registers the
public tool surface from `openags/paper-search-mcp`.

Use this project only where you have the legal right to access and download the content.

## Features

- Resolve a DOI to a full-text URL through legal open-access providers first
  (arXiv → Unpaywall → OpenAlex → Europe PMC → DOAJ → CORE), with Sci-Hub as a
  configurable last-resort fallback.
- Search by title through CrossRef, then resolve the best DOI match the same way.
- Search by keyword through CrossRef (maximum 20 results). Keyword resolution is
  open-access-only — the Sci-Hub fallback is disabled for bulk search to avoid
  automated scraping.
- Responses report provenance: `source`, `oa_status`, `license`, `landing_url`, and
  `is_open_access`, so callers can see exactly where a URL came from.
- Retrieve DOI metadata from CrossRef without requiring a download.
- Download direct PDF URLs into a restricted local download directory.
- Search, download, and read papers through integrated `paper-search-mcp` connectors.
- Unified multi-source search across arXiv, PubMed, bioRxiv, medRxiv, CrossRef,
  OpenAlex, PMC, CORE, Europe PMC, dblp, OpenAIRE, CiteSeerX, DOAJ, BASE, Zenodo,
  HAL, SSRN, Unpaywall, and other configured sources.

## Open-Access Resolution

`search_scihub_by_doi`, `search_scihub_by_title`, and `search_scihub_by_keyword` resolve
a DOI by trying these providers in order and returning the first hit (see
[`oa_resolver.py`](oa_resolver.py)):

| Order | Provider | Notes |
| --- | --- | --- |
| 1 | arXiv | Zero-network shortcut for arXiv-minted DOIs (`10.48550/arXiv.*`). |
| 2 | Unpaywall | Authoritative OA aggregator. Requires a contact email. |
| 3 | OpenAlex | Second aggregator; catches what Unpaywall misses. |
| 4 | Europe PMC | Strong for biomedical full text and PMC open-access renders. |
| 5 | DOAJ | Full text from vetted fully open-access journals. |
| 6 | CORE | Repository aggregator; runs only when `CORE_API_KEY` is set. |
| last | Sci-Hub | Last resort only, gated by `SCIHUB_MCP_ENABLE_SCIHUB_FALLBACK`. |

CrossRef is used for metadata and DOI resolution, not as an open-access PDF source: its
text-mining links are frequently paywalled and are not reliable open-access signals.

### Resolution configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `SCIHUB_MCP_CONTACT_EMAIL` | Contact email for Unpaywall (required by its terms) and the OpenAlex polite pool. Without it, Unpaywall is skipped. `UNPAYWALL_EMAIL` is accepted as a fallback name. | unset |
| `SCIHUB_MCP_ENABLE_SCIHUB_FALLBACK` | Enable the Sci-Hub last-resort fallback. Set to `0`/`false`/`no`/`off` to disable. | `1` (enabled) |
| `SCIHUB_MCP_SCIHUB_MIRRORS` | Comma-separated Sci-Hub mirrors for the last-resort fallback, e.g. `sci-hub.ru,sci-hub.se`. Use only where you have the legal right to access the content. | `sci-hub.ru` |
| `SCIHUB_MCP_OA_PROVIDERS` | Comma-separated provider order/subset override, e.g. `unpaywall,openalex`. Unknown names are ignored. | full default order |
| `CORE_API_KEY` | Enables the CORE provider when set. | unset |

Set `SCIHUB_MCP_CONTACT_EMAIL` to a real address — it unlocks Unpaywall, the single
most effective open-access source, and is required by Unpaywall's API terms.

## Requirements

- Python 3.10+
- `mcp >= 1.2.0`
- `requests`
- `paper-search-mcp` from commit `dba2c7430aec7e17463ad981caf1d391f0204335`

> Note: the Sci-Hub last-resort fallback scrapes HTML that changes often, so it
> may break independently of the open-access resolver. Set
> `SCIHUB_MCP_ENABLE_SCIHUB_FALLBACK=0` to run open-access only.

## Installation

```bash
git clone https://github.com/leomartinsjf/Sci-Hub-MCP-Server.git
cd Sci-Hub-MCP-Server
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

`pip install -e .` reads dependencies from `pyproject.toml` and installs the
`sci-hub-mcp` console command. The pinned requirements file also still works:

```bash
pip install -r requirements.txt      # runtime only
pip install -r requirements-dev.txt  # runtime + ruff + pytest
```

## Running the Server

After `pip install -e .` (or `pip install .`):

```bash
sci-hub-mcp
```

Or run the script directly:

```bash
python sci_hub_server.py
```

## Running with Docker

Build the image from the local checkout:

```bash
docker build -t sci-hub-mcp-server .
```

Run the MCP server over stdio, with downloads persisted to a local directory:

```bash
mkdir -p downloads
docker run --rm -i \
  -e SCIHUB_MCP_TOOLS=core \
  -e SCIHUB_MCP_DOWNLOAD_DIR=/downloads \
  -v "$PWD/downloads:/downloads" \
  sci-hub-mcp-server
```

## Claude Desktop Configuration

Use absolute paths for the Python executable and server script.

**Recommended for Claude** — set `SCIHUB_MCP_TOOLS=core` to expose a small,
high-signal tool set (the 5 local tools + unified search/download/metadata).
A large tool surface degrades Claude's tool-selection accuracy and consumes
context, so the lean profile is the better default for an assistant.

macOS example:

```json
{
  "mcpServers": {
    "scihub": {
      "command": "/absolute/path/to/Sci-Hub-MCP-Server/.venv/bin/python",
      "args": ["/absolute/path/to/Sci-Hub-MCP-Server/sci_hub_server.py"],
      "env": {
        "SCIHUB_MCP_DOWNLOAD_DIR": "/absolute/path/to/downloads",
        "SCIHUB_MCP_CONTACT_EMAIL": "you@example.com",
        "SCIHUB_MCP_TOOLS": "core"
      }
    }
  }
}
```

If you installed with `pip install -e .`, you can use the console command instead
of absolute paths (`"command": "sci-hub-mcp", "args": []`).

Windows example:

```json
{
  "mcpServers": {
    "scihub": {
      "command": "C:\\path\\to\\Sci-Hub-MCP-Server\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\Sci-Hub-MCP-Server\\sci_hub_server.py"],
      "env": {
        "SCIHUB_MCP_DOWNLOAD_DIR": "C:\\path\\to\\downloads",
        "SCIHUB_MCP_CONTACT_EMAIL": "you@example.com",
        "SCIHUB_MCP_TOOLS": "core"
      }
    }
  }
}
```

Setting `SCIHUB_MCP_CONTACT_EMAIL` configures both the local resolver and the
integrated Unpaywall tool (it is mirrored into `UNPAYWALL_EMAIL` automatically).

## MCP Tools

The server exposes 62 tools by default:

- 5 local Sci-Hub/CrossRef tools.
- 57 integrated `paper-search-mcp` tools.

When IEEE and ACM API keys are configured, the upstream package defines 6 additional
optional tools, for a maximum of 68 tools on this combined server.

### Selecting which tools to expose

`SCIHUB_MCP_TOOLS` controls which integrated `paper-search-mcp` tools are registered.
The 5 local tools are always present. A large tool surface degrades Claude's
tool-selection accuracy, so a curated set is recommended for assistant use.

| Value | Effect |
| --- | --- |
| `all` (default) | All integrated tools (62 total). |
| `core` | Curated minimal set: `search_papers`, `download_with_fallback`, `get_crossref_paper_by_doi` (8 tools total with the 5 local). Recommended for Claude. |
| `none` | Only the 5 local tools. |
| `a,b,c` | Explicit allowlist of integrated tool names; unknown names are ignored. |

### Local Tools

| Tool | Purpose |
| --- | --- |
| `search_scihub_by_doi` | Resolve a DOI to a full-text URL, open-access first, Sci-Hub last resort. |
| `search_scihub_by_title` | Resolve a title via CrossRef, then the same open-access-first chain. |
| `search_scihub_by_keyword` | Find keyword matches via CrossRef that have an open-access full text (no Sci-Hub fallback). |
| `download_scihub_pdf` | Download a direct PDF URL into the configured download directory. |
| `get_paper_metadata` | Get CrossRef metadata for a DOI. |

### Integrated `paper-search-mcp` Tools

Unified search:

- `search_papers`

Source search:

- `search_arxiv`
- `search_pubmed`
- `search_biorxiv`
- `search_medrxiv`
- `search_google_scholar`
- `search_iacr`
- `search_semantic`
- `search_crossref`
- `search_openalex`
- `search_pmc`
- `search_core`
- `search_europepmc`
- `search_dblp`
- `search_openaire`
- `search_citeseerx`
- `search_doaj`
- `search_base`
- `search_zenodo`
- `search_hal`
- `search_ssrn`
- `search_unpaywall`

Downloads and fallback:

- `download_arxiv`
- `download_pubmed`
- `download_biorxiv`
- `download_medrxiv`
- `download_iacr`
- `download_semantic`
- `download_crossref`
- `download_scihub`
- `download_with_fallback`
- `download_dblp`
- `download_openaire`
- `download_citeseerx`
- `download_doaj`
- `download_base`
- `download_zenodo`
- `download_hal`
- `download_ssrn`
- `download_openalex`

Read/extract:

- `read_arxiv_paper`
- `read_pubmed_paper`
- `read_biorxiv_paper`
- `read_medrxiv_paper`
- `read_iacr_paper`
- `read_semantic_paper`
- `read_crossref_paper`
- `read_dblp_paper`
- `read_openaire_paper`
- `read_citeseerx_paper`
- `read_doaj_paper`
- `read_base_paper`
- `read_zenodo_paper`
- `read_hal_paper`
- `read_ssrn_paper`
- `read_openalex_paper`

DOI lookup:

- `get_crossref_paper_by_doi`

Optional API-key tools:

- `search_ieee`
- `download_ieee`
- `read_ieee_paper`
- `search_acm`
- `download_acm`
- `read_acm_paper`

Set `PAPER_SEARCH_MCP_IEEE_API_KEY` or `PAPER_SEARCH_MCP_ACM_API_KEY` before server
startup to make the corresponding optional tools available. Legacy `IEEE_API_KEY` and
`ACM_API_KEY` are also supported by the upstream package.

## Download Safety

`download_scihub_pdf` and every integrated `paper-search-mcp` tool that accepts
`save_path` restrict writes to `SCIHUB_MCP_DOWNLOAD_DIR`. If that environment variable is
not set, downloads are restricted to `./downloads` from the server process working
directory.

The tool rejects:

- paths outside the configured download directory,
- non-HTTP(S) URLs,
- responses that are not PDF content,
- downloads larger than `SCIHUB_MCP_MAX_DOWNLOAD_BYTES`.

`download_scihub_pdf` also rejects non-`.pdf` output paths. Integrated source-specific
tools treat `save_path` as a directory and normalize it under the same configured
download directory.

`SCIHUB_MCP_MAX_DOWNLOAD_BYTES` defaults to `104857600` bytes.

Integrated source-specific download tools may have their own source restrictions. Some
connectors are metadata-only or require API keys.

## Development

Run the checks before submitting changes:

```bash
ruff check .
pytest
```

The normal test suite includes a completeness check that parses the installed
`paper_search_mcp.server` source and verifies that all 63 upstream `@mcp.tool()`
definitions are listed in `paper_search_integration.PAPER_SEARCH_TOOL_NAMES`.

To inspect the runtime tool count:

```bash
python - <<'PY'
import asyncio
import sci_hub_server

async def main():
    tools = await sci_hub_server.mcp.list_tools()
    print(f"total tools: {len(tools)}")
    print(f"integrated paper-search tools: {len(sci_hub_server.REGISTERED_PAPER_SEARCH_TOOLS)}")

asyncio.run(main())
PY
```

Run the real network integration tests with CrossRef metadata lookup, integrated arXiv
search, and open-access PDF downloads:

```bash
SCIHUB_MCP_RUN_NETWORK_TESTS=1 pytest -m integration
```

By default, the integration test downloads an arXiv PDF. To test a different direct PDF
URL that you are allowed to access:

```bash
SCIHUB_MCP_RUN_NETWORK_TESTS=1 \
SCIHUB_MCP_INTEGRATION_PDF_URL="https://example.org/paper.pdf" \
pytest -m integration
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

## Disclaimer

This tool is for research and interoperability purposes only. Respect copyright law,
publisher terms, institutional access policies, and local regulations.
