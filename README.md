# Doc Segmentation Pipeline

Converts raw documents → Markdown → Topic-based sub-docs using Mistral (local, via Ollama).

---

## Folder Structure

```
rag-agent/
├── raw_docs/          ← DROP YOUR FILES HERE (PDF, DOCX, etc.)
├── markdown_docs/     ← Auto-created: converted markdown files
├── sub_docs/          ← Auto-created: segmented sub-docs
│   └── doc_name/
│       ├── design.md
│       ├── timeline.md
│       └── requirements.md
├── pipeline.py        ← Main script
└── requirements.txt
```

---

## Setup

```bash
# 1. Create and activate virtual environment
python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1

# Mac/Linux
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Make sure Ollama is running with mistral pulled
ollama serve           # in a separate terminal
ollama pull mistral    # only needed once
```

---

## Usage

```bash
# Drop your files into raw_docs/ then:
python pipeline.py
```

---

## Output

- markdown_docs/ — one .md file per raw input doc
- sub_docs/<doc_name>/ — one .md file per detected topic

Example:
  sub_docs/
  └── project_brief/
      ├── design.md
      ├── timeline.md
      ├── budget.md
      └── requirements.md

---

## Config (edit top of pipeline.py)

CHUNK_SIZE_WORDS = 3000   (words per chunk sent to Mistral)
OLLAMA_MODEL     = mistral
OLLAMA_TIMEOUT   = 120s
