"""
Design Artifact Generator: OpenAPI 3.1 Specification.
Generates complete OpenAPI spec from requirements + technical docs.
"""

import json
from pathlib import Path
from loguru import logger

from pipeline.utils.config import get_config
from pipeline.utils.llm_client import create_client, OpenCodeClient
from pipeline.models.schemas import OpenAPISpec, APIEndpoint, DesignArtifacts


OPENAPI_PROMPT = """You are a senior API architect creating an OpenAPI 3.1 specification.

Based on the project documentation below, generate a comprehensive OpenAPI spec for the MediBook platform.

PROJECT DOCUMENTATION:
{context}

Return ONLY a valid JSON object matching the OpenAPI 3.1 schema. Include:

1. **info**: title, version, description, contact, license
2. **servers**: dev, staging, production URLs
3. **paths**: All endpoints organized by tags
4. **components**:
   - schemas: All request/response models (Patient, Appointment, Doctor, Prescription, Invoice, etc.)
   - securitySchemes: BearerAuth (JWT), ApiKeyAuth (for integrations)
   - parameters: Common parameters (pagination, filters)
   - responses: Standard error responses
5. **security**: Global security requirement
6. **tags**: Organized by domain (Appointments, Patients, Doctors, Admin, Billing, Notifications, Integrations)

**Required Endpoints** (derive from requirements):
- Patient: register, login, profile, appointments, prescriptions, reports, invoices, payments
- Doctor: dashboard, schedule, patients, prescriptions, clinical notes, lab requests
- Admin: doctor management, clinic config, reports, billing, users, branches
- Integrations: Medi-Plus sync, Tally sync, Razorpay webhooks, WhatsApp templates
- Notifications: preferences, history, templates

**Schema Design Rules**:
- Use semantic naming: PascalCase for schemas, camelCase for properties
- All IDs: string (UUID) format
- Dates: date-time (ISO 8601)
- Enums for status fields
- Required fields marked
- Examples for complex objects
- Reusable components via $ref

**Security**:
- JWT Bearer token for user endpoints
- API Key for integration endpoints
- Role-based access (patient, doctor, admin, receptionist)"""


def generate_openapi_spec(
    context: str,
    client: OpenCodeClient,
    output_dir: Path | None = None,
) -> OpenAPISpec:
    """Generate OpenAPI 3.1 specification from project context."""
    config = get_config()
    
    if not config.design_artifacts.generate.get("openapi_spec", True):
        logger.info("  OpenAPI spec generation disabled in config")
        return None
    
    logger.info("\n  Generating OpenAPI specification...")
    
    prompt = OPENAPI_PROMPT.format(context=context)
    
    try:
        result = client.call_structured(
            prompt=prompt,
            response_model=OpenAPISpec,
            label="OpenAPI spec",
        )
        
        # Validate required fields
        if not result.paths:
            logger.warning("  No paths generated in OpenAPI spec")
        
        # Save outputs
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "openapi.json").write_text(
                result.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
            )
            # Also save as YAML for readability
            import yaml
            (output_dir / "openapi.yaml").write_text(
                yaml.dump(json.loads(result.model_dump_json(exclude_none=True)), sort_keys=False),
                encoding="utf-8"
            )
            logger.info(f"  Saved: openapi.json, openapi.yaml")
        
        return result
        
    except Exception as e:
        logger.error(f"  OpenAPI generation failed: {e}")
        return None


def validate_openapi_spec(spec_path: Path) -> list[str]:
    """Validate OpenAPI spec using spectral (if available)."""
    errors = []
    try:
        import subprocess
        result = subprocess.run(
            ["spectral", "lint", str(spec_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            errors.append(result.stdout)
    except FileNotFoundError:
        errors.append("spectral not installed - skipping validation")
    except Exception as e:
        errors.append(f"Validation error: {e}")
    return errors