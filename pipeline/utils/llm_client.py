"""
Unified LLM Client with structured output support.
Uses OpenCode CLI with retry logic, JSON parsing, and Pydantic validation.
"""

import json
import re
import subprocess
import tiktoken
from pathlib import Path
from typing import Optional, Type, TypeVar, Any
from dataclasses import dataclass
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
    before_sleep_log,
)
from loguru import logger

from pipeline.models.schemas import TokenUsage

T = TypeVar("T")


@dataclass
class LLMResponse:
    content: str
    usage: TokenUsage
    raw_output: str = ""
    parsed: Any = None


class OpenCodeClient:
    """OpenCode CLI wrapper with JSON parsing, Pydantic validation, and token tracking."""
    
    def __init__(
        self,
        model: str = "opencode/deepseek-v4-flash-free",
        timeout: int = 300,
        max_retries: int = 3,
        base_delay: float = 2.0,
        max_delay: float = 60.0,
    ):
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        
        self.encoder = tiktoken.get_encoding("cl100k_base")
        self.total_usage = TokenUsage()
        self.call_count = 0
    
    def _count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self.encoder.encode(text))
    
    def _estimate_thinking_tokens(self, prompt: str, response: str) -> int:
        return 0
    
    def _run_opencode(self, prompt: str) -> tuple[str, str]:
        """Execute opencode CLI and return (stdout, stderr)."""
        cmd = ["powershell", "-NoProfile", "-Command", f"$input | opencode run -m {self.model}"]
        
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            encoding="utf-8",
        )
        
        return result.stdout.strip(), result.stderr.strip()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=60),
        retry=retry_if_exception_type((subprocess.TimeoutExpired, ConnectionError)),
        before_sleep=before_sleep_log(logger, "WARNING"),
    )
    def call(self, prompt: str, system_prompt: str = "", label: str = "") -> LLMResponse:
        """Call LLM with raw text response."""
        self.call_count += 1
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        
        input_tokens = self._count_tokens(full_prompt)
        
        if label:
            logger.info(f"  -> {label}...")
        
        try:
            raw_output, stderr = self._run_opencode(full_prompt)
            
            if stderr and "error" in stderr.lower():
                logger.error(f"OpenCode stderr: {stderr[:200]}")
            
            output_tokens = self._count_tokens(raw_output)
            thinking_tokens = self._estimate_thinking_tokens(full_prompt, raw_output)
            estimated_total = input_tokens + output_tokens
            
            usage = TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                thinking_tokens=thinking_tokens if thinking_tokens > 0 else 0,
                total_tokens=estimated_total,
            )
            
            self.total_usage = TokenUsage(
                input_tokens=self.total_usage.input_tokens + usage.input_tokens,
                output_tokens=self.total_usage.output_tokens + usage.output_tokens,
                thinking_tokens=self.total_usage.thinking_tokens + usage.thinking_tokens,
                total_tokens=self.total_usage.total_tokens + usage.total_tokens,
            )
            
            if label:
                logger.success(f"  -> {label} done [{usage}]")
            
            return LLMResponse(
                content=raw_output,
                usage=usage,
                raw_output=raw_output,
            )
            
        except subprocess.TimeoutExpired:
            logger.error(f"OpenCode timed out after {self.timeout}s")
            raise
        except FileNotFoundError:
            logger.error("'opencode' command not found. Install OpenCode CLI.")
            raise
        except Exception as e:
            logger.error(f"OpenCode error: {e}")
            raise
    
    def call_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: str = "",
        label: str = "",
    ) -> T:
        """
        Call LLM, parse JSON, and validate into a Pydantic model.
        For list responses (e.g. list[UserJourney]), use call_json and validate separately.
        """
        response = self.call(prompt, system_prompt, label)
        parsed = self._parse_json(response.content)
        
        if isinstance(parsed, dict):
            try:
                return response_model(**parsed)
            except Exception as e:
                logger.error(f"  {label}: validation failed - {e}")
                return response_model()
        elif isinstance(parsed, list):
            if len(parsed) == 1 and isinstance(parsed[0], dict):
                try:
                    return response_model(**parsed[0])
                except Exception:
                    pass
            return parsed  # Return raw list; caller validates each item
        
        logger.error(f"  Could not parse structured response for {label}")
        return response_model()
    
    def call_json(self, prompt: str, system_prompt: str = "", label: str = "") -> dict | list:
        """Call LLM and parse JSON response."""
        response = self.call(prompt, system_prompt, label)
        return self._parse_json(response.content)
    
    def _parse_json(self, text: str) -> dict | list:
        if not text:
            return {}
        
        text = text.strip()
        text = re.sub(r"```(?:json)?\s*", "", text).strip()
        
        # Try direct parsing first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Find JSON object/array by tracking brace depth
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start = text.find(start_char)
            if start == -1:
                continue
            depth = 0
            for end in range(start, len(text)):
                if text[end] == start_char:
                    depth += 1
                elif text[end] == end_char:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:end+1])
                        except json.JSONDecodeError:
                            break
        return {}
    
    def print_summary(self):
        logger.info(f"\n{'='*50}")
        logger.info(f"  TOKEN USAGE SUMMARY")
        logger.info(f"  Calls: {self.call_count}")
        logger.info(f"  Total: {self.total_usage}")
        logger.info(f"{'='*50}\n")


def create_client(
    model: str = "opencode/deepseek-v4-flash-free",
    timeout: int = 300,
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
) -> OpenCodeClient:
    return OpenCodeClient(
        model=model,
        timeout=timeout,
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
    )