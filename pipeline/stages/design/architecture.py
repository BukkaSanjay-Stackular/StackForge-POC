"""
Design Artifact Generator: System Architecture Diagram (C4 Model).
Generates Mermaid and PlantUML diagrams from requirements + technical docs.
"""

import json
from pathlib import Path
from loguru import logger

from pipeline.utils.config import get_config
from pipeline.utils.llm_client import create_client, OpenCodeClient
from pipeline.models.schemas import ArchitectureDiagram, ArchitectureComponent, DesignArtifacts


ARCHITECTURE_PROMPT = """You are a senior software architect creating a C4 architecture diagram.

Based on the project documentation below, generate a C4 **Container Diagram** (level 2) showing:
- External actors (patients, doctors, admins, external systems)
- Containers (web app, mobile apps, API gateway, services, databases, queues)
- External systems (Medi-Plus EMR, Tally ERP, Razorpay, WhatsApp API, SMS gateway)
- Key relationships and data flows

PROJECT DOCUMENTATION:
{context}

Return ONLY a valid JSON object matching this schema:
{{
  "title": "MediBook Platform - Container Diagram",
  "scope": "container",
  "components": [
    {{
      "name": "Patient Mobile App",
      "type": "container",
      "description": "Native iOS/Android app for patients to book appointments, view records",
      "technology": "React Native / Swift / Kotlin",
      "relationships": [
        {{"target": "API Gateway", "description": "HTTPS/REST", "technology": "JSON over TLS"}}
      ]
    }},
    {{
      "name": "API Gateway",
      "type": "container",
      "description": "Entry point for all client requests, handles auth, rate limiting, routing",
      "technology": "Kong / AWS API Gateway / NGINX",
      "relationships": [
        {{"target": "Appointment Service", "description": "gRPC/REST", "technology": "Protocol Buffers"}}
      ]
    }}
  ]
}}

Rules:
- Include ALL external systems mentioned in integrations (Medi-Plus, Tally, Razorpay, WhatsApp, SMS)
- Show databases explicitly (PostgreSQL, Redis)
- Show message queues if async processing mentioned
- Use standard C4 types: person, software_system, container, component, database, queue, external_system
- Relationships must have target, description, and technology
- Generate 10-20 components for a comprehensive diagram"""


def generate_architecture_diagram(
    context: str,
    client: OpenCodeClient,
    output_dir: Path | None = None,
) -> ArchitectureDiagram:
    """Generate C4 architecture diagram from project context."""
    config = get_config()
    
    if not config.design_artifacts.generate.get("architecture_diagram", True):
        logger.info("  Architecture diagram generation disabled in config")
        return None
    
    logger.info("\n  Generating architecture diagram...")
    
    prompt = ARCHITECTURE_PROMPT.format(context=context)
    
    try:
        result = client.call_structured(
            prompt=prompt,
            response_model=ArchitectureDiagram,
            label="Architecture diagram",
        )
        
        # Generate Mermaid diagram
        result.mermaid = _generate_mermaid_c4(result)
        
        # Generate PlantUML diagram
        result.plantuml = _generate_plantuml_c4(result)
        
        # Save outputs
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "architecture.json").write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )
            (output_dir / "architecture.mmd").write_text(result.mermaid, encoding="utf-8")
            (output_dir / "architecture.puml").write_text(result.plantuml, encoding="utf-8")
            logger.info(f"  Saved: architecture.json, architecture.mmd, architecture.puml")
        
        return result
        
    except Exception as e:
        logger.error(f"  Architecture generation failed: {e}")
        return None


def _generate_mermaid_c4(diagram: ArchitectureDiagram) -> str:
    """Generate Mermaid C4 diagram from structured data."""
    lines = [
        "```mermaid",
        "C4Context",
        f"title {diagram.title}",
        "",
    ]
    
    # Define elements
    for comp in diagram.components:
        shape = _get_mermaid_shape(comp.type)
        lines.append(f'  {shape}("{comp.name}", "{comp.description}", "{comp.technology or ""}")')
    
    lines.append("")
    
    # Define relationships
    for comp in diagram.components:
        for rel in comp.relationships:
            lines.append(f'  Rel({comp.name}, "{rel["target"]}", "{rel["description"]}", "{rel.get("technology", "")}")')
    
    lines.append("```")
    return "\n".join(lines)


def _generate_plantuml_c4(diagram: ArchitectureDiagram) -> str:
    """Generate PlantUML C4 diagram from structured data."""
    lines = [
        "@startuml",
        "!include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Container.puml",
        "",
        f'title {diagram.title}',
        "",
    ]
    
    # Define elements
    for comp in diagram.components:
        stereotype = _get_plantuml_stereotype(comp.type)
        alias = comp.name.replace(" ", "_").replace("-", "_")
        lines.append(f'{stereotype}({alias}, "{comp.name}", "{comp.technology or ""}", "{comp.description}")')
    
    lines.append("")
    
    # Define relationships
    for comp in diagram.components:
        for rel in comp.relationships:
            source_alias = comp.name.replace(" ", "_").replace("-", "_")
            target_alias = rel["target"].replace(" ", "_").replace("-", "_")
            lines.append(f'Rel({source_alias}, {target_alias}, "{rel["description"]}", "{rel.get("technology", "")}")')
    
    lines.append("@enduml")
    return "\n".join(lines)


def _get_mermaid_shape(comp_type: str) -> str:
    """Map C4 type to Mermaid shape."""
    shapes = {
        "person": "Person",
        "software_system": "System",
        "container": "Container",
        "component": "Component",
        "database": "Database",
        "queue": "Queue",
        "external_system": "System_Ext",
    }
    return shapes.get(comp_type, "Container")


def _get_plantuml_stereotype(comp_type: str) -> str:
    """Map C4 type to PlantUML stereotype."""
    stereotypes = {
        "person": "Person",
        "software_system": "System",
        "container": "Container",
        "component": "Component",
        "database": "Database",
        "queue": "Queue",
        "external_system": "System_Ext",
    }
    return stereotypes.get(comp_type, "Container")