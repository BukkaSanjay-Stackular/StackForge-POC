"""
Design Artifact Generator: UI Component Inventory + User Journeys.
"""

import json
from pathlib import Path
from loguru import logger

from pipeline.utils.config import get_config
from pipeline.utils.llm_client import OpenCodeClient
from pipeline.models.schemas import UIComponentInventory, UIComponent, UserJourney, UserJourneyStep

UI_COMPONENTS_PROMPT = """You are a senior UI/UX architect creating a comprehensive UI component inventory.

Based on the project documentation below, generate a complete inventory of screens and components.

PROJECT DOCUMENTATION:
{context}

Return ONLY a valid JSON object with this structure:
{{
  "components": [
    {{
      "id": "scr-patient-booking",
      "name": "Appointment Booking Screen",
      "type": "screen",
      "description": "Main screen for patients to search and book appointments",
      "props": [
        {{"name": "selectedDoctor", "type": "DoctorId | null", "description": "Pre-selected doctor"}},
        {{"name": "selectedClinic", "type": "ClinicId | null", "description": "Pre-selected clinic"}}
      ],
      "states": ["loading", "empty_no_slots", "calendar_view", "list_view", "confirming", "confirmed"],
      "interactions": [
        {{"event": "onSlotSelected", "action": "navigate to confirmation", "target": "scr-confirmation"}}
      ],
      "parent_id": null,
      "children_ids": ["comp-doctor-card", "comp-time-slot-grid", "comp-date-picker"],
      "user_story_ids": ["APT-001", "APT-002"]
    }}
  ],
  "screens": [
    {{
      "id": "scr-patient-booking",
      "name": "Appointment Booking Screen",
      "type": "screen",
      "description": "Main screen for patients to search and book appointments",
      "props": [],
      "states": [],
      "interactions": [],
      "parent_id": null,
      "children_ids": [],
      "user_story_ids": ["APT-001", "APT-002"],
      "design_references": ["Section 4.1"]
    }}
  ],
  "design_system": {{
    "colors": {{
      "primary": "#1A73E8",
      "secondary": "#34A853",
      "danger": "#EA4335",
      "warning": "#FBBC04",
      "background": "#FFFFFF",
      "surface": "#F8F9FA",
      "text_primary": "#202124",
      "text_secondary": "#5F6368"
    }},
    "typography": {{
      "font_family": "Inter, system-ui, sans-serif",
      "headings": {{"h1": "32px/40px", "h2": "24px/32px", "h3": "20px/28px"}},
      "body": {{"default": "16px/24px", "small": "14px/20px"}}
    }},
    "spacing": {{"xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32}},
    "border_radius": {{"sm": 4, "md": 8, "lg": 12, "xl": 16, "full": 9999}},
    "shadows": ["none", "sm", "md", "lg", "xl"]
  }}
}}

**Required Screens** (derive from requirements):
- Patient screens: Splash, Login(OTP), Register, Home, Booking, Appointments, Records, Prescriptions, Lab Reports, Invoices, Payments, Profile, Settings, Family Members
- Doctor screens: Dashboard, TodaySchedule, PatientHistory, Prescription, ClinicalNotes, LabRequests
- Admin screens: Dashboard, DoctorManagement, BranchManagement, Reports, Billing, UserManagement
- Shared: Notifications, Search, Camera/Scanner

**Rules**:
- Every requirement must map to at least one screen
- Include loading, error, empty, and edge case states
- Reference specific user story IDs
- Design system with colors, typography, spacing, shadows"""


