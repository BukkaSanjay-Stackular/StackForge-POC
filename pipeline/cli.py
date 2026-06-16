"""
SDLC Pipeline CLI — Typer-based command line interface.
"""

import time
import json
from pathlib import Path
from typing import Optional
import typer
from loguru import logger
from rich.console import Console
from rich.table import Table
from dotenv import load_dotenv

from pipeline.utils.config import load_config, get_config, get_path
from pipeline.utils.hashing import ContentHasher
from pipeline.utils.llm_client import create_client
from pipeline.stages.convert import convert_to_markdown
from pipeline.stages.classify import classify_chunks
from pipeline.stages.synthesize import synthesize_subdocs
from pipeline.stages.design import generate_all_design_artifacts, load_design_context
from pipeline.stages.user_stories import UserStoriesGenerator
from pipeline.stages.stitch_bridge import generate_screens_from_design
from pipeline.stages.traceability import generate_traceability_matrix
from pipeline.stages.quality_gates import run_quality_gates


app = typer.Typer(
    name="sdlc-pipeline",
    help="SDLC Pipeline - Automate requirements through design to user stories",
    add_completion=False,
)
console = Console()


def _setup_logging():
    """Configure structured logging."""
    config = get_config()
    log_level = config.logging.level.upper() if hasattr(config, "logging") else "INFO"
    logger.remove()
    logger.add(lambda msg: console.print(msg, markup=False), level=log_level)


def _get_hasher():
    """Get content hasher for incremental processing."""
    config = get_config()
    hash_path = get_path("content_hashes")
    return ContentHasher(hash_path, config.incremental.hash_algorithm)


@app.callback()
def main_callback(
    config_file: str = typer.Option("config.yaml", "--config", "-c", help="Path to configuration file"),
):
    """Load configuration on startup."""
    load_dotenv()
    try:
        load_config(config_file)
        _setup_logging()
    except Exception as e:
        console.print(f"[red]Failed to load config: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def convert(
    incremental: bool = typer.Option(True, "--incremental/--full", help="Only process changed files"),
):
    """Stage 1: Convert raw documents to Markdown."""
    hasher = _get_hasher() if incremental else None
    md_files = convert_to_markdown(hasher)
    
    if not md_files:
        console.print("[yellow]No files to convert.[/yellow]")
        return
    
    console.print(f"[green]Converted {len(md_files)} file(s) to markdown_docs/[/green]")


@app.command()
def classify(
    incremental: bool = typer.Option(True, "--incremental/--full", help="Only process changed files"),
):
    """Stage 2: Classify markdown chunks into SDLC topic sub-docs."""
    config = get_config()
    md_dir = get_path("markdown_docs")
    
    md_files = sorted(md_dir.glob("*.md"))
    if not md_files:
        console.print("[yellow]No markdown files found. Run 'convert' first.[/yellow]")
        return
    
    # Create client
    client = create_client(
        model=config.llm.classifier.get("model", config.llm.primary.get("model")),
        timeout=config.llm.classifier.get("timeout", config.llm.primary.get("timeout")),
    )
    
    # Classify chunks
    classifications = classify_chunks(md_files, client)
    
    # Synthesize into sub-docs
    subdocs = synthesize_subdocs(classifications)
    
    # Token summary
    client.print_summary()
    
    console.print(f"[green]Classified into {len(subdocs)} topic sub-docs[/green]")


@app.command()
def design(
    generate_all: bool = typer.Option(True, "--all/--no-all", help="Generate all design artifacts"),
    generate_screens: bool = typer.Option(True, "--screens/--no-screens", help="Generate screens via Stitch MCP"),
):
    """Stage 3: Generate all design artifacts from sub-docs."""
    config = get_config()
    
    # Load context from sub_docs
    context = load_design_context()
    if not context:
        console.print("[red]No context found. Run 'classify' first.[/red]")
        raise typer.Exit(code=1)
    
    # Create designer client
    client = create_client(
        model=config.llm.designer.get("model", config.llm.primary.get("model")),
        timeout=config.llm.designer.get("timeout", config.llm.primary.get("timeout")),
    )
    
    # Generate design artifacts
    if generate_all:
        artifacts = generate_all_design_artifacts(context=context, client=client)
        console.print(f"[green]Generated design artifacts in design_artifacts/[/green]")
    else:
        # Only selected ones
        from pipeline.stages.design.architecture import generate_architecture_diagram
        from pipeline.stages.design.api_spec import generate_openapi_spec
        from pipeline.stages.design.db_schema import generate_database_schema
        
        arch = generate_architecture_diagram(context, client)
        oas = generate_openapi_spec(context, client)
        db = generate_database_schema(context, client)
        
        console.print(f"[green]Architecture: {'OK' if arch else 'FAIL'}")
        console.print(f"OpenAPI: {'OK' if oas else 'FAIL'}")
        console.print(f"Database: {'OK' if db else 'FAIL'}[/green]")
    
    # Generate screens via Stitch
    if generate_screens:
        stitch_result = generate_screens_from_design()
        if "error" in stitch_result:
            console.print(f"[red]Stitch MCP: {stitch_result['error']}[/red]")
        elif stitch_result.get("skipped"):
            console.print("[yellow]Stitch MCP disabled in config[/yellow]")
        else:
            console.print(f"[green]Generated {stitch_result.get('screens_generated', 0)} screens via Stitch MCP[/green]")
    
    # Print token usage
    client.print_summary()


