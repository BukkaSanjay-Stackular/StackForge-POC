"""
Quality Gates / Validation Stage.
Validates pipeline outputs for completeness, correctness, and consistency.
"""

import json
import re
from pathlib import Path
from loguru import logger

from pipeline.utils.config import get_config
from pipeline.models.schemas import QualityGateResult


def run_quality_gates(
    sub_docs_dir: Path | None = None,
    design_dir: Path | None = None,
) -> list[QualityGateResult]:
    """
    Run all quality gates on pipeline artifacts.
    
    Args:
        sub_docs_dir: Directory containing sub-docs
        design_dir: Directory containing design artifacts
        
    Returns:
        List of QualityGateResult for each gate
    """
    config = get_config()
    sub_docs_dir = sub_docs_dir or Path(config.paths.sub_docs)
    design_dir = design_dir or Path(config.paths.design_artifacts)
    
    if not config.quality_gates.enabled:
        logger.info("  Quality gates disabled in config")
        return []
    
    logger.info(f"\n{'='*55}")
    logger.info(f"  RUNNING QUALITY GATES")
    logger.info(f"{'='*55}")
    
    results = []
    
    # Gate 1: All 8 sub-docs exist
    results.append(_check_subdoc_completeness(sub_docs_dir))
    
    # Gate 2: Requirements completeness (MoSCoW coverage)
    results.append(_check_requirements_completeness(sub_docs_dir))
    
    # Gate 3: Design coverage of requirements
    results.append(_check_design_coverage(sub_docs_dir, design_dir))
    
    # Gate 4: Cross-document consistency
    results.append(_check_cross_doc_consistency(sub_docs_dir))
    
    # Gate 5: Design artifacts completeness
    results.append(_check_design_artifacts(design_dir))
    
    # Summary
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    logger.info(f"\n{'='*55}")
    logger.info(f"  QUALITY GATES: {passed}/{total} PASSED")
    for r in results:
        icon = "PASS" if r.passed else "FAIL"
        logger.info(f"    [{icon}] {r.gate_name}")
        if r.warnings:
            for w in r.warnings[:3]:
                logger.warning(f"           {w}")
        if r.errors:
            for e in r.errors[:3]:
                logger.error(f"           {e}")
    logger.info(f"{'='*55}\n")
    
    # Save results
    (sub_docs_dir.parent / "quality_gates.json").write_text(
        json.dumps([r.model_dump() for r in results], indent=2),
        encoding="utf-8",
    )
    
    return results


def _check_subdoc_completeness(sub_docs_dir: Path) -> QualityGateResult:
    """Gate 1: Check that all 8 SDLC sub-docs exist and are non-empty."""
    config = get_config()
    expected_topics = config.sdlc_topics
    
    errors = []
    warnings = []
    
    for topic in expected_topics:
        fpath = sub_docs_dir / f"{topic}.md"
        if not fpath.exists():
            errors.append(f"Missing sub-doc: {topic}.md")
        elif fpath.stat().st_size == 0:
            errors.append(f"Empty sub-doc: {topic}.md")
    
    # Check for files with very low content
    for topic in expected_topics:
        fpath = sub_docs_dir / f"{topic}.md"
        if fpath.exists() and fpath.stat().st_size < 100:
            warnings.append(f"Very small sub-doc: {topic}.md ({fpath.stat().st_size} bytes)")
    
    return QualityGateResult(
        gate_name="Sub-doc Completeness",
        passed=len(errors) == 0,
        score=len([t for t in expected_topics if (sub_docs_dir / f"{t}.md").exists()]) / len(expected_topics) * 100 if expected_topics else 0,
        errors=errors,
        warnings=warnings,
    )


def _check_requirements_completeness(sub_docs_dir: Path) -> QualityGateResult:
    """Gate 2: Check requirements follow MoSCoW and have IDs."""
    config = get_config()
    req_path = sub_docs_dir / "requirements.md"
    
    errors = []
    warnings = []
    
    if not req_path.exists():
        return QualityGateResult(
            gate_name="Requirements Completeness",
            passed=False,
            errors=["requirements.md not found"],
        )
    
    text = req_path.read_text(encoding="utf-8")
    
    # Check for requirement IDs
    import re
    req_ids = re.findall(r'\b[A-Z]{3}-\d{3}\b', text)
    if not req_ids:
        errors.append("No requirement IDs found (e.g., APT-001)")
    else:
        # Check MoSCoW coverage
        priorities = re.findall(r'Must have|Should have|Could have', text, re.IGNORECASE)
        if "Must have" not in text and "Must Have" not in text:
            warnings.append("No Must Have priorities found")
        if "Should have" not in text and "Should Have" not in text:
            warnings.append("No Should Have priorities found")
    
    return QualityGateResult(
        gate_name="Requirements Completeness",
        passed=len(errors) == 0,
        score=len(req_ids) if req_ids else 0,
        details={"requirement_ids_found": len(req_ids)},
        errors=errors,
        warnings=warnings,
    )


