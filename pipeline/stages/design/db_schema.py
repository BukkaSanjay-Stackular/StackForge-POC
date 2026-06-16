"""
Design Artifact Generator: Database Schema (ERD + DDL).
Generates PostgreSQL schema from requirements + technical docs.
"""

import json
from pathlib import Path
from loguru import logger

from pipeline.utils.config import get_config
from pipeline.utils.llm_client import create_client, OpenCodeClient
from pipeline.models.schemas import DatabaseSchema, DatabaseTable, DesignArtifacts


DB_SCHEMA_PROMPT = """You are a senior database architect designing a PostgreSQL schema.

Based on the project documentation below, generate a comprehensive database schema for the MediBook platform.

PROJECT DOCUMENTATION:
{context}

Return ONLY a valid JSON object with this structure:
{{
  "dialect": "postgresql",
  "tables": [
    {{
      "name": "patients",
      "description": "Patient demographic and account information",
      "columns": [
        {{"name": "id", "type": "uuid", "nullable": false, "default": "gen_random_uuid()", "comment": "Primary key"}},
        {{"name": "phone", "type": "varchar(20)", "nullable": false, "unique": true, "comment": "Login identifier"}},
        {{"name": "email", "type": "varchar(255)", "nullable": true, "unique": true}},
        {{"name": "full_name", "type": "varchar(255)", "nullable": false}},
        {{"name": "date_of_birth", "type": "date", "nullable": true}},
        {{"name": "gender", "type": "varchar(20)", "nullable": true, "check": "gender IN ('male', 'female', 'other')"}},
        {{"name": "address", "type": "jsonb", "nullable": true, "comment": "Structured address"}},
        {{"name": "language", "type": "varchar(10)", "nullable": false, "default": "'en'", "check": "language IN ('en', 'te')"}},
        {{"name": "is_active", "type": "boolean", "nullable": false, "default": "true"}},
        {{"name": "created_at", "type": "timestamptz", "nullable": false, "default": "now()"}},
        {{"name": "updated_at", "type": "timestamptz", "nullable": false, "default": "now()"}}
      ],
      "primary_key": ["id"],
      "foreign_keys": [],
      "indexes": [
        {{"name": "idx_patients_phone", "columns": ["phone"], "unique": true}},
        {{"name": "idx_patients_email", "columns": ["email"], "unique": true}},
        {{"name": "idx_patients_name", "columns": ["full_name"]}}
      ],
      "constraints": [
        "CHECK (char_length(phone) >= 10)"
      ]
    }}
  ]
}}

**Required Tables** (derive from requirements):
- patients (demographics, auth, preferences, family members)
- doctors (profiles, specialties, schedules, availability)
- clinics/branches (locations, hours, settings)
- appointments (booking, status, queue, waitlist)
- prescriptions (medications, dosage, doctor, patient)
- clinical_notes (SOAP format, doctor, patient, appointment)
- lab_requests / lab_results (investigations, reports)
- invoices / payments / refunds (billing, Razorpay integration)
- notifications (SMS, WhatsApp, email, in-app, templates)
- mediplus_sync / tally_sync (integration logs, ETL tracking)
- users / roles / permissions (admin panel RBAC)
- audit_logs (compliance, HIPAA, DPDP)

**Design Rules**:
- Use UUID primary keys (gen_random_uuid())
- timestamptz for all timestamps with now() default
- Proper foreign keys with ON DELETE CASCADE/SET NULL
- Indexes on all FK columns + common query patterns
- JSONB for flexible data (addresses, notification payloads)
- Check constraints for enums
- Partitioning strategy for high-volume tables (audit_logs, notifications)
- Row-level security policies for multi-tenancy (branches)
- Soft deletes (deleted_at) for audit-critical tables
- Naming: snake_case, plural table names, singular column names"""


def generate_database_schema(
    context: str,
    client: OpenCodeClient,
    output_dir: Path | None = None,
) -> DatabaseSchema:
    """Generate PostgreSQL database schema from project context."""
    config = get_config()
    
    if not config.design_artifacts.generate.get("database_schema", True):
        logger.info("  Database schema generation disabled in config")
        return None
    
    logger.info("\n  Generating database schema...")
    
    prompt = DB_SCHEMA_PROMPT.format(context=context)
    
    try:
        result = client.call_structured(
            prompt=prompt,
            response_model=DatabaseSchema,
            label="Database schema",
        )
        
        # Generate Mermaid ERD
        result.mermaid_erd = _generate_mermaid_erd(result)
        
        # Generate SQL DDL
        sql_ddl = _generate_sql_ddl(result)
        
        # Save outputs
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "database_schema.json").write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )
            (output_dir / "schema.sql").write_text(sql_ddl, encoding="utf-8")
            (output_dir / "erd.mmd").write_text(result.mermaid_erd, encoding="utf-8")
            logger.info(f"  Saved: database_schema.json, schema.sql, erd.mmd")
        
        return result
        
    except Exception as e:
        logger.error(f"  Database schema generation failed: {e}")
        return None


