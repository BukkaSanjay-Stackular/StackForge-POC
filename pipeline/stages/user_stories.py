"""
Enhanced User Story Generator.
Uses structured output via Instructor for reliable Epic → Feature → User Story generation.
"""

import json
import re
from pathlib import Path
from loguru import logger

from pipeline.utils.config import get_config, get_path
from pipeline.utils.llm_client import create_client, OpenCodeClient
from pipeline.models.schemas import (
    Epic, Feature, UserStory, AcceptanceCriterion, Priority, StoryPoints,
)


EPICS_PROMPT = """You are a senior product manager creating epics for an SDLC project.

Based on the project documentation below, identify the main Epics (major functional areas).

PROJECT DOCUMENTATION:
{context}

Return ONLY a JSON array of epics. Each epic must have:
- id: "E001", "E002" etc.
- title: short epic name
- description: one sentence describing what this epic covers

Generate {min_epics}-{max_epics} epics based ONLY on what is mentioned in the documents.

Example:
[
  {{"id": "E001", "title": "Patient Appointment Management", "description": "All features related to booking, rescheduling and cancelling appointments."}},
  {{"id": "E002", "title": "Patient Portal", "description": "Patient-facing features for viewing records, prescriptions and invoices."}}
]"""


FEATURES_PROMPT = """You are a senior product manager writing a backlog for an SDLC project.

For the epic below, generate Features and User Stories based on the project documentation.

EPIC:
ID: {epic_id}
Title: {epic_title}
Description: {epic_description}

RULES:
- Generate {min_features}-{max_features} features for this epic
- Generate {min_stories}-{max_stories} user stories per feature
- Every user story MUST use this exact format:
  "As a [user type], I want to [action], so that [benefit]."
- Every user story MUST have:
  - acceptance_criteria: 3 items in Given/When/Then format
  - priority: "Must Have", "Should Have", or "Could Have"
  - story_points: 1, 2, 3, 5, or 8
- Base everything ONLY on what is mentioned in the documentation
- Do NOT invent features not in the docs

Valid priorities: {priorities}
Valid story points: {story_points}

PROJECT DOCUMENTATION (relevant excerpt):
{context}

Return ONLY a JSON object with a "features" array matching this structure:
{{
  "features": [
    {{
      "id": "F001",
      "title": "Feature title",
      "description": "What this feature delivers",
      "user_stories": [
        {{
          "id": "US001",
          "title": "Short title",
          "story": "As a [user], I want to [action], so that [benefit].",
          "acceptance_criteria": [
            {{"given": "context", "when": "action", "then": "result"}},
            {{"given": "context", "when": "action", "then": "result"}},
            {{"given": "context", "when": "action", "then": "result"}}
          ],
          "priority": "Must Have",
          "story_points": 3
        }}
      ]
    }}
  ]
}}"""


