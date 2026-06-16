"""
Configuration loader for the pipeline.
Loads config.yaml and provides typed access to all settings.
"""

import yaml
from pathlib import Path
from typing import Any
from pydantic import BaseModel
from functools import lru_cache


class PathsConfig(BaseModel):
    raw_docs: str = "raw_docs"
    markdown_docs: str = "markdown_docs"
    sub_docs: str = "sub_docs"
    user_stories: str = "user_stories"
    design_artifacts: str = "design_artifacts"
    processed_log: str = "processed_files.txt"
    content_hashes: str = ".content_hashes.json"


class LLMConfig(BaseModel):
    primary: dict
    fallback: dict
    classifier: dict
    designer: dict


class ChunkingConfig(BaseModel):
    chunk_size_words: int = 600
    min_chunk_words: int = 50
    merge_tiny_chunks: bool = True
    split_on_headings: bool = True
    heading_levels: list[int] = [1, 2]


class ClassificationConfig(BaseModel):
    max_topics_per_chunk: int = 3
    min_topics_per_chunk: int = 1
    require_meaningful_match: bool = True
    skip_empty_chunks: bool = True


class UserStoriesConfig(BaseModel):
    max_epics: int = 6
    min_epics: int = 4
    features_per_epic: list[int] = [2, 4]
    stories_per_feature: list[int] = [2, 3]
    max_context_words: int = 1200
    epic_context_words: int = 1500
    priority_values: list[str] = ["Must Have", "Should Have", "Could Have"]
    story_point_values: list[int] = [1, 2, 3, 5, 8]


class DesignArtifactsConfig(BaseModel):
    generate: dict
    formats: dict
    stitch_mcp: dict


class QualityGatesConfig(BaseModel):
    enabled: bool = True
    requirements_completeness: dict
    design_coverage: dict
    api_validation: dict
    sql_validation: dict
    cross_doc_consistency: dict


class IncrementalConfig(BaseModel):
    enabled: bool = True
    hash_algorithm: str = "sha256"
    reclassify_on_change: bool = True


class RetryConfig(BaseModel):
    max_attempts: int = 3
    base_delay: float = 2.0
    max_delay: float = 60.0
    exponential_base: int = 2
    jitter: bool = True


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "rich"
    token_usage_summary: bool = True


class Config(BaseModel):
    paths: PathsConfig
    llm: LLMConfig
    chunking: ChunkingConfig
    sdlc_topics: list[str]
    topic_descriptions: dict
    classification: ClassificationConfig
    user_stories: UserStoriesConfig
    design_artifacts: DesignArtifactsConfig
    quality_gates: QualityGatesConfig
    incremental: IncrementalConfig
    retry: RetryConfig
    logging: LoggingConfig


@lru_cache(maxsize=1)
def load_config(config_path: str = "config.yaml") -> Config:
    """Load and parse configuration from YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    return Config(**data)


def get_config() -> Config:
    """Get the global config instance."""
    return load_config()


def get_path(key: str) -> Path:
    """Get a path from config as Path object."""
    config = get_config()
    return Path(getattr(config.paths, key))