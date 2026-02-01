"""
ECHO OS Barebone: Claude Provider Implementation

Uses Anthropic's Claude model for chat generation.
"""

import logging
from typing import List, Optional

import anthropic

from .base import LLMProvider
from .types import LLMMessage, LLMResponse, LLMConfig


logger = logging.getLogger(__name__)


class ClaudeProvider(LLMProvider):
    """Claude provider implementation"""

    def __init__(self, api_key: str):
        """Initialize the Claude provider.

        Args:
            api_key: Anthropic API key
        """
        self.client = anthropic.Anthropic(api_key=api_key)

    def generate(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """Generate a response using Claude.

        Args:
            messages: List of conversation messages
            config: Optional generation configuration

        Returns:
            LLMResponse with the generated content
        """
        config = config or LLMConfig()

        # Separate system message from conversation messages
        system_msg = None
        user_messages = []

        for msg in messages:
            if msg.role == "system":
                system_msg = msg.content
            else:
                user_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })

        logger.info(f"CLAUDE_REQUEST: model={config.model}, "
                   f"system_len={len(system_msg) if system_msg else 0}, "
                   f"messages={len(user_messages)}")

        try:
            response = self.client.messages.create(
                model=config.model,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                system=system_msg if system_msg else "",
                messages=user_messages
            )

            content = response.content[0].text
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            }

            logger.info(f"CLAUDE_RESPONSE: tokens={usage}, "
                       f"content_len={len(content)}")

            return LLMResponse(
                content=content,
                provider="claude",
                model=config.model,
                usage=usage
            )

        except Exception as e:
            logger.error(f"CLAUDE_ERROR: {type(e).__name__}: {e}")
            raise

    def get_provider_name(self) -> str:
        return "claude"
