"""
Design Artifacts Orchestrator.
Generates all design artifacts from sub-docs: architecture, API spec, DB schema, UI components, ADRs.
"""

from pathlib import Path
from loguru import logger

from pipeline.utils.config import get_config
from pipeline.utils.llm_client import create_client, OpenCodeClient
from pipeline.models.schemas import DesignArtifacts
from pipeline.stages.design.architecture import generate_architecture_diagram
from pipeline.stages.design.api_spec import generate_openapi_spec
from pipeline.stages.design.db_schema import generate_database_schema
from pipeline.stages.design.ui_components import generate_ui_components, generate_user_journeys
from pipeline.stages.design.adr_generator import generate_adrs


def load_design_context(sub_docs_dir: Path | None = None) -> str:
    """Load context from sub-docs for design generation."""
    config = get_config()
    sub_docs_dir = sub_docs_dir or Path(config.paths.sub_docs)
    
    primary_docs = ["requirements.md", "design.md", "technical.md", "integrations.md"]
    context_parts = []
    
    if sub_docs_dir.exists():
        for fname in primary_docs:
            fpath = sub_docs_dir / fname
            if fpath.exists():
                content = fpath.read_text(encoding="utf-8").strip()
                if content:
                    context_parts.append(f"=== {fname.replace('.md','').upper()} ===\n{content}")
        
    if context_parts:
        logger.info(f"  Loaded design context from sub_docs/")
        return "\n\n".join(context_parts)
    
    # Fallback to markdown_docs
    md_dir = Path(config.paths.markdown_docs)
    if md_dir.exists():
        for f in sorted(md_dir.glob("*.md")):
            content = f.read_text(encoding="utf-8").strip()
            if content:
                context_parts.append(f"=== {f.stem.upper()} ===\n{content}")
        if context_parts:
            logger.info(f"  Fallback: loaded context from markdown_docs/")
            return "\n\n".join(context_parts)
    
    logger.warning("  No context found for design generation")
    return ""


def generate_all_design_artifacts(
    context: str | None = None,
    output_dir: Path | None = None,
    client: OpenCodeClient | None = None,
) -> DesignArtifacts:
    """
    Generate all design artifacts from project context.
    
    Args:
        context: Project context string. If None, loads from sub_docs.
        output_dir: Output directory for generated files. Defaults to design_artifacts/.
        client: LLM client. If None, creates a new one.
        
    Returns:
        DesignArtifacts with all generated artifacts.
    """
    config = get_config()
    out_dir = output_dir or Path(config.paths.design_artifacts)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Load context if not provided
    if context is None:
        context = load_design_context()
    
    if not context:
        logger.error("  No context available for design generation")
        return DesignArtifacts()
    
    # Create client if not provided
    if client is None:
        client = create_client(
            model=config.llm.designer.get("model", config.llm.primary.get("model")),
            timeout=config.llm.designer.get("timeout", config.llm.primary.get("timeout")),
        )
    
    logger.info(f"\n{'='*55}")
    logger.info(f"  GENERATING DESIGN ARTIFACTS")
    logger.info(f"{'='*55}")
    logger.info(f"  Context: {len(context.split()):,} words")
    
    artifacts = DesignArtifacts()
    
    # Generate each artifact
    architecture = generate_architecture_diagram(context, client, out_dir)
    if architecture:
        artifacts.architecture = architecture
    
    openapi = generate_openapi_spec(context, client, out_dir)
    if openapi:
        artifacts.openapi_spec = openapi
    
    db_schema = generate_database_schema(context, client, out_dir)
    if db_schema:
        artifacts.database_schema = db_schema
    
    ui_components = generate_ui_components(context, client, out_dir)
    if ui_components:
        artifacts.ui_components = ui_components
    
    journeys = generate_user_journeys(context, client, out_dir)
    if journeys:
        artifacts.user_journeys = journeys
    
    adrs = generate_adrs(context, client, out_dir)
    if adrs:
        artifacts.adrs = adrs
    
    # Save combined metadata
    (out_dir / "design_artifacts.json").write_text(
        artifacts.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
    )
    
    logger.info(f"\n{'='*55}")
    logger.info(f"  DESIGN ARTIFACTS GENERATED:")
    logger.info(f"  Architecture: {'YES' if artifacts.architecture else 'NO'}")
    logger.info(f"  OpenAPI Spec: {'YES' if artifacts.openapi_spec else 'NO'}")
    logger.info(f"  Database Schema: {'YES' if artifacts.database_schema else 'NO'}")
    logger.info(f"  UI Components: {'YES' if artifacts.ui_components else 'NO'}")
    logger.info(f"  User Journeys: {len(artifacts.user_journeys)}")
    logger.info(f"  ADRs: {len(artifacts.adrs)}")
    logger.info(f"  Output: {out_dir}/")
    logger.info(f"{'='*55}\n")
    
    return artifacts


if __name__ == "__main__":
    generate_all_design_artifacts()