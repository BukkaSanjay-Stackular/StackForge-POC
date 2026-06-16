"""
Traceability Matrix Generator.
Links requirements ↔ design components ↔ user stories for end-to-end traceability.
"""

import re
from pathlib import Path
from collections import defaultdict
from loguru import logger

from pipeline.utils.config import get_config
from pipeline.utils.llm_client import OpenCodeClient
from pipeline.models.schemas import TraceabilityLink, TraceabilityMatrix


TRACEABILITY_PROMPT = """You are a requirements engineer creating a traceability matrix.

Based on the project documentation below, identify traceability links between requirements, design elements, and user stories.

PROJECT DOCUMENTATION:
{context}

Return ONLY a JSON array of traceability links:

[
  {{
    "from_type": "requirement",
    "from_id": "APT-001",
    "to_type": "design",
    "to_id": "scr-patient-booking",
    "relationship": "implements"
  }},
  {{
    "from_type": "requirement",
    "from_id": "APT-002",
    "to_type": "user_story",
    "to_id": "US001",
    "relationship": "verifies"
  }}
]

**Link Types**:
- requirement → design: "implements" (design satisfies requirement)
- requirement → user_story: "derived_from" (story originated from req)
- design → user_story: "relates_to" (component relates to story)
- user_story → test_case: "verifies" (test validates story)

**Rules**:
- Every Must Have requirement must link to at least one design element
- Every user story should trace back to a requirement
- Use exact IDs as they appear in the docs"""


def extract_requirement_ids(text: str) -> list[str]:
    """Extract requirement IDs like APT-001, PAT-002 from text."""
    pattern = r'\b[A-Z]{3}-\d{3}\b'
    return re.findall(pattern, text)


def extract_screen_ids(text: str) -> list[str]:
    """Extract screen/component IDs like scr-patient-booking."""
    pattern = r'\bscr-[\w-]+\b'
    return re.findall(pattern, text)


def extract_component_ids(text: str) -> list[str]:
    """Extract component IDs like comp-doctor-card."""
    pattern = r'\bcomp-[\w-]+\b'
    return re.findall(pattern, text)


