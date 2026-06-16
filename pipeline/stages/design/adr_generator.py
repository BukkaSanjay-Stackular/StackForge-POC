"""
Design Artifact Generator: Architecture Decision Records (ADRs).
"""

import json
from pathlib import Path
from loguru import logger

from pipeline.utils.config import get_config
from pipeline.utils.llm_client import OpenCodeClient
from pipeline.models.schemas import ADR

ADRS_PROMPT = """You are a senior software architect documenting Architecture Decision Records (ADRs).

Based on the project documentation below, identify key architectural decisions and record them as ADRs.

PROJECT DOCUMENTATION:
{context}

Return ONLY a JSON array of ADRs:

[
  {{
    "id": "ADR-001",
    "title": "Use React Native for mobile app development",
    "status": "accepted",
    "context": "The client requires native mobile apps for both Android and iOS. We need to choose between native development (Swift/Kotlin), React Native, or Flutter.",
    "decision": "We will use React Native for mobile app development. This allows code sharing between platforms, faster development cycles, and the team has existing React/TypeScript expertise from the web frontend.",
    "consequences": {{
      "positive": "Faster time-to-market, shared codebase, hot reload for faster iteration",
      "negative": "Performance limitations for complex animations, native module bridging needed for some features",
      "neutral": "Will need to maintain separate native entry points and platform-specific UI adaptations"
    }},
    "related_requirements": ["APT-001", "PAT-001", "DOC-001"]
  }}
]

**Required ADRs** (derive from docs):
1. Mobile framework choice (React Native vs Flutter vs Swift/Kotlin)
2. API architecture (REST vs GraphQL vs gRPC)
3. Authentication approach (JWT vs OAuth vs OTP-based)
4. Database choice (PostgreSQL + Redis)
5. Cloud provider (AWS vs Azure vs GCP)
6. Payment gateway integration (Razorpay approach)
7. WhatsApp API integration strategy
8. Medi-Plus EMR integration method
9. Offline mode strategy for mobile
10. Notification architecture (SMS + WhatsApp + Push)

**ADR Format** (Y-Statements):
- Title: Clear decision statement
- Context: Why this decision was needed, alternatives considered
- Decision: What was decided (not what will be decided later)
- Consequences: Positive, negative, neutral implications
- Related requirements: Trace back to specific requirement IDs"""


def generate_adrs(
    context: str,
    client: OpenCodeClient,
    output_dir: Path | None = None,
) -> list[ADR]:
    """Generate Architecture Decision Records from project context."""
    config = get_config()

    if not config.design_artifacts.generate.get("adrs", True):
        logger.info("  ADR generation disabled in config")
        return []

    logger.info("\n  Generating Architecture Decision Records...")

    try:
        result = client.call_structured(
            prompt=ADRS_PROMPT.format(context=context),
            response_model=list[ADR],
            label="ADRs",
        )
        
        # Validate raw list into ADR models
        if isinstance(result, list):
            result = [ADR(**item) if isinstance(item, dict) else item for item in result]
        
        if output_dir:
            adr_dir = output_dir / "adr"
            adr_dir.mkdir(parents=True, exist_ok=True)

            # Save individual ADR files
            for adr in result:
                adr_content = _format_adr_markdown(adr)
                (adr_dir / f"{adr.id}.md").write_text(adr_content, encoding="utf-8")

            # Save combined JSON
            (output_dir / "adrs.json").write_text(
                json.dumps([a.model_dump() for a in result], indent=2),
                encoding="utf-8",
            )

            logger.info(f"  Saved: {len(result)} ADRs in adr/")

        return result

    except Exception as e:
        logger.error(f"  ADR generation failed: {e}")
        return []


def _format_adr_markdown(adr: ADR) -> str:
    """Format an ADR as a Markdown document."""
    req_bullets = "\n".join(f"- {r}" for r in adr.related_requirements)
    return f"""# {adr.id}: {adr.title}

**Status:** {adr.status}

**Date:** Adopted

---

## Context

{adr.context}

---

## Decision

{adr.decision}

---

## Consequences

### Positive
{_format_bullets(adr.consequences.get('positive', ''))}

### Negative
{_format_bullets(adr.consequences.get('negative', ''))}

### Neutral
{_format_bullets(adr.consequences.get('neutral', ''))}

---

## Related Requirements

{req_bullets}
"""


def _format_bullets(text: str) -> str:
    """Format text as bullet points."""
    if not text:
        return "_None_"
    lines = text.split(". ")
    return "\n".join(f"- {line.strip()}." for line in lines if line.strip())