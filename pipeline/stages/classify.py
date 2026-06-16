"""
Stage 2: Classify markdown chunks into SDLC topics using LLM.
Uses structured output via Instructor for reliable classification.
"""

import re
from pathlib import Path
from loguru import logger

from pipeline.utils.config import get_config
from pipeline.utils.llm_client import create_client, OpenCodeClient
from pipeline.models.schemas import (
    SDLCTopic,
    ClassificationResult,
    ChunkClassification,
)


def build_classification_prompt(config) -> str:
    """Build the classification prompt from config topic descriptions."""
    topic_lines = []
    for topic in config.sdlc_topics:
        desc = config.topic_descriptions.get(topic, "")
        topic_lines.append(f"{topic.upper()}:\n{desc}")
    
    topics_text = "\n\n".join(topic_lines)
    
    return f"""You are an SDLC document classifier. Your job is to read a document chunk and assign it to the correct topic buckets.

Here are the 8 topic buckets with detailed descriptions:

{topics_text}

CLASSIFICATION RULES:
- Return 1 to 3 topics that BEST match the content — do not over-assign
- Only assign a topic if the chunk has MEANINGFUL content for it (not just a passing mention)
- If a chunk contains a payment schedule table → budget
- If a chunk contains requirement IDs like APT-001 → requirements
- If a chunk contains phase dates and durations → timeline
- If a chunk mentions Razorpay, Tally, Medi-Plus, WhatsApp API → integrations
- If a chunk contains tech stack, database, security details → technical
- If a chunk contains UI/UX, wireframes, mockups, user flows → design
- If nothing clearly matches any topic → return empty list

Valid topic names: {", ".join(config.sdlc_topics)}

Document chunk to classify:
---
{{chunk}}
---

Return only the JSON object with a "topics" array, e.g.:
{{"topics": ["requirements", "design"]}}
or
{{"topics": []}}
"""


def chunk_markdown(text: str, config) -> list[str]:
    """
    Smart chunker that splits on headings first, then paragraphs.
    Respects chunk_size_words limit.
    """
    chunk_size = config.chunking.chunk_size_words
    min_chunk = config.chunking.min_chunk_words
    
    # Split on H1 and H2 headings
    heading_pattern = re.compile(r'(?=^#{1,2}\s)', re.MULTILINE)
    major_sections = heading_pattern.split(text)
    major_sections = [s.strip() for s in major_sections if s.strip()]
    
    if not major_sections:
        major_sections = [text]
    
    all_sections = []
    for section in major_sections:
        word_count = len(section.split())
        if word_count <= chunk_size:
            all_sections.append(section)
        else:
            # Split on H3+ headings
            sub_pattern = re.compile(r'(?=^#{3,6}\s)', re.MULTILINE)
            sub_sections = sub_pattern.split(section)
            sub_sections = [s.strip() for s in sub_sections if s.strip()]
            
            for sub in sub_sections:
                if len(sub.split()) <= chunk_size:
                    all_sections.append(sub)
                else:
                    # Split on paragraphs
                    paragraphs = [p.strip() for p in re.split(r'\n\n+', sub) if p.strip()]
                    current, current_wc = "", 0
                    for para in paragraphs:
                        para_wc = len(para.split())
                        if current_wc + para_wc > chunk_size and current:
                            all_sections.append(current.strip())
                            current, current_wc = para, para_wc
                        else:
                            current += "\n\n" + para
                            current_wc += para_wc
                    if current.strip():
                        all_sections.append(current.strip())
    
    # Merge tiny sections
    if config.chunking.merge_tiny_chunks:
        merged, i = [], 0
        while i < len(all_sections):
            section = all_sections[i]
            if len(section.split()) < min_chunk and i + 1 < len(all_sections):
                section = section + "\n\n" + all_sections[i + 1]
                i += 2
            else:
                i += 1
            merged.append(section.strip())
        return merged
    
    return all_sections


def classify_chunks(md_files: list[Path], client: OpenCodeClient) -> list[ChunkClassification]:
    """
    Classify all chunks from markdown files into SDLC topics.
    
    Returns:
        List of ChunkClassification with chunk text, topics, and source file
    """
    config = get_config()
    prompt_template = build_classification_prompt(config)
    
    all_classifications = []
    
    for md_file in md_files:
        logger.info(f"\n  [PROCESSING] {md_file.name}")
        
        text = md_file.read_text(encoding="utf-8")
        chunks = chunk_markdown(text, config)
        logger.info(f"    -> {len(chunks)} chunk(s)")
        
        for i, chunk in enumerate(chunks, 1):
            prompt = prompt_template.replace("{chunk}", chunk)
            
            try:
                result = client.call_structured(
                    prompt=prompt,
                    response_model=ClassificationResult,
                    label=f"Classifying chunk {i}/{len(chunks)}",
                )
                
                # Handle both object and bare list responses
                if isinstance(result, list):
                    result = ClassificationResult(topics=result)
                
                topics = result.topics
                
                if topics:
                    logger.info(f"    -> Chunk {i}/{len(chunks)}: -> {[t.value for t in topics]}")
                    all_classifications.append(ChunkClassification(
                        chunk_index=i,
                        chunk_text=chunk,
                        topics=topics,
                        source_file=md_file.name,
                    ))
                else:
                    logger.info(f"    -> Chunk {i}/{len(chunks)}: -> no match, skipped")
                    
            except Exception as e:
                logger.error(f"    -> Chunk {i}/{len(chunks)}: classification failed - {e}")
    
    return all_classifications