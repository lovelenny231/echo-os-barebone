"""
ECHO OS Barebone: LLM Type definitions
"""

from dataclasses import dataclass
from typing import Dict, Optional, Literal


@dataclass
class LLMMessage:
    """A single message in the conversation"""
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class LLMConfig:
    """Configuration for LLM generation"""
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 2048
    temperature: float = 0.7


@dataclass
class LLMResponse:
    """Response from an LLM provider"""
    content: str
    provider: str
    model: str
    usage: Optional[Dict[str, int]] = None
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
