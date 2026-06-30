---
name: scientific-literature-search
description: Designs and documents reproducible scientific literature searches using OA-first MCP tools and accepted review-search practices. Use when the task involves finding papers, building database queries, DOI/title/keyword searches, systematic/scoping/narrative review searches, search logs, inclusion/exclusion boundaries, or source coverage across scholarly databases.
---

# Scientific Literature Search

## Core Rule

Run an OA-first, reproducible search. Do not rely on Sci-Hub fallback for bulk
searches. Use legal open-access routes first and record what was searched, when,
with what query, and what was found.

## Workflow

1. Define the review question and scope before searching.
   - Use PICO/PECO for intervention or exposure questions.
   - Use PCC for scoping reviews.
   - Use SPIDER for qualitative or mixed-methods evidence.
   - State population, phenomenon/intervention/exposure, comparator if relevant,
     outcomes, study designs, language/date limits, and exclusions.

2. Build search concepts.
   - Split the question into concept blocks.
   - Add synonyms, spelling variants, acronyms, MeSH/controlled vocabulary when
     the target database supports it, and known landmark authors or trials.
   - Prefer transparent Boolean logic: `(concept A synonyms) AND (concept B synonyms)`.
   - Avoid over-narrowing early searches with outcome terms unless recall is too broad.

3. Search multiple source classes.
   - Use this MCP server for OA-first DOI, title, keyword, and provider searches.
   - Use `search` / `fetch` for ChatGPT-compatible read-only search.
   - Use `search_scihub_by_keyword` only as OA-only keyword discovery.
   - Use `search_scihub_by_doi` or `search_scihub_by_title` for targeted paper
     lookup; report source provenance from the response.
   - Use integrated tools such as `search_papers`, `search_crossref`,
     `search_openalex`, `search_europepmc`, `search_pubmed`, `search_arxiv`,
     `search_unpaywall`, and `search_doaj` when exposed.

4. Track coverage and deduplicate.
   - Preserve DOI, title, authors, year, source database/provider, URL/PDF URL,
     retrieval status, and reason for inclusion/exclusion.
   - Deduplicate by DOI first, then normalized title plus year.
   - Keep near-duplicates visible until a human or explicit rule resolves them.

5. Document the search.
   - Report database/provider names, exact queries, date searched, result counts,
     limits/filters, and failed sources.
   - For systematic or scoping review work, structure the log so it can support a
     PRISMA-style flow diagram.
   - For formal systematic reviews, recommend peer review of the electronic
     search strategy using PRESS-style checks.

## Output Pattern

For search planning, return:

- Research question and framework.
- Inclusion/exclusion criteria.
- Concept blocks and draft Boolean strings.
- Source plan and why each source is included.
- Reproducible search log template.

For search execution, return:

- Search date and tool/provider used.
- Query or identifier used.
- Results table with DOI/title/year/source/URL/status.
- Notes on gaps, failed sources, and next searches.

## Quality Guardrails

- Separate search retrieval from quality appraisal; do not reject studies for
  quality until the appraisal skill is used.
- Do not infer full-text availability from a title alone.
- If no OA copy is found, report `not_found` and suggest institutional/library,
  author manuscript, preprint, or repository routes.
- Do not add CAPTCHA evasion, browser impersonation, proxy rotation, or automated
  paywall-circumvention strategies.

## Standards To Anchor

Use these as methodological anchors when relevant: PRISMA 2020 for reporting
review searches, PRISMA-S for search reporting detail, PRESS for peer review of
search strategies, Cochrane Handbook Chapter 4 for study identification, and
PROSPERO/OSF-style protocol registration for formal reviews.
