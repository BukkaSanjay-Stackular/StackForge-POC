# StackForge SDLC Pipeline

Automates raw project documents → structured SDLC artifacts: sub-docs, design diagrams, API specs, DB schemas, user stories, and traceability.

Powered by DeepSeek V4 Flash via OpenCode CLI.

## Quick Start

```bash
# 1. Drop your files into raw_docs/
#    Supported: PDF, DOCX, XLSX, CSV, TXT, PPTX, HTML, XML, JSON, EPUB, MD
mkdir raw_docs
# (copy your files here)

# 2. Setup
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .

# 3. Run full pipeline
sdlc-pipeline pipeline
```

## Pipeline Stages

| Stage | Input | Output |
|-------|-------|--------|
| **1. Convert** | `raw_docs/` (PDF, DOCX, TXT, CSV, etc.) | `markdown_docs/` — one .md per file |
| **2. Classify** | `markdown_docs/` — chunked via LLM | `sub_docs/` — 8 topic files (requirements, design, technical, timeline, budget, testing, integrations, team & process) |
| **3. Design** | `sub_docs/` | `design_artifacts/` — C4 architecture (Mermaid/PlantUML), OpenAPI 3.1 spec, PostgreSQL DDL+ERD, UI components, user journeys, ADRs |
| **4. Stories** | `sub_docs/` | `user_stories/` — Epics → Features → User Stories with acceptance criteria |
| **5. Trace** | All artifacts | Traceability matrix (req ↔ design ↔ stories) |
| **6. Quality** | All artifacts | 5 validation gates (completeness, coverage, consistency) |

## Commands

```bash
# Full pipeline (all 6 stages)
sdlc-pipeline pipeline

# Or run stages individually
sdlc-pipeline convert              # Stage 1: docs -> markdown
sdlc-pipeline classify             # Stage 2: markdown -> sub-docs
sdlc-pipeline design               # Stage 3: sub-docs -> design artifacts
sdlc-pipeline stories              # Stage 4: sub-docs -> user stories
sdlc-pipeline trace                # Stage 5: traceability matrix
sdlc-pipeline quality              # Stage 6: quality gates

# Utilities
sdlc-pipeline status               # Show current pipeline state
sdlc-pipeline reset --all          # Delete all outputs (markdown_docs/, sub_docs/, design_artifacts/, user_stories/)
sdlc-pipeline reset --hashes       # Reset content hashes only
sdlc-pipeline --help               # All available commands

# Options
sdlc-pipeline pipeline --stages convert,classify   # Run specific stages
sdlc-pipeline pipeline --full                      # Re-process everything (ignore cache)
```

## Example Workflow

```bash
# 1. Place files in raw_docs/
# 2. Convert + Classify + Design + Stories
sdlc-pipeline pipeline

# 3. Check results
sdlc-pipeline status
Get-ChildItem -Recurse sub_docs/ design_artifacts/ user_stories/
```

## Folder Structure

```
project-root/
├── raw_docs/              ← PLACE YOUR FILES HERE
│   ├── BRD_Project.docx
│   ├── Technical_Spec.pdf
│   └── requirements.csv
├── markdown_docs/         ← Auto-created (Stage 1)
├── sub_docs/              ← Auto-created (Stage 2)
├── design_artifacts/      ← Auto-created (Stage 3)
│   ├── architecture.mmd
│   ├── architecture.puml
│   ├── openapi.json
│   ├── schema.sql
│   ├── schema_er.puml
│   ├── ui_components.json
│   ├── user_journeys.json
│   └── adrs.md
├── user_stories/          ← Auto-created (Stage 4)
│   ├── user_stories.md
│   ├── epics_summary.md
│   └── user_stories.json
├── config.yaml            ← All settings (paths, models, thresholds)
├── .env                   ← API keys (STITCH_API_KEY)
└── pipeline/              ← Source code
```

## Configuration

All settings in `config.yaml`: LLM models, chunk sizes, quality thresholds, retry, logging.

## Stitch MCP (optional screen generation)

1. Set `STITCH_API_KEY=your_key` in `.env`
2. Enabled by default in `config.yaml`
3. Runs as part of `sdlc-pipeline design`
