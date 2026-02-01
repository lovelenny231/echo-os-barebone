"""
ECHO OS Barebone: OpenAI Provider Implementation
"""

import logging
from typing import List, Optional

from openai import OpenAI

from .base import LLMProvider
from .types import LLMMessage, LLMResponse, LLMConfig


logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI GPT provider implementation"""

    def __init__(self, api_key: str):
        """Initialize the OpenAI provider.

        Args:
            api_key: OpenAI API key
        """
        self.client = OpenAI(api_key=api_key)

    def generate(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """Generate a response using OpenAI.

        Args:
            messages: List of conversation messages
            config: Optional generation configuration

        Returns:
            LLMResponse with the generated content
        """
        config = config or LLMConfig(model="gpt-4o")

        # Convert to OpenAI format
        openai_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        logger.info(f"OPENAI_REQUEST: model={config.model}, "
                   f"messages={len(openai_messages)}")

        try:
            response = self.client.chat.completions.create(
                model=config.model,
                messages=openai_messages,
                max_tokens=config.max_tokens,
                temperature=config.temperature
            )

            content = response.choices[0].message.content
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }

            logger.info(f"OPENAI_RESPONSE: tokens={usage}, "
                       f"content_len={len(content)}")

            return LLMResponse(
                content=content,
                provider="openai",
                model=config.model,
                usage=usage
            )

        except Exception as e:
            logger.error(f"OPENAI_ERROR: {type(e).__name__}: {e}")
            raise

    def get_provider_name(self) -> str:
        return "openai"
