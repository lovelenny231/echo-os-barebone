"""
ECHO OS Barebone: Gemini Provider Implementation
"""

import logging
from typing import List, Optional

from .base import LLMProvider
from .types import LLMMessage, LLMResponse, LLMConfig


logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """Google Gemini provider implementation"""

    def __init__(self, api_key: str):
        """Initialize the Gemini provider.

        Args:
            api_key: Google API key
        """
        try:
            from google import genai
            self.client = genai.Client(api_key=api_key)
            self.genai = genai
        except ImportError:
            logger.error("google-genai package not installed")
            raise

    def generate(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """Generate a response using Gemini.

        Args:
            messages: List of conversation messages
            config: Optional generation configuration

        Returns:
            LLMResponse with the generated content
        """
        config = config or LLMConfig(model="gemini-2.0-flash")

        # Extract system prompt and user messages
        system_prompt = None
        contents = []

        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                role = "user" if msg.role == "user" else "model"
                contents.append({"role": role, "parts": [{"text": msg.content}]})

        logger.info(f"GEMINI_REQUEST: model={config.model}, "
                   f"system_len={len(system_prompt) if system_prompt else 0}, "
                   f"contents={len(contents)}")

        try:
            generation_config = self.genai.types.GenerateContentConfig(
                temperature=config.temperature,
                max_output_tokens=config.max_tokens,
                system_instruction=system_prompt if system_prompt else None,
            )

            response = self.client.models.generate_content(
                model=config.model,
                contents=contents,
                config=generation_config,
            )

            content = response.text
            usage = {}
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = {
                    "prompt_tokens": getattr(response.usage_metadata, 'prompt_token_count', 0),
                    "completion_tokens": getattr(response.usage_metadata, 'candidates_token_count', 0),
                }

            logger.info(f"GEMINI_RESPONSE: tokens={usage}, "
                       f"content_len={len(content)}")

            return LLMResponse(
                content=content,
                provider="gemini",
                model=config.model,
                usage=usage
            )

        except Exception as e:
            logger.error(f"GEMINI_ERROR: {type(e).__name__}: {e}")
            raise

    def get_provider_name(self) -> str:
        return "gemini"
