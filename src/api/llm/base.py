"""
ECHO OS Barebone: LLM Provider Abstract Base Class
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from .types import LLMMessage, LLMResponse, LLMConfig


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""

    @abstractmethod
    def generate(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """Generate a response from the LLM.

        Args:
            messages: List of conversation messages
            config: Optional generation configuration

        Returns:
            LLMResponse with the generated content
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the provider name for logging"""
        pass
