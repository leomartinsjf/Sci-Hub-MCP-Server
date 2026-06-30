FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SCIHUB_MCP_DOWNLOAD_DIR=/downloads

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY sci_hub_server.py sci_hub_search.py oa_resolver.py paper_search_integration.py ./

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

RUN mkdir -p /downloads

EXPOSE 8000

ENTRYPOINT ["sci-hub-mcp"]
CMD ["--transport", "stdio"]
