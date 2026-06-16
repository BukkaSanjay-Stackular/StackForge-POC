"""
Stitch MCP Integration.
Automates screen generation from design artifacts using Google's Stitch MCP API.
"""

import json
import os
import requests
from pathlib import Path
from typing import Optional
from loguru import logger

from pipeline.utils.config import get_config
from pipeline.models.schemas import UIComponentInventory, UserJourney


class StitchMCPClient:
    """Client for Google Stitch MCP API for automated screen generation."""
    
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://stitch.googleapis.com/mcp"):
        self.api_key = api_key or os.getenv("STITCH_API_KEY", "")
        self.base_url = base_url
        self.request_id = 1
        
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            self.headers["X-Goog-Api-Key"] = self.api_key
    
    def _call(self, method: str, params: dict = None) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {},
        }
        self.request_id += 1
        
        try:
            response = requests.post(
                self.base_url,
                headers=self.headers,
                json=payload,
                timeout=300,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Stitch API call failed: {e}")
            return {"error": str(e)}
    
    def list_tools(self) -> dict:
        return self._call("tools/list")
    
    def create_project(self, title: str = "Generated Design") -> dict:
        return self._call("tools/call", {
            "name": "create_project",
            "arguments": {"title": title},
        })
    
    def generate_screen(self, project_id: str, prompt: str, model_id: str = "GEMINI_3_FLASH") -> dict:
        return self._call("tools/call", {
            "name": "generate_screen_from_text",
            "arguments": {
                "projectId": project_id,
                "prompt": prompt,
                "modelId": model_id,
            },
        })
    
    def edit_screens(self, project_id: str, screen_ids: list[str], prompt: str) -> dict:
        return self._call("tools/call", {
            "name": "edit_screens",
            "arguments": {
                "projectId": project_id,
                "selectedScreenIds": screen_ids,
                "prompt": prompt,
            },
        })


def build_screen_prompts(
    ui_components: UIComponentInventory,
    user_journeys: list[UserJourney],
) -> list[dict]:
    """
    Build screen generation prompts from UI components and journeys.
    Returns a list of {screen_id, prompt} dicts.
    """
    screens = []
    
    for component in ui_components.components:
        if component.type != "screen":
            continue
        
        # Find related journey steps
        related_journey_steps = []
        for journey in user_journeys:
            for step in journey.steps:
                if step.screen and step.screen.lower() in component.name.lower():
                    related_journey_steps.append({
                        "journey": journey.name,
                        "step": step.step,
                        "action": step.action,
                    })
        
        # Build structured prompt
        states_str = ", ".join(component.states) if component.states else "default"
        props_str = "; ".join(f"{p.get('name')}: {p.get('type')}" for p in component.props) if component.props else "none"
        
        prompt = f"""Generate a UI screen for: {component.name}
Description: {component.description}
States: {states_str}
Props: {props_str}
"""
        if related_journey_steps:
            prompt += "\nUser interactions:"
            for js in related_journey_steps:
                prompt += f"\n- {js['action']} (in {js['journey']})"
        
        screens.append({
            "screen_id": component.id,
            "name": component.name,
            "prompt": prompt,
        })
    
    return screens


def generate_screens_from_design(
    ui_components: UIComponentInventory | None = None,
    user_journeys: list[UserJourney] | None = None,
    project_name: str = "MediBook - Generated Design",
    api_key: Optional[str] = None,
    model_id: str = "GEMINI_3_FLASH",
    output_dir: Path | None = None,
) -> dict:
    """
    Automatically generate screens using Stitch MCP from design artifacts.
    
    Args:
        ui_components: UI component inventory (optional - loads from file if None)
        user_journeys: User journeys (optional - loads from file if None)
        project_name: Name for the Stitch project
        api_key: Stitch API key (defaults to env var STITCH_API_KEY)
        model_id: Model ID for generation
        output_dir: Output directory
        
    Returns:
        Dict with project_id and generated screens
    """
    config = get_config()
    out_dir = output_dir or Path(config.paths.design_artifacts)
    
    if not config.design_artifacts.stitch_mcp.get("enabled", False):
        logger.info("  Stitch MCP integration disabled in config")
        return {"skipped": True}
    
    stitch_key = api_key or config.design_artifacts.stitch_mcp.get("api_key", "") or os.getenv("STITCH_API_KEY", "")
    if not stitch_key:
        logger.warning("  No Stitch API key found. Set STITCH_API_KEY env var or configure in config.yaml")
        return {"error": "No API key"}
    
    client = StitchMCPClient(api_key=stitch_key)
    
    # Load UI components if not provided
    if ui_components is None:
        ui_path = out_dir / "ui_components.json"
        if ui_path.exists():
            ui_data = json.loads(ui_path.read_text(encoding="utf-8"))
            ui_components = UIComponentInventory(**ui_data)
            logger.info(f"  Loaded {len(ui_components.components)} UI components")
    
    # Load user journeys if not provided
    if user_journeys is None:
        journeys_path = out_dir / "user_journeys.json"
        if journeys_path.exists():
            journeys_data = json.loads(journeys_path.read_text(encoding="utf-8"))
            user_journeys = [UserJourney(**j) for j in journeys_data]
            logger.info(f"  Loaded {len(user_journeys)} user journeys")
    
    if not ui_components:
        logger.error("  No UI components available for screen generation")
        return {"error": "No UI components"}
    
    logger.info(f"\n{'='*55}")
    logger.info(f"  GENERATING SCREENS VIA STITCH MCP")
    logger.info(f"{'='*55}")
    
    # List available tools
    tools = client.list_tools()
    if "error" in tools:
        logger.error(f"  Stitch MCP not available: {tools['error']}")
        return tools
    logger.info(f"  Stitch MCP connected, tools available")
    
    # Create project
    project = client.create_project(title=project_name)
    if "error" in project:
        logger.error(f"  Project creation failed: {project['error']}")
        return project
    
    project_id = None
    if isinstance(project, dict) and "result" in project:
        project_id = project["result"].get("projectId") or project.get("projectId")
    
    if not project_id:
        logger.warning("  Could not extract projectId from response, using manual input fallback")
        logger.info(f"  Response: {json.dumps(project, indent=2)[:500]}")
        return project
    
    logger.info(f"  Created project: {project_name} (ID: {project_id})")
    
    # Build screen prompts
    screen_prompts = build_screen_prompts(ui_components, user_journeys or [])
    logger.info(f"  Generating {len(screen_prompts)} screens...")
    
    generated_screens = []
    for i, sp in enumerate(screen_prompts, 1):
        logger.info(f"    Screen {i}/{len(screen_prompts)}: {sp['name']}")
        result = client.generate_screen(project_id, sp["prompt"], model_id)
        generated_screens.append({
            "screen_id": sp["screen_id"],
            "name": sp["name"],
            "result": result,
        })
    
    # Save results
    (out_dir / "stitch_generated_screens.json").write_text(
        json.dumps(generated_screens, indent=2, default=str),
        encoding="utf-8",
    )
    
    logger.info(f"  Generated {len(generated_screens)} screens")
    logger.info(f"  Project ID: {project_id}")
    logger.info(f"  Saved: stitch_generated_screens.json")
    
    return {
        "project_id": project_id,
        "project_name": project_name,
        "screens_generated": len(generated_screens),
        "screens": generated_screens,
    }