def _generate_mermaid_erd(schema: DatabaseSchema) -> str:
    """Generate Mermaid ER diagram from schema."""
    lines = [
        "```mermaid",
        "erDiagram",
    ]
    
    for table in schema.tables:
        lines.append(f"    {table.name} {{")
        for col in table.columns:
            pk = "PK" if col["name"] in table.primary_key else ""
            fk = "FK" if any(col["name"] in fk.get("columns", []) for fk in table.foreign_keys) else ""
            nullable = "NULL" if col.get("nullable", True) else "NOT NULL"
            col_type = col["type"]
            lines.append(f"        {col_type} {col['name']} {pk} {fk} {nullable}")
        lines.append("    }")
    
    # Relationships
    for table in schema.tables:
        for fk in table.foreign_keys:
            ref_table = fk.get("references", {}).get("table", "")
            ref_cols = fk.get("references", {}).get("columns", [])
            local_cols = fk.get("columns", [])
            if ref_table and local_cols:
                lines.append(f"    {table.name} ||--o{{ {ref_table} : \"{', '.join(local_cols)}\"")
    
    lines.append("```")
    return "\n".join(lines)


def _generate_sql_ddl(schema: DatabaseSchema) -> str:
    """Generate PostgreSQL DDL from schema."""
    lines = [
        "-- MediBook Platform Database Schema",
        "-- Generated by SDLC Pipeline",
        f"-- Dialect: {schema.dialect}",
        "",
        "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";",
        "CREATE EXTENSION IF NOT EXISTS \"pgcrypto\";",
        "",
    ]
    
    for table in schema.tables:
        lines.append(f"-- Table: {table.name}")
        if table.description:
            lines.append(f"-- {table.description}")
        
        # Create table
        col_defs = []
        for col in table.columns:
            col_def = f"    {col['name']} {col['type']}"
            
            if not col.get("nullable", True):
                col_def += " NOT NULL"
            
            if "default" in col:
                col_def += f" DEFAULT {col['default']}"
            
            if "unique" in col and col["unique"]:
                col_def += " UNIQUE"
            
            if "check" in col:
                col_def += f" CHECK ({col['check']})"
            
            if "comment" in col:
                col_def += f" -- {col['comment']}"
            
            col_defs.append(col_def)
        
        # Primary key
        if table.primary_key:
            col_defs.append(f"    PRIMARY KEY ({', '.join(table.primary_key)})")
        
        lines.append(f"CREATE TABLE {table.name} (")
        lines.append(",\n".join(col_defs))
        lines.append(");")
        lines.append("")
        
        # Foreign keys
        for fk in table.foreign_keys:
            local = ", ".join(fk.get("columns", []))
            ref_table = fk.get("references", {}).get("table", "")
            ref_cols = ", ".join(fk.get("references", {}).get("columns", []))
            on_delete = fk.get("on_delete", "RESTRICT")
            on_update = fk.get("on_update", "CASCADE")
            lines.append(
                f"ALTER TABLE {table.name} ADD CONSTRAINT fk_{table.name}_{local} "
                f"FOREIGN KEY ({local}) REFERENCES {ref_table} ({ref_cols}) "
                f"ON DELETE {on_delete} ON UPDATE {on_update};"
            )
        
        # Indexes
        for idx in table.indexes:
            unique = "UNIQUE " if idx.get("unique", False) else ""
            cols = ", ".join(idx.get("columns", []))
            lines.append(f"CREATE {unique}INDEX {idx['name']} ON {table.name} ({cols});")
        
        # Constraints
        for constraint in table.constraints:
            lines.append(f"ALTER TABLE {table.name} ADD CONSTRAINT {constraint};")
        
        lines.append("")
    
    # Updated at trigger function
    lines.extend([
        "-- Updated at trigger",
        "CREATE OR REPLACE FUNCTION update_updated_at_column()",
        "RETURNS TRIGGER AS $$",
        "BEGIN",
        "    NEW.updated_at = now();",
        "    RETURN NEW;",
        "END;",
        "$$ language 'plpgsql';",
        "",
    ])
    
    # Apply trigger to tables with updated_at
    for table in schema.tables:
        has_updated_at = any(c["name"] == "updated_at" for c in table.columns)
        if has_updated_at:
            lines.append(
                f"CREATE TRIGGER update_{table.name}_updated_at "
                f"BEFORE UPDATE ON {table.name} "
                f"FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();"
            )
    
    return "\n".join(lines)


def validate_sql_ddl(sql_path: Path) -> list[str]:
    """Validate SQL DDL using sqlfluff."""
    errors = []
    try:
        import subprocess
        result = subprocess.run(
            ["sqlfluff", "lint", str(sql_path), "--dialect", "postgres"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            errors.append(result.stdout)
    except FileNotFoundError:
        errors.append("sqlfluff not installed - skipping validation")
    except Exception as e:
        errors.append(f"Validation error: {e}")
    return errors