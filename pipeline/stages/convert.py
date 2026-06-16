"""
Stage 1: Convert raw documents to Markdown.
Supports PDF, DOCX, PPTX, XLSX, CSV, TXT, HTML, XML, JSON, and more via MarkItDown.
"""

import shutil
from pathlib import Path
from markitdown import MarkItDown
from loguru import logger

from pipeline.utils.config import get_config, get_path
from pipeline.utils.hashing import ContentHasher


SUPPORTED_EXTENSIONS = [
    ".pdf", ".docx", ".doc",
    ".pptx", ".ppt",
    ".xlsx", ".xls", ".csv",
    ".txt", ".rtf",
    ".html", ".htm",
    ".xml", ".json",
    ".zip", ".epub",
    ".md",
]

def convert_to_markdown(hasher: ContentHasher | None = None) -> list[Path]:
    """
    Convert all new/changed files in raw_docs/ to markdown_docs/.
    
    Args:
        hasher: Optional ContentHasher for incremental processing
        
    Returns:
        List of newly converted/updated markdown file paths
    """
    config = get_config()
    
    raw_dir = get_path("raw_docs")
    md_dir = get_path("markdown_docs")
    md_dir.mkdir(parents=True, exist_ok=True)
    
    converter = MarkItDown()
    
    # Find all supported files
    all_files = [
        f for f in raw_dir.iterdir()
        if f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    
    if not all_files:
        logger.info("  No supported files found in raw_docs/")
        return []
    
    # Filter changed files if hasher provided
    if hasher and config.incremental.enabled:
        files_to_process = hasher.get_changed_files(all_files)
        skipped = len(all_files) - len(files_to_process)
        if skipped:
            logger.info(f"  Skipping {skipped} unchanged file(s)")
    else:
        files_to_process = all_files
    
    if not files_to_process:
        logger.info("  [OK] All files up to date -- nothing to convert")
        return []
    
    logger.info(f"\n{'='*55}")
    logger.info(f"  STAGE 1: Converting {len(files_to_process)} file(s) to Markdown")
    logger.info(f"{'='*55}")
    
    newly_converted = []
    
    for file in files_to_process:
        try:
            out_path = md_dir / (file.stem + ".md")
            
            if file.suffix.lower() == ".md":
                # Direct copy for markdown files
                shutil.copy2(file, out_path)
                logger.info(f"  [COPIED]    {file.name} -> markdown_docs/{out_path.name}")
            else:
                result = converter.convert(str(file))
                if not result.text_content or not result.text_content.strip():
                    logger.warning(f"  [SKIPPED] (empty output): {file.name}")
                    continue
                out_path.write_text(result.text_content, encoding="utf-8")
                logger.info(f"  [CONVERTED] {file.name} -> markdown_docs/{out_path.name}")
            
            newly_converted.append(out_path)
            
            # Update hash
            if hasher:
                hasher.update(file)
                
        except Exception as e:
            logger.error(f"  [FAILED] {file.name} - {e}")
    
    if hasher:
        hasher.save()
    
    logger.info(f"\n  Summary: {len(newly_converted)} file(s) ready for classification")
    return newly_converted


def convert_single_file(file_path: Path, output_dir: Path | None = None) -> Path | None:
    """Convert a single file to markdown. Useful for testing."""
    config = get_config()
    md_dir = output_dir or get_path("markdown_docs")
    md_dir.mkdir(parents=True, exist_ok=True)
    
    converter = MarkItDown()
    
    try:
        out_path = md_dir / (file_path.stem + ".md")
        
        if file_path.suffix.lower() == ".md":
            shutil.copy2(file_path, out_path)
        else:
            result = converter.convert(str(file_path))
            if not result.text_content or not result.text_content.strip():
                logger.warning(f"Empty output for {file_path.name}")
                return None
            out_path.write_text(result.text_content, encoding="utf-8")
        
        logger.info(f"Converted: {file_path.name} -> {out_path.name}")
        return out_path
        
    except Exception as e:
        logger.error(f"Failed to convert {file_path.name}: {e}")
        return None