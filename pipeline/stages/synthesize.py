"""
Stage 3: Synthesize classified chunks into unified sub-docs.
Copies full original chunk text into topic-based sub-documents.
"""

from pathlib import Path
from collections import defaultdict
from loguru import logger

from pipeline.utils.config import get_config
from pipeline.models.schemas import ChunkClassification, SDLCTopic, SubDocContent


def synthesize_subdocs(
    classifications: list[ChunkClassification],
    output_dir: Path | None = None,
) -> list[SubDocContent]:
    """
    Copy FULL original chunk text into each matched topic sub-doc.
    LLM only decided the topics — Python writes the original text.
    """
    config = get_config()
    sub_docs_dir = output_dir or Path(config.paths.sub_docs)
    sub_docs_dir.mkdir(parents=True, exist_ok=True)
    
    # Group chunks by topic
    topic_chunks: dict[SDLCTopic, list[ChunkClassification]] = defaultdict(list)
    for cls in classifications:
        for topic in cls.topics:
            topic_chunks[topic].append(cls)
    
    if not topic_chunks:
        logger.warning("  No classifications to synthesize")
        return []
    
    logger.info(f"\n{'='*55}")
    logger.info(f"  STAGE 3: Synthesizing {len(topic_chunks)} sub-docs")
    logger.info(f"{'='*55}")
    
    subdoc_contents = []
    
    for topic, chunks in topic_chunks.items():
        out_file = sub_docs_dir / f"{topic.value}.md"
        
        # Build content: each chunk with source attribution
        content_parts = []
        source_files = set()
        
        for chunk in chunks:
            source_files.add(chunk.source_file)
            content_parts.append(
                f"\n\n---\n*Source: {chunk.source_file}*\n\n{chunk.chunk_text}"
            )
        
        full_content = "".join(content_parts)
        title = topic.value.replace("_", " ").title()
        
        if out_file.exists():
            existing = out_file.read_text(encoding="utf-8")
            # Avoid duplicate content
            if full_content.strip() not in existing:
                out_file.write_text(existing + full_content, encoding="utf-8")
                logger.info(f"  [APPENDED] sub_docs/{topic.value}.md ({len(chunks)} chunks)")
            else:
                logger.info(f"  [SKIPPED] sub_docs/{topic.value}.md (content already present)")
        else:
            out_file.write_text(f"# {title}{full_content}", encoding="utf-8")
            logger.info(f"  [CREATED] sub_docs/{topic.value}.md ({len(chunks)} chunks)")
        
        subdoc_contents.append(SubDocContent(
            topic=topic,
            title=title,
            content=full_content.strip(),
            source_files=list(source_files),
        ))
    
    return subdoc_contents


def read_subdocs(sub_docs_dir: Path | None = None) -> dict[str, str]:
    """Read all sub-docs into a dictionary."""
    config = get_config()
    sub_docs_dir = sub_docs_dir or Path(config.paths.sub_docs)
    
    subdocs = {}
    if sub_docs_dir.exists():
        for md_file in sub_docs_dir.glob("*.md"):
            subdocs[md_file.stem] = md_file.read_text(encoding="utf-8")
    
    return subdocs