def _check_design_coverage(sub_docs_dir: Path, design_dir: Path) -> QualityGateResult:
    """Gate 3: Check that design artifacts cover key requirements."""
    config = get_config()
    req_path = sub_docs_dir / "requirements.md"
    
    errors = []
    warnings = []
    covered = 0
    total = 0
    
    if not req_path.exists():
        return QualityGateResult(
            gate_name="Design Coverage",
            passed=False,
            errors=["requirements.md not found"],
        )
    
    req_text = req_path.read_text(encoding="utf-8")
    
    # Key requirement categories that should be covered by design
    key_areas = [
        "appointment booking",
        "patient portal",
        "doctor dashboard",
        "admin panel",
        "notification",
        "payment",
        "prescription",
    ]
    
    # Check design artifacts exist
    ui_path = design_dir / "ui_components.json" if design_dir.exists() else None
    arch_path = design_dir / "architecture.json" if design_dir.exists() else None
    db_path = design_dir / "database_schema.json" if design_dir.exists() else None
    
    design_artifacts_exist = sum([
        1 for p in [ui_path, arch_path, db_path] 
        if p is not None and p.exists()
    ])
    
    if design_artifacts_exist < 2:
        errors.append(f"Only {design_artifacts_exist}/3 design artifacts generated")
    
    # Check key areas mentioned in requirements are in design
    if ui_path and ui_path.exists():
        import json
        ui_text = ui_path.read_text(encoding="utf-8").lower()
        for area in key_areas:
            total += 1
            if area.lower() in ui_text:
                covered += 1
            else:
                warnings.append(f"Design may not cover: {area}")
    
    coverage_pct = (covered / total * 100) if total > 0 else 0
    threshold = config.quality_gates.design_coverage.get("min_requirement_coverage", 0.8) * 100
    
    return QualityGateResult(
        gate_name="Design Coverage",
        passed=coverage_pct >= threshold,
        score=coverage_pct,
        details={
            "key_areas_covered": covered,
            "total_key_areas": total,
            "coverage_pct": coverage_pct,
            "design_artifacts_exist": design_artifacts_exist,
        },
        errors=errors,
        warnings=warnings,
    )


def _check_cross_doc_consistency(sub_docs_dir: Path) -> QualityGateResult:
    """Gate 4: Check for contradictions across sub-docs."""
    config = get_config()
    
    if not config.quality_gates.cross_doc_consistency.get("enabled", True):
        return QualityGateResult(
            gate_name="Cross-doc Consistency",
            passed=True,
            details={"skipped": "Disabled in config"},
        )
    
    errors = []
    warnings = []
    
    # Read all sub-docs
    subdocs = {}
    for md_file in sub_docs_dir.glob("*.md"):
        subdocs[md_file.stem] = md_file.read_text(encoding="utf-8")
    
    # Check for tech stack consistency between technical.md and others
    if "technical" in subdocs and "integrations" in subdocs:
        tech_text = subdocs["technical"].lower()
        int_text = subdocs["integrations"].lower()
        
        # If integrations mentions specific APIs, check technical mentions them too
        api_patterns = re.findall(r'razorpay|tally|whatsapp|medi-plus', int_text)
        for api in api_patterns:
            if api not in tech_text:
                warnings.append(f"Integration {api} mentioned in integrations.md but not in technical.md")
    
    # Check timeline vs budget consistency
    if "timeline" in subdocs and "budget" in subdocs:
        timeline_text = subdocs["timeline"].lower()
        budget_text = subdocs["budget"].lower()
        
        # Look for phase mentions in both
        phase_pattern = re.findall(r'phase\s+\d+', timeline_text)
        for phase in phase_pattern:
            if phase not in budget_text:
                warnings.append(f"{phase} in timeline.md but not in budget.md")
    
    return QualityGateResult(
        gate_name="Cross-doc Consistency",
        passed=len(errors) == 0,
        score=max(0, 100 - len(warnings) * 10),
        errors=errors,
        warnings=warnings,
    )


def _check_design_artifacts(design_dir: Path) -> QualityGateResult:
    """Gate 5: Check design artifacts are complete and consistent."""
    if not design_dir or not design_dir.exists():
        return QualityGateResult(
            gate_name="Design Artifacts",
            passed=False,
            errors=["Design artifacts directory not found"],
        )
    
    errors = []
    warnings = []
    artifacts_found = []
    
    expected_files = [
        "architecture.json", "architecture.mmd",
        "openapi.json", "openapi.yaml",
        "database_schema.json", "schema.sql",
        "ui_components.json",
        "user_journeys.json",
        "adrs.json",
        "traceability_matrix.json",
    ]
    
    for fname in expected_files:
        fpath = design_dir / fname
        if fpath.exists():
            artifacts_found.append(fname)
        else:
            warnings.append(f"Missing design artifact: {fname}")
    
    return QualityGateResult(
        gate_name="Design Artifacts",
        passed=len(errors) == 0,
        score=len(artifacts_found) / len(expected_files) * 100,
        details={
            "artifacts_found": len(artifacts_found),
            "expected_artifacts": len(expected_files),
            "completeness_pct": len(artifacts_found) / len(expected_files) * 100,
            "artifacts_generated": artifacts_found,
            "missing_artifacts": [f for f in expected_files if f not in artifacts_found],
        },
        errors=errors,
        warnings=warnings,
    )