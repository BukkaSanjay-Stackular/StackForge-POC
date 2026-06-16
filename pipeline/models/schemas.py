"""
Pydantic schemas for all pipeline artifacts.
Provides structured validation for LLM outputs and inter-stage data.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator
from dataclasses import dataclass
from enum import Enum


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            thinking_tokens=self.thinking_tokens + other.thinking_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )

    def __str__(self) -> str:
        return f"input={self.input_tokens:,} output={self.output_tokens:,} thinking={self.thinking_tokens:,} total={self.total_tokens:,}"


class SDLCTopic(str, Enum):
    REQUIREMENTS = "requirements"
    DESIGN = "design"
    TECHNICAL = "technical"
    TIMELINE = "timeline"
    BUDGET = "budget"
    TESTING = "testing"
    INTEGRATIONS = "integrations"
    TEAM_AND_PROCESS = "team_and_process"


class ClassificationResult(BaseModel):
    """LLM classification output for a single chunk."""
    topics: list[SDLCTopic] = Field(
        default_factory=list,
        min_length=0,
        max_length=3,
        description="1-3 topic labels that best match the chunk content"
    )
    
    @field_validator("topics", mode="before")
    @classmethod
    def validate_topics(cls, v):
        if isinstance(v, list):
            return [SDLCTopic(t) if isinstance(t, str) else t for t in v]
        return v


class ChunkClassification(BaseModel):
    """A chunk with its classification result."""
    chunk_index: int
    chunk_text: str
    topics: list[SDLCTopic]
    source_file: str


class SubDocContent(BaseModel):
    """Content for a single sub-document."""
    topic: SDLCTopic
    title: str
    content: str
    source_files: list[str] = Field(default_factory=list)


# USER STORY SCHEMAS 

class Priority(str, Enum):
    MUST_HAVE = "Must Have"
    SHOULD_HAVE = "Should Have"
    COULD_HAVE = "Could Have"


class StoryPoints(int, Enum):
    ONE = 1
    TWO = 2
    THREE = 3
    FIVE = 5
    EIGHT = 8


class AcceptanceCriterion(BaseModel):
    """Single acceptance criterion in Given/When/Then format."""
    given: str = Field(..., description="Precondition context")
    when: str = Field(..., description="Action taken")
    then: str = Field(..., description="Expected result")
    
    def to_gherkin(self) -> str:
        return f"Given {self.given}, when {self.when}, then {self.then}"


class UserStory(BaseModel):
    """Individual user story with full detail."""
    id: str = Field(..., pattern=r"^US\d{3}$")
    title: str = Field(..., min_length=5, max_length=100)
    story: str = Field(..., description="As a [user], I want to [action], so that [benefit].")
    acceptance_criteria: list[AcceptanceCriterion] = Field(
        ..., min_length=3, max_length=3, description="Exactly 3 criteria"
    )
    priority: Priority
    story_points: StoryPoints


class Feature(BaseModel):
    """Feature containing multiple user stories."""
    id: str = Field(..., pattern=r"^F\d{3}$")
    title: str = Field(..., min_length=5, max_length=100)
    description: str = Field(..., min_length=10)
    user_stories: list[UserStory] = Field(..., min_length=2, max_length=3)


class Epic(BaseModel):
    """Epic containing multiple features."""
    id: str = Field(..., pattern=r"^E\d{3}$")
    title: str = Field(..., min_length=5, max_length=100)
    description: str = Field(..., min_length=10)
    features: list[Feature] = Field(default_factory=list)


class UserStoriesOutput(BaseModel):
    """Complete user stories generation output."""
    project_name: str
    epics: list[Epic] = Field(..., min_length=4, max_length=6)
    
    @property
    def total_features(self) -> int:
        return sum(len(e.features) for e in self.epics)
    
    @property
    def total_stories(self) -> int:
        return sum(len(f.user_stories) for e in self.epics for f in e.features)
    
    @property
    def total_story_points(self) -> int:
        return sum(
            us.story_points.value 
            for e in self.epics 
            for f in e.features 
            for us in f.user_stories
        )

# DESIGN ARTIFACT SCHEMAS 

class ArchitectureComponent(BaseModel):
    """Component in system architecture (C4 model)."""
    name: str
    type: Literal["person", "software_system", "container", "component", "database", "queue", "external_system"]
    description: str
    technology: Optional[str] = None
    relationships: list[dict] = Field(default_factory=list)


class ArchitectureDiagram(BaseModel):
    """C4 architecture diagram specification."""
    title: str
    scope: Literal["context", "container", "component", "code"]
    components: list[ArchitectureComponent]
    mermaid: Optional[str] = None
    plantuml: Optional[str] = None


class APIEndpoint(BaseModel):
    """Single API endpoint specification."""
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
    path: str
    summary: str
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    parameters: list[dict] = Field(default_factory=list)
    request_body: Optional[dict] = None
    responses: dict = Field(default_factory=dict)
    security: list[dict] = Field(default_factory=list)


class OpenAPISpec(BaseModel):
    """OpenAPI 3.1 specification."""
    openapi: str = "3.1.0"
    info: dict
    servers: list[dict] = Field(default_factory=list)
    paths: dict = Field(default_factory=dict)
    components: dict = Field(default_factory=dict)
    security: list[dict] = Field(default_factory=list)
    tags: list[dict] = Field(default_factory=list)


class DatabaseTable(BaseModel):
    """Database table definition."""
    name: str
    description: Optional[str] = None
    columns: list[dict] = Field(default_factory=list)
    primary_key: list[str] = Field(default_factory=list)
    foreign_keys: list[dict] = Field(default_factory=list)
    indexes: list[dict] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class DatabaseSchema(BaseModel):
    """Complete database schema."""
    dialect: str = "postgresql"
    tables: list[DatabaseTable]
    mermaid_erd: Optional[str] = None


class UIComponent(BaseModel):
    """UI component specification."""
    id: str
    name: str
    type: Literal["screen", "component", "widget", "layout", "navigation"]
    description: str
    props: list[dict] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)
    interactions: list[dict] = Field(default_factory=list)
    parent_id: Optional[str] = None
    children_ids: list[str] = Field(default_factory=list)
    user_story_ids: list[str] = Field(default_factory=list)
    design_references: list[str] = Field(default_factory=list)


class UIComponentInventory(BaseModel):
    """Complete UI component inventory."""
    components: list[UIComponent]
    screens: list[UIComponent] = Field(default_factory=list)
    design_system: dict = Field(default_factory=dict)


class UserJourneyStep(BaseModel):
    """Single step in a user journey."""
    step: int
    actor: str
    action: str
    screen: Optional[str] = None
    system_response: Optional[str] = None
    decision_points: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)


class UserJourney(BaseModel):
    """Complete user journey map."""
    id: str
    name: str
    actor: str
    goal: str
    steps: list[UserJourneyStep]
    mermaid: Optional[str] = None


class ADR(BaseModel):
    """Architecture Decision Record."""
    id: str
    title: str
    status: Literal["proposed", "accepted", "deprecated", "superseded"]
    context: str
    decision: str
    consequences: dict = Field(default_factory=dict)  # positive, negative, neutral
    related_requirements: list[str] = Field(default_factory=list)


class DesignArtifacts(BaseModel):
    """All design artifacts generated for a project."""
    architecture: Optional[ArchitectureDiagram] = None
    openapi_spec: Optional[OpenAPISpec] = None
    database_schema: Optional[DatabaseSchema] = None
    ui_components: Optional[UIComponentInventory] = None
    user_journeys: list[UserJourney] = Field(default_factory=list)
    adrs: list[ADR] = Field(default_factory=list)


# TRACEABILITY SCHEMAS 

class TraceabilityLink(BaseModel):
    """Single traceability link between artifacts."""
    from_type: Literal["requirement", "design", "user_story", "test_case", "code"]
    from_id: str
    to_type: Literal["requirement", "design", "user_story", "test_case", "code"]
    to_id: str
    relationship: Literal["implements", "verifies", "derived_from", "depends_on", "relates_to"]


class TraceabilityMatrix(BaseModel):
    """Complete traceability matrix."""
    links: list[TraceabilityLink]
    
    def get_coverage(self, from_type: str, to_type: str) -> dict:
        """Calculate coverage from one artifact type to another."""
        from_items = set(l.from_id for l in self.links if l.from_type == from_type)
        covered = set()
        for link in self.links:
            if link.from_type == from_type and link.to_type == to_type:
                covered.add(link.from_id)
        return {
            "total": len(from_items),
            "covered": len(covered),
            "coverage_pct": len(covered) / len(from_items) * 100 if from_items else 0,
            "uncovered": list(from_items - covered)
        }


# QUALITY GATE SCHEMAS 

class QualityGateResult(BaseModel):
    """Result of a quality gate check."""
    gate_name: str
    passed: bool
    score: Optional[float] = None
    details: dict = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PipelineRunResult(BaseModel):
    """Complete pipeline execution result."""
    success: bool
    stages_completed: list[str]
    stages_failed: list[str]
    artifacts_generated: list[str]
    quality_gates: list[QualityGateResult]
    token_usage: dict = Field(default_factory=dict)
    duration_seconds: float
    errors: list[str] = Field(default_factory=list)