@app.command()
def stories(
    force: bool = typer.Option(False, "--force", "-f", help="Regenerate even if cached"),
):
    """Stage 4: Generate user stories from sub-docs."""
    config = get_config()
    
    generator = UserStoriesGenerator()
    epics = generator.generate()
    
    if epics:
        console.print(f"[green]Generated {len(epics)} epics with user stories in user_stories/[/green]")
    else:
        console.print("[red]User story generation failed[/red]")


@app.command()
def trace(
    force: bool = typer.Option(False, "--force", "-f", help="Regenerate even if cached"),
):
    """Generate traceability matrix from all artifacts."""
    matrix = generate_traceability_matrix()
    console.print(f"[green]Generated {len(matrix.links)} traceability links[/green]")


@app.command()
def quality():
    """Run all quality gates on artifacts."""
    results = run_quality_gates()
    
    table = Table(title="Quality Gate Results")
    table.add_column("Gate", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Issues")
    
    for r in results:
        status = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
        score = f"{r.score:.0f}%" if r.score else "-"
        issues = "; ".join(r.errors[:2]) or "; ".join(r.warnings[:2]) or "-"
        table.add_row(r.gate_name, status, score, issues)
    
    console.print(table)
    
    passed = sum(1 for r in results if r.passed)
    console.print(f"\n[bold]{passed}/{len(results)} gates passed[/bold]")


@app.command()
def pipeline(
    stages: str = typer.Option("convert,classify,design,stories,trace,quality", help="Comma-separated stages to run"),
    incremental: bool = typer.Option(True, "--incremental/--full", help="Process only changed files"),
):
    """Run the full pipeline through all stages."""
    config = get_config()
    stage_list = [s.strip() for s in stages.split(",")]
    
    console.print(f"[bold]SDLC Pipeline - Stages: {', '.join(stage_list)}[/bold]")
    console.print(f"[dim]{'='*55}[/dim]")
    
    start_time = time.time()
    stages_completed = []
    stages_failed = []
    
    # Stage 1: Convert
    if "convert" in stage_list:
        console.print("\n[bold cyan]Stage 1: Convert -> Markdown[/bold cyan]")
        hasher = _get_hasher() if incremental else None
        md_files = convert_to_markdown(hasher)
        if md_files:
            stages_completed.append("convert")
        else:
            stages_completed.append("convert (no new files)")
    
    # Stage 2: Classify
    if "classify" in stage_list:
        console.print("\n[bold cyan]Stage 2: Classify -> SDLC Topics[/bold cyan]")
        md_dir = get_path("markdown_docs")
        md_files = sorted(md_dir.glob("*.md"))
        
        if md_files:
            client = create_client(
                model=config.llm.classifier.get("model", config.llm.primary.get("model")),
                timeout=config.llm.classifier.get("timeout", config.llm.primary.get("timeout")),
            )
            classifications = classify_chunks(md_files, client)
            subdocs = synthesize_subdocs(classifications)
            client.print_summary()
            stages_completed.append("classify")
        else:
            console.print("[yellow]  No markdown files to classify[/yellow]")
            stages_completed.append("classify (skipped)")
    
    # Stage 3: Design
    if "design" in stage_list:
        console.print("\n[bold cyan]Stage 3: Design Artifacts[/bold cyan]")
        context = load_design_context()
        if context:
            client = create_client(
                model=config.llm.designer.get("model", config.llm.primary.get("model")),
                timeout=config.llm.designer.get("timeout", config.llm.primary.get("timeout")),
            )
            artifacts = generate_all_design_artifacts(context=context, client=client)
            client.print_summary()
            stages_completed.append("design")
        else:
            console.print("[yellow]  No context for design[/yellow]")
            stages_completed.append("design (skipped)")
    
    # Stage 4: User Stories
    if "stories" in stage_list:
        console.print("\n[bold cyan]Stage 4: User Stories[/bold cyan]")
        generator = UserStoriesGenerator()
        epics = generator.generate()
        if epics:
            stages_completed.append("stories")
        else:
            stages_failed.append("stories")
    
    # Stage 5: Traceability
    if "trace" in stage_list:
        console.print("\n[bold cyan]Stage 5: Traceability Matrix[/bold cyan]")
        matrix = generate_traceability_matrix()
        stages_completed.append("traceability")
    
    # Stage 6: Quality Gates
    if "quality" in stage_list:
        console.print("\n[bold cyan]Stage 6: Quality Gates[/bold cyan]")
        results = run_quality_gates()
        stages_completed.append("quality")
        
        # Print gate results
        for r in results:
            status = "PASS" if r.passed else "FAIL"
            console.print(f"  [{status}] {r.gate_name}")
    
    # Summary
    elapsed = time.time() - start_time
    console.print(f"\n[bold]{'='*55}[/bold]")
    console.print(f"[bold]PIPELINE COMPLETE[/bold]")
    console.print(f"Duration: {elapsed:.1f}s")
    console.print(f"Stages: {', '.join(stages_completed)}")
    if stages_failed:
        console.print(f"[red]Failed: {', '.join(stages_failed)}[/red]")
    console.print(f"[bold]{'='*55}[/bold]")


@app.command()
def status():
    """Show current pipeline status and statistics."""
    config = get_config()
    
    table = Table(title="Pipeline Status")
    table.add_column("Item", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details")
    
    # Check raw_docs
    raw_dir = get_path("raw_docs")
    raw_count = len(list(raw_dir.glob("*"))) if raw_dir.exists() else 0
    table.add_row("raw_docs/", "OK" if raw_count else "empty", f"{raw_count} files")
    
    # Check markdown_docs
    md_dir = get_path("markdown_docs")
    md_count = len(list(md_dir.glob("*.md"))) if md_dir.exists() else 0
    table.add_row("markdown_docs/", "OK" if md_count else "empty", f"{md_count} files")
    
    # Check sub_docs
    sd_dir = get_path("sub_docs")
    sd_count = len(list(sd_dir.glob("*.md"))) if sd_dir.exists() else 0
    sd_topics = [f.stem for f in sd_dir.glob("*.md")] if sd_dir.exists() else []
    status = "OK" if sd_count >= 6 else "partial" if sd_count > 0 else "none"
    table.add_row("sub_docs/", status, f"{sd_count} topics: {', '.join(sd_topics[:8])}")
    
    # Check design artifacts
    da_dir = get_path("design_artifacts")
    da_files = list(da_dir.glob("*")) if da_dir.exists() else []
    da_count = len(da_files)
    table.add_row("design_artifacts/", "OK" if da_count >= 5 else "partial" if da_count > 0 else "none", f"{da_count} files")
    
    # Check user stories
    us_dir = get_path("user_stories")
    us_count = len(list(us_dir.glob("*.md"))) if us_dir.exists() else 0
    table.add_row("user_stories/", "OK" if us_count else "empty", f"{us_count} files")
    
    # Check processed log
    log_path = get_path("processed_log")
    processed_count = len(log_path.read_text().splitlines()) if log_path.exists() else 0
    table.add_row("Processed files", "OK" if processed_count else "none", f"{processed_count} files")
    
    console.print(table)


@app.command()
def reset(
    all_data: bool = typer.Option(False, "--all", "-a", help="Remove all generated data"),
    hashes: bool = typer.Option(False, "--hashes", help="Reset content hashes only"),
):
    """Reset pipeline state (processed files, hashes, generated artifacts)."""
    config = get_config()
    
    if all_data:
        import shutil
        paths_to_clear = ["markdown_docs", "sub_docs", "user_stories", "design_artifacts"]
        for pname in paths_to_clear:
            p = Path(getattr(config.paths, pname))
            if p.exists():
                shutil.rmtree(p)
                console.print(f"[yellow]Cleared: {pname}/[/yellow]")
    
    if hashes:
        hash_path = get_path("content_hashes")
        if hash_path.exists():
            hash_path.unlink()
            console.print("[yellow]Reset: content hashes[/yellow]")
    
    console.print("[green]Reset complete[/green]")


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    app()