USER_JOURNEYS_PROMPT = """You are a senior UX designer creating detailed user journey maps.

Based on the project documentation below, generate user journeys for key actors.

PROJECT DOCUMENTATION:
{context}

Return ONLY a JSON array of user journeys:

[
  {{
    "id": "UJ-001",
    "name": "Patient Books Appointment",
    "actor": "Patient",
    "goal": "Book a doctor appointment at their preferred clinic",
    "steps": [
      {{
        "step": 1,
        "actor": "Patient",
        "action": "Opens MediBook app",
        "screen": "Home",
        "system_response": "Shows search bar, specialties, recent doctors",
        "decision_points": [],
        "pain_points": ["Slow loading on slow connection"]
      }},
      {{
        "step": 2,
        "actor": "Patient",
        "action": "Searches for doctor by specialty or name",
        "screen": "Book Appointment",
        "system_response": "Shows matching doctors with availability",
        "decision_points": ["Choose doctor", "Filter by clinic"]
      }}
    ]
  }}
]

**Required Journeys**:
1. Patient books appointment (primary flow)
2. Patient reschedules/cancels appointment
3. Patient views lab report
4. Doctor starts consultation → issues prescription
5. Doctor views patient history
6. Admin manages doctor schedule
7. Walk-in patient registered by receptionist
8. Payment via Razorpay (success + failure)
9. Patient receives notifications (reminder, prescription, report)
10. Admin generates monthly report"""


def generate_ui_components(
    context: str,
    client: OpenCodeClient,
    output_dir: Path | None = None,
) -> UIComponentInventory:
    """Generate UI component inventory from project context."""
    config = get_config()

    if not config.design_artifacts.generate.get("ui_components", True):
        logger.info("  UI component generation disabled in config")
        return None

    logger.info("\n  Generating UI component inventory...")

    try:
        result = client.call_structured(
            prompt=UI_COMPONENTS_PROMPT.format(context=context),
            response_model=UIComponentInventory,
            label="UI components",
        )

        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "ui_components.json").write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )
            logger.info(f"  Saved: ui_components.json ({len(result.components)} components)")

        return result

    except Exception as e:
        logger.error(f"  UI component generation failed: {e}")
        return None


def generate_user_journeys(
    context: str,
    client: OpenCodeClient,
    output_dir: Path | None = None,
) -> list[UserJourney]:
    """Generate user journey maps from project context."""
    config = get_config()

    if not config.design_artifacts.generate.get("user_journeys", True):
        logger.info("  User journey generation disabled in config")
        return []

    logger.info("\n  Generating user journeys...")

    try:
        result = client.call_structured(
            prompt=USER_JOURNEYS_PROMPT.format(context=context),
            response_model=list[UserJourney],
            label="User journeys",
        )
        
        # Validate raw list into UserJourney models
        if isinstance(result, list):
            result = [UserJourney(**item) if isinstance(item, dict) else item for item in result]
        
        # Generate Mermaid diagrams for each journey
        for journey in result:
            journey.mermaid = _generate_journey_mermaid(journey)

        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "user_journeys.json").write_text(
                json.dumps([j.model_dump() for j in result], indent=2, default=str),
                encoding="utf-8",
            )

            # Save combined Mermaid
            mermaid_lines = []
            for j in result:
                mermaid_lines.append(j.mermaid or "")
            (output_dir / "user_journeys.mmd").write_text(
                "\n\n".join(mermaid_lines), encoding="utf-8"
            )

            logger.info(f"  Saved: user_journeys.json ({len(result)} journeys)")

        return result

    except Exception as e:
        logger.error(f"  User journey generation failed: {e}")
        return []


def _generate_journey_mermaid(journey: UserJourney) -> str:
    """Generate Mermaid flowchart for a user journey."""
    import json
    lines = [
        "```mermaid",
        "graph TD",
        f'    title[{journey.name}]',
        f'    actor[{journey.actor}]',
    ]

    for step in journey.steps:
        node_id = f"S{step.step}"
        label = f"{step.step}. {step.action}"
        if step.screen:
            label += f" [{step.screen}]"
        lines.append(f'    {node_id}["{label}"]')

    for i in range(len(journey.steps) - 1):
        lines.append(f"    S{i+1} --> S{i+2}")

    lines.append("```")
    return "\n".join(lines)