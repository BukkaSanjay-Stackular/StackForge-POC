# StackForge SDLC Pipeline

Automates raw project documents → structured SDLC artifacts: sub-docs, design diagrams, API specs, DB schemas, user stories, and traceability.

Powered by DeepSeek V4 Flash via OpenCode CLI.

## Pipeline Stages

| Stage | Input | Output |
|-------|-------|--------|
| **1. Convert** | PDF, DOCX, TXT, CSV, etc. | Markdown files |
| **2. Classify** | Markdown chunks | 8 topic sub-docs (requirements, design, technical, timeline, budget, testing, integrations, team & process) |
| **3. Design** | Sub-docs | Architecture (C4/Mermaid/PlantUML), OpenAPI 3.1 spec, PostgreSQL DDL + ERD, UI components inventory, user journeys, ADRs |
| **4. Stories** | Sub-docs | Epics → Features → User Stories with acceptance criteria |
| **5. Trace** | All artifacts | Requirements ↔ Design ↔ Stories traceability matrix |
| **6. Quality** | All artifacts | 5 validation gates (completeness, coverage, consistency) |

## Setup

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

## Usage

```bash
# Full pipeline
sdlc-pipeline pipeline

# Individual stages
sdlc-pipeline convert
sdlc-pipeline classify
sdlc-pipeline design
sdlc-pipeline stories
sdlc-pipeline trace
sdlc-pipeline quality

# Status & reset
sdlc-pipeline status
sdlc-pipeline reset --all
```

## Stitch MCP (screen generation)

1. Set `STITCH_API_KEY=your_key` in `.env`
2. Enabled by default in `config.yaml`
3. Runs as part of `sdlc-pipeline design`

## Configuration

All settings in `config.yaml`: paths, LLM models, chunk sizes, quality thresholds, retry, logging.
