# Scientific Skills

This repository includes four cross-vendor agent skills for scientific literature
work. They are intentionally small and procedural, so an agent can combine them
with the MCP paper-search tools without loading a large methods manual into
context.

## Skill Locations

OpenAI/Codex:

```text
.agents/skills/
```

Anthropic/Claude Code:

```text
.claude/skills/
```

The skill names are the same in both locations:

- `scientific-literature-search`
- `literature-review-synthesis`
- `research-quality-appraisal`
- `research-impact-assessment`

## Recommended Use

Use `scientific-literature-search` before retrieval-heavy tasks. It focuses on
question framing, query construction, source coverage, deduplication, and search
logs.

Use `literature-review-synthesis` after a paper set exists. It focuses on
extraction matrices, evidence grouping, cautious synthesis, and review-ready
prose.

Use `research-quality-appraisal` before judging credibility. It routes appraisal
to design-appropriate tools such as RoB 2, ROBINS-I, AMSTAR 2, NIH/JBI/CASP,
QUADAS-2, MMAT, and GRADE.

Use `research-impact-assessment` when the question is importance or influence
rather than internal validity. It follows responsible-metrics principles and
keeps citation, policy, practice, implementation, and social impact separate.

## Method Anchors

The skills are built around these current best-practice anchors:

- PRISMA 2020 and PRISMA-S for transparent review and search reporting.
- PRESS for peer review of electronic search strategies.
- Cochrane Handbook guidance for identifying, selecting, and synthesizing studies.
- RoB 2 and ROBINS-I for risk of bias in randomized and non-randomized studies.
- AMSTAR 2, NIH, JBI, CASP, QUADAS-2, and MMAT for design-specific appraisal.
- GRADE for certainty of evidence across a body of literature.
- DORA and the Leiden Manifesto for responsible research-impact assessment.

The skills do not encode full copyrighted checklists. When exact item-level
completion is required, retrieve the current official checklist and apply it
explicitly.

## Safety Boundary

The skills preserve this repository's OA-first architecture. They should not add
CAPTCHA evasion, browser impersonation, proxy rotation, cookie workarounds, or
automated paywall-circumvention strategies.