def generate_traceability_matrix(
    sub_docs_dir: Path | None = None,
    design_dir: Path | None = None,
    stories_dir: Path | None = None,
    client: OpenCodeClient | None = None,
) -> TraceabilityMatrix:
    """
    Generate complete traceability matrix from all pipeline artifacts.
    
    Args:
        sub_docs_dir: Directory containing sub-docs
        design_dir: Directory containing design artifacts
        stories_dir: Directory containing user stories
        client: Optional LLM client for AI-assisted linking
        
    Returns:
        TraceabilityMatrix with all links
    """
    config = get_config()
    sub_docs_dir = sub_docs_dir or Path(config.paths.sub_docs)
    design_dir = design_dir or Path(config.paths.design_artifacts)
    stories_dir = stories_dir or Path(config.paths.user_stories)
    
    logger.info(f"\n{'='*55}")
    logger.info(f"  GENERATING TRACEABILITY MATRIX")
    logger.info(f"{'='*55}")
    
    links = []
    
    # 1. Extract requirement IDs from sub-docs
    req_ids = set()
    if sub_docs_dir.exists():
        for md_file in sub_docs_dir.glob("*.md"):
            text = md_file.read_text(encoding="utf-8")
            found = extract_requirement_ids(text)
            req_ids.update(found)
    
    logger.info(f"  Found {len(req_ids)} requirement IDs: {sorted(req_ids)}")
    
    # 2. Extract design element IDs from design artifacts
    design_ids = set()
    if design_dir.exists():
        ui_path = design_dir / "ui_components.json"
        if ui_path.exists():
            import json
            data = json.loads(ui_path.read_text(encoding="utf-8"))
            for comp in data.get("components", []):
                comp_id = comp.get("id", "")
                if comp_id.startswith("scr-") or comp_id.startswith("comp-"):
                    design_ids.add(comp_id)
        
        # Also extract from all files
        for md_file in design_dir.glob("*.json"):
            text = md_file.read_text(encoding="utf-8")
            design_ids.update(extract_screen_ids(text))
            design_ids.update(extract_component_ids(text))
        
        # ADR IDs
        adr_dir = design_dir / "adr"
        if adr_dir.exists():
            for f in adr_dir.glob("*.md"):
                text = f.read_text(encoding="utf-8")
                adr_ids = re.findall(r'ADR-\d{3}', text)
                for aid in adr_ids:
                    links.append(TraceabilityLink(
                        from_type="design",
                        from_id=aid,
                        to_type="requirement",
                        to_id="multiple",  # Will be refined
                        relationship="relates_to",
                    ))
    
    logger.info(f"  Found {len(design_ids)} design element IDs")
    
    # 3. Extract user story IDs
    story_ids = set()
    if stories_dir.exists():
        stories_file = stories_dir / "user_stories.json"
        if stories_file.exists():
            import json
            data = json.loads(stories_file.read_text(encoding="utf-8"))
            for epic in data.get("epics", []):
                for feat in epic.get("features", []):
                    for us in feat.get("user_stories", []):
                        story_ids.add(us.get("id", ""))
        
        # Also extract from markdown
        for md_file in stories_dir.glob("*.md"):
            text = md_file.read_text(encoding="utf-8")
            story_ids.update(re.findall(r'\bUS\d{3}\b', text))
    
    logger.info(f"  Found {len(story_ids)} user story IDs: {sorted(story_ids)}")
    
    # 4. Build basic links (rule-based)
    # Link requirements to similar design elements by naming conventions
    req_to_design_map = {
        "APT": "scr-patient-booking",
        "PAT": "scr-patient-portal",
        "DOC": "scr-doctor-dashboard",
        "ADM": "scr-admin-panel",
        "NOT": "scr-notifications",
    }
    
    for req_id in req_ids:
        prefix = req_id.split("-")[0]
        design_id = req_to_design_map.get(prefix)
        if design_id:
            links.append(TraceabilityLink(
                from_type="requirement",
                from_id=req_id,
                to_type="design",
                to_id=design_id,
                relationship="implements",
            ))
    
    # Link user stories to requirements
    for story_id in story_ids:
        # Crude mapping: US prefix maps to certain req categories
        prefix_rank = int(story_id[2:]) if len(story_id) == 5 and story_id.startswith("US") else 0
        if req_ids and prefix_rank > 0:
            req_list = sorted(req_ids)
            idx = min(prefix_rank - 1, len(req_list) - 1)
            links.append(TraceabilityLink(
                from_type="user_story",
                from_id=story_id,
                to_type="requirement",
                to_id=req_list[idx],
                relationship="derived_from",
            ))
    
    matrix = TraceabilityMatrix(links=links)
    
    # 5. Save matrix
    output_dir = Path(config.paths.design_artifacts)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "traceability_matrix.json").write_text(
        matrix.model_dump_json(indent=2), encoding="utf-8"
    )
    
    # Generate markdown report
    _save_traceability_report(matrix, req_ids, design_ids, story_ids, output_dir)
    
    logger.info(f"  Total traceability links: {len(links)}")
    logger.info(f"  Saved: traceability_matrix.json")
    
    return matrix


def _save_traceability_report(
    matrix: TraceabilityMatrix,
    req_ids: set,
    design_ids: set,
    story_ids: set,
    output_dir: Path,
):
    """Save a readable markdown traceability report."""
    req_coverage = matrix.get_coverage("requirement", "design")
    story_coverage = matrix.get_coverage("user_story", "requirement")
    
    lines = [
        "# Traceability Matrix Report",
        "",
        f"**Generated:** SDLC Pipeline",
        "",
        "## Coverage Summary",
        "",
        "| Type | Total | Covered | Coverage |",
        "|------|-------|---------|----------|",
        f"| Requirements → Design | {req_coverage['total']} | {req_coverage['covered']} | {req_coverage['coverage_pct']:.0f}% |",
        f"| User Stories → Requirements | {story_coverage['total']} | {story_coverage['covered']} | {story_coverage['coverage_pct']:.0f}% |",
        "",
        "## Uncovered Items",
        "",
    ]
    
    if req_coverage["uncovered"]:
        lines.append("### Requirements without Design coverage")
        for r in req_coverage["uncovered"]:
            lines.append(f"- {r}")
        lines.append("")
    
    # Link details
    lines.append("## All Traceability Links")
    lines.append("")
    lines.append("| From | To | Relationship |")
    lines.append("|------|----|--------------|")
    for link in matrix.links:
        lines.append(f"| {link.from_type}:{link.from_id} | {link.to_type}:{link.to_id} | {link.relationship} |")
    
    (output_dir / "traceability_report.md").write_text("\n".join(lines), encoding="utf-8")