class UserStoriesGenerator:
    """Generates epics, features, and user stories from project context."""
    
    def __init__(self, client: OpenCodeClient | None = None):
        self.config = get_config()
        self.client = client or create_client(
            model=self.config.llm.primary.get("model"),
            timeout=self.config.llm.primary.get("timeout"),
        )
    
    def load_context(self) -> str:
        """Load context from sub_docs or markdown_docs."""
        context_parts = []
        sub_docs_dir = get_path("sub_docs")
        
        if sub_docs_dir.exists():
            primary_docs = ["requirements.md", "design.md", "integrations.md", "technical.md"]
            for fname in primary_docs:
                fpath = sub_docs_dir / fname
                if fpath.exists():
                    content = fpath.read_text(encoding="utf-8").strip()
                    if content:
                        context_parts.append(f"=== {fname.replace('.md','').upper()} ===\n{content}")
        
        if context_parts:
            return "\n\n".join(context_parts)
        
        # Fallback
        md_dir = get_path("markdown_docs")
        if md_dir.exists():
            for f in sorted(md_dir.glob("*.md")):
                content = f.read_text(encoding="utf-8").strip()
                if content:
                    context_parts.append(f"=== {f.stem.upper()} ===\n{content}")
            return "\n\n".join(context_parts)
        
        return ""
    
    def _truncate_context(self, context: str, max_words: int) -> str:
        words = context.split()
        if len(words) > max_words:
            return " ".join(words[:max_words])
        return context
    
    def _extract_relevant_context(self, context: str, epic_title: str, max_words: int) -> str:
        """Extract paragraphs most relevant to this epic."""
        keywords = [w.lower() for w in epic_title.split() if len(w) > 3]
        paragraphs = [p.strip() for p in re.split(r'\n\n+', context) if p.strip()]
        
        scored = []
        for para in paragraphs:
            para_lower = para.lower()
            score = sum(para_lower.count(kw) for kw in keywords)
            scored.append((score, para))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        selected, word_count = [], 0
        for score, para in scored:
            wc = len(para.split())
            if word_count + wc > max_words:
                break
            selected.append(para)
            word_count += wc
        
        if selected:
            return "\n\n".join(selected)
        return self._truncate_context(context, max_words)
    
    def _generate_epics(self, context: str) -> list[Epic]:
        """Generate epics list."""
        us_config = self.config.user_stories
        context = self._truncate_context(context, us_config.epic_context_words)
        
        prompt = EPICS_PROMPT.format(
            context=context,
            min_epics=us_config.min_epics,
            max_epics=us_config.max_epics,
        )
        
        result = self.client.call_structured(
            prompt=prompt,
            response_model=list[Epic],
            label="Generating Epics",
        )
        
        # Validate raw list into Epic models
        if isinstance(result, list):
            result = [Epic(**item) if isinstance(item, dict) else item for item in result]
        
        # Filter out features from the initial response (they'll be empty)
        for epic in result:
            epic.features = []
        
        return result
    
    def _generate_features_for_epic(self, epic: Epic, full_context: str) -> Epic:
        """Generate features and user stories for one epic."""
        us_config = self.config.user_stories
        relevant_context = self._extract_relevant_context(
            full_context, epic.title, us_config.max_context_words
        )
        
        feature_prompt = FEATURES_PROMPT.format(
            epic_id=epic.id,
            epic_title=epic.title,
            epic_description=epic.description,
            context=relevant_context,
            min_features=us_config.features_per_epic[0],
            max_features=us_config.features_per_epic[1],
            min_stories=us_config.stories_per_feature[0],
            max_stories=us_config.stories_per_feature[1],
            priorities=", ".join(us_config.priority_values),
            story_points=", ".join(str(sp) for sp in us_config.story_point_values),
        )
        
        result = self.client.call_structured(
            prompt=feature_prompt,
            response_model=dict,  # Just get dict so we can renumber
            label=f"Features for {epic.id}: {epic.title}",
        )
        
        features = []
        feature_list = result.get("features", []) if isinstance(result, dict) else (result if isinstance(result, list) else [])
        
        for i, feat_data in enumerate(feature_list):
            feature = Feature(
                id=f"F{i+1:03d}",
                title=feat_data.get("title", ""),
                description=feat_data.get("description", ""),
                user_stories=[
                    UserStory(
                        id=f"US{j+1:03d}",
                        title=us.get("title", ""),
                        story=us.get("story", ""),
                        acceptance_criteria=[
                            AcceptanceCriterion(**ac) if isinstance(ac, dict)
                            else AcceptanceCriterion(given=ac, when="", then="") if isinstance(ac, str) and "when" not in ac
                            else AcceptanceCriterion(given="", when="", then=ac)
                            for ac in us.get("acceptance_criteria", [])
                        ],
                        priority=us.get("priority", "Must Have"),
                        story_points=us.get("story_points", 3),
                    )
                    for j, us in enumerate(feat_data.get("user_stories", []))
                ],
            )
            features.append(feature)
        
        epic.features = features
        return epic
    
    def generate(self, output_dir: Path | None = None) -> list[Epic]:
        """
        Run the full user story generation pipeline.
        
        Returns:
            List of complete Epics with features and user stories
        """
        out_dir = output_dir or get_path("user_stories")
        out_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"\n{'='*55}")
        logger.info(f"  GENERATING USER STORIES")
        logger.info(f"{'='*55}")
        
        # Load context
        context = self.load_context()
        if not context:
            logger.error("  No context found. Run pipeline.py first.")
            return []
        
        logger.info(f"  Context: {len(context.split()):,} words")
        
        # Step 1: Generate epics
        logger.info("\n  Step 1: Identifying Epics...")
        epics = self._generate_epics(context)
        if not epics:
            logger.error("  Failed to generate epics")
            return []
        logger.info(f"  Found {len(epics)} epics: {[e.title for e in epics]}")
        
        # Step 2: Generate features + user stories per epic
        logger.info("\n  Step 2: Generating Features & User Stories...")
        full_epics = []
        for epic in epics:
            enriched = self._generate_features_for_epic(epic, context)
            full_epics.append(enriched)
            
            feat_count = len(enriched.features)
            us_count = sum(len(f.user_stories) for f in enriched.features)
            sp_count = sum(us.story_points.value for f in enriched.features for us in f.user_stories)
            logger.info(f"    {epic.id}: {feat_count} features, {us_count} stories, {sp_count} SP")
        
        # Save outputs
        self._save_outputs(full_epics, out_dir)
        
        # Token summary
        self.client.print_summary()
        
        return full_epics
    
    def _save_outputs(self, epics: list[Epic], out_dir: Path):
        """Save all outputs in multiple formats."""
        project_name = "MediBook - Patient Portal & Clinic Management System"
        total_us = sum(len(f.user_stories) for e in epics for f in e.features)
        total_sp = sum(us.story_points.value for e in epics for f in e.features for us in f.user_stories)
        
        # User stories markdown
        md_content = _render_user_stories_md(project_name, epics, self.client.model)
        (out_dir / "user_stories.md").write_text(md_content, encoding="utf-8")
        
        # Epics summary
        summary_content = _render_epics_summary_md(project_name, epics)
        (out_dir / "epics_summary.md").write_text(summary_content, encoding="utf-8")
        
        # JSON output
        json_output = {
            "project_name": project_name,
            "epics": [e.model_dump() for e in epics],
            "metadata": {
                "model": self.client.model,
                "total_epics": len(epics),
                "total_features": sum(len(e.features) for e in epics),
                "total_stories": total_us,
                "total_story_points": total_sp,
            }
        }
        (out_dir / "user_stories.json").write_text(
            json.dumps(json_output, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        
        logger.info(f"\n  Saved:")
        logger.info(f"    {out_dir}/user_stories.md ({Path(out_dir / 'user_stories.md').stat().st_size:,} bytes)")
        logger.info(f"    {out_dir}/epics_summary.md")
        logger.info(f"    {out_dir}/user_stories.json")
        logger.info(f"\n  Total: {len(epics)} Epics, {sum(len(e.features) for e in epics)} Features, {total_us} Stories, {total_sp} SP")


def _render_user_stories_md(project_name: str, epics: list[Epic], model_name: str) -> str:
    """Render user stories as comprehensive Markdown."""
    total_features = sum(len(e.features) for e in epics)
    total_us = sum(len(f.user_stories) for e in epics for f in e.features)
    total_sp = sum(us.story_points.value for e in epics for f in e.features for us in f.user_stories)
    
    lines = [
        f"# {project_name} — User Stories & Backlog",
        f"\n**Generated by:** SDLC Pipeline | **Model:** {model_name}",
        f"\n| Metric | Count |",
        f"|---|---|",
        f"| Epics | {len(epics)} |",
        f"| Features | {total_features} |",
        f"| User Stories | {total_us} |",
        f"| Total Story Points | {total_sp} |",
        "\n---\n",
    ]
    
    for epic in epics:
        lines.append(f"## Epic {epic.id}: {epic.title}")
        lines.append(f"\n_{epic.description}_\n")
        
        for feat in epic.features:
            lines.append(f"### Feature {feat.id}: {feat.title}")
            lines.append(f"\n_{feat.description}_\n")
            
            for us in feat.user_stories:
                priority_badge = {"Must Have": "HIGH", "Should Have": "MED", "Could Have": "LOW"}.get(us.priority, "?")
                lines.append(f"#### [{priority_badge}] {us.id}: {us.title}")
                lines.append(f"\n**Priority:** {us.priority} | **SP:** {us.story_points.value}\n")
                lines.append(f"**Story:**\n> {us.story}\n")
                lines.append("**Acceptance Criteria:**")
                for ac in us.acceptance_criteria:
                    lines.append(f"- {ac.to_gherkin()}")
                lines.append("")
        
        lines.append("---\n")
    
    return "\n".join(lines)


def _render_epics_summary_md(project_name: str, epics: list[Epic]) -> str:
    """Render a concise epics summary table."""
    total_us = sum(len(f.user_stories) for e in epics for f in e.features)
    total_sp = sum(us.story_points.value for e in epics for f in e.features for us in f.user_stories)
    
    lines = [
        f"# {project_name} — Epics & Features Summary\n",
        f"| Metric | Count |",
        f"|---|---|",
        f"| Epics | {len(epics)} |",
        f"| Features | {sum(len(e.features) for e in epics)} |",
        f"| User Stories | {total_us} |",
        f"| Total Story Points | {total_sp} |",
        "",
    ]
    
    for epic in epics:
        lines.append(f"\n## {epic.id}: {epic.title}")
        lines.append(f"_{epic.description}_\n")
        lines.append("| Feature | Stories | SP | Priority Mix |")
        lines.append("|---|---|---|---|")
        for feat in epic.features:
            us_list = feat.user_stories
            sp = sum(us.story_points.value for us in us_list)
            must_count = sum(1 for us in us_list if us.priority == "Must Have")
            should_count = sum(1 for us in us_list if us.priority == "Should Have")
            could_count = sum(1 for us in us_list if us.priority == "Could Have")
            lines.append(f"| {feat.id}: {feat.title} | {len(us_list)} | {sp} | M:{must_count} S:{should_count} C:{could_count} |")
    
    return "\n".join(lines)