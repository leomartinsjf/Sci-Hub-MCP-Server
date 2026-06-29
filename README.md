# Sci-Hub MCP Server

[![smithery badge](https://smithery.ai/badge/@JackKuo666/sci-hub-mcp-server)](https://smithery.ai/server/@JackKuo666/sci-hub-mcp-server)

Sci-Hub MCP Server exposes a Model Context Protocol interface for looking up academic
papers by DOI, title, keyword, and multiple academic repositories. It keeps the original
Sci-Hub-oriented tools and also registers the public tool surface from
`openags/paper-search-mcp`.

Use this project only where you have the legal right to access and download the content.

## Features

- Search by DOI and return a resolved PDF URL when available.
- Search by title through CrossRef, then resolve the best DOI match.
- Search by keyword through CrossRef with a maximum of 20 requested results.
- Retrieve DOI metadata from CrossRef without requiring a Sci-Hub download.
- Download direct PDF URLs into a restricted local download directory.
- Search, download, and read papers through integrated `paper-search-mcp` connectors.
- Unified multi-source search across arXiv, PubMed, bioRxiv, medRxiv, CrossRef,
  OpenAlex, PMC, CORE, Europe PMC, dblp, OpenAIRE, CiteSeerX, DOAJ, BASE, Zenodo,
  HAL, SSRN, Unpaywall, and other configured sources.

## Requirements

- Python 3.10+
- `mcp`
- `requests`
- `bs4`
- `scihub`
- `paper-search-mcp` from commit `dba2c7430aec7e17463ad981caf1d391f0204335`

## Installation

```bash
git clone https://github.com/JackKuo666/Sci-Hub-MCP-Server.git
cd Sci-Hub-MCP-Server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For local development:

```bash
pip install -r requirements-dev.txt
```

## Running the Server

```bash
python sci_hub_server.py
```

You can also run it as a module from the repository root:

```bash
python -m sci_hub_server
```

## Claude Desktop Configuration

Use absolute paths for the Python executable and server script.

macOS example:

```json
{
  "mcpServers": {
    "scihub": {
      "command": "/absolute/path/to/Sci-Hub-MCP-Server/.venv/bin/python",
      "args": ["/absolute/path/to/Sci-Hub-MCP-Server/sci_hub_server.py"],
      "env": {
        "SCIHUB_MCP_DOWNLOAD_DIR": "/absolute/path/to/downloads"
      }
    }
  }
}
```

Windows example:

```json
{
  "mcpServers": {
    "scihub": {
      "command": "C:\\path\\to\\Sci-Hub-MCP-Server\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\Sci-Hub-MCP-Server\\sci_hub_server.py"],
      "env": {
        "SCIHUB_MCP_DOWNLOAD_DIR": "C:\\path\\to\\downloads"
      }
    }
  }
}
```

## MCP Tools

The server exposes 62 tools by default:

- 5 local Sci-Hub/CrossRef tools.
- 57 integrated `paper-search-mcp` tools.

When IEEE and ACM API keys are configured, the upstream package defines 6 additional
optional tools, for a maximum of 68 tools on this combined server.

### Local Tools

| Tool | Purpose |
| --- | --- |
| `search_scihub_by_doi` | Search Sci-Hub by DOI. |
| `search_scihub_by_title` | Search CrossRef by title and resolve the DOI on Sci-Hub. |
| `search_scihub_by_keyword` | Search CrossRef by keyword and resolve matching DOIs on Sci-Hub. |
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
