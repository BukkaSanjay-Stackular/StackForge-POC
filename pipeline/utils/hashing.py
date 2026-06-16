"""
Content hashing and change detection for incremental processing.
"""

import hashlib
import json
from pathlib import Path
from typing import Any
from dataclasses import dataclass, asdict


@dataclass
class FileHash:
    """Hash record for a single file."""
    path: str
    hash: str
    size: int
    mtime: float


class ContentHasher:
    """Manages content hashes for incremental processing."""
    
    def __init__(self, hash_file: Path, algorithm: str = "sha256"):
        self.hash_file = hash_file
        self.algorithm = algorithm
        self._hashes: dict[str, FileHash] = {}
        self._load()
    
    def _load(self):
        """Load existing hashes from file."""
        if self.hash_file.exists():
            try:
                with open(self.hash_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._hashes = {
                    k: FileHash(**v) for k, v in data.items()
                }
            except (json.JSONDecodeError, KeyError, TypeError):
                self._hashes = {}
    
    def save(self):
        """Save hashes to file."""
        self.hash_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.hash_file, "w", encoding="utf-8") as f:
            json.dump(
                {k: asdict(v) for k, v in self._hashes.items()},
                f,
                indent=2,
            )
    
    def compute_hash(self, content: str | bytes) -> str:
        """Compute hash of content."""
        if isinstance(content, str):
            content = content.encode("utf-8")
        hasher = hashlib.new(self.algorithm)
        hasher.update(content)
        return hasher.hexdigest()
    
    def compute_file_hash(self, file_path: Path) -> FileHash:
        """Compute hash for a file."""
        stat = file_path.stat()
        content = file_path.read_bytes()
        return FileHash(
            path=str(file_path),
            hash=self.compute_hash(content),
            size=stat.st_size,
            mtime=stat.st_mtime,
        )
    
    def has_changed(self, file_path: Path) -> bool:
        """Check if file has changed since last hash."""
        current = self.compute_file_hash(file_path)
        stored = self._hashes.get(str(file_path))
        
        if not stored:
            return True
        
        return stored.hash != current.hash
    
    def update(self, file_path: Path):
        """Update hash for a file."""
        self._hashes[str(file_path)] = self.compute_file_hash(file_path)
    
    def remove(self, file_path: Path):
        """Remove hash for a deleted file."""
        self._hashes.pop(str(file_path), None)
    
    def get_changed_files(self, file_paths: list[Path]) -> list[Path]:
        """Get list of files that have changed."""
        return [f for f in file_paths if self.has_changed(f)]
    
    def get_all_hashes(self) -> dict[str, FileHash]:
        """Get all stored hashes."""
        return self._hashes.copy()


def compute_content_hash(content: str, algorithm: str = "sha256") -> str:
    """Compute hash of string content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.new(algorithm, content).hexdigest()