"""
ECHO OS Barebone: LLM Factory with Fallback Mechanism

Handles provider selection, content-based fallback, and exception-based fallback.
"""

import logging
import os
from typing import List, Optional

from .base import LLMProvider
from .claude_provider import ClaudeProvider
from .openai_provider import OpenAIProvider
from .gemini_provider import GeminiProvider
from .types import LLMMessage, LLMResponse, LLMConfig


logger = logging.getLogger(__name__)


# Content-based fallback keywords
FALLBACK_KEYWORDS = [
    "見当たりませんでした",
    "確認できませんでした",
    "記載がありません",
    "見つかりませんでした",
    "該当する規定はありません",
]

MIN_RESPONSE_LENGTH = 50


def _should_fallback_by_content(content: str, has_l4_context: bool) -> bool:
    """Determine if fallback should be triggered based on response content."""
    if not has_l4_context:
        return False

    if len(content) < MIN_RESPONSE_LENGTH:
        logger.warning(f"FALLBACK_CHECK: Response too short ({len(content)} chars)")
        return True

    for keyword in FALLBACK_KEYWORDS:
        if keyword in content:
            logger.warning(f"FALLBACK_CHECK: Found keyword '{keyword}' in response")
            return True

    return False


class LLMFactory:
    """Factory for creating and managing LLM providers with fallback support.

    Primary: Claude (if ANTHROPIC_API_KEY is set)
    Fallback: OpenAI GPT-4o (if OPENAI_API_KEY is set)
    """

    def __init__(self):
        self.primary: Optional[LLMProvider] = None
        self.fallback: Optional[LLMProvider] = None
        self._initialize_providers()

    def _initialize_providers(self):
        """Initialize primary and fallback providers based on available API keys."""
        primary_llm = os.getenv("PRIMARY_LLM", "").lower()
        google_key = os.getenv("GOOGLE_API_KEY")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        # Explicit PRIMARY_LLM=gemini override
        if primary_llm == "gemini" and google_key:
            self.primary = GeminiProvider(google_key)
            logger.info("LLM_FACTORY: Primary provider = Gemini (PRIMARY_LLM=gemini)")

            if anthropic_key:
                self.fallback = ClaudeProvider(anthropic_key)
                logger.info("LLM_FACTORY: Fallback provider = Claude")

        # Claude as DEFAULT when ANTHROPIC_API_KEY is present
        elif anthropic_key:
            self.primary = ClaudeProvider(anthropic_key)
            logger.info("LLM_FACTORY: Primary provider = Claude (DEFAULT)")

            if google_key:
                self.fallback = GeminiProvider(google_key)
                logger.info("LLM_FACTORY: Fallback provider = Gemini")
            elif openai_key:
                self.fallback = OpenAIProvider(openai_key)
                logger.info("LLM_FACTORY: Fallback provider = OpenAI GPT-4o")

        # Gemini as primary only when no Anthropic key
        elif google_key:
            self.primary = GeminiProvider(google_key)
            logger.info("LLM_FACTORY: Primary provider = Gemini (no Anthropic key)")

            if openai_key:
                self.fallback = OpenAIProvider(openai_key)
                logger.info("LLM_FACTORY: Fallback provider = OpenAI GPT-4o")

        elif openai_key:
            self.primary = OpenAIProvider(openai_key)
            logger.info("LLM_FACTORY: Primary provider = OpenAI GPT-4o (no Anthropic/Google key)")

        if not self.primary:
            logger.error("LLM_FACTORY: No LLM provider configured! "
                        "Set GOOGLE_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY")

    def generate(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None,
        has_l4_context: bool = False
    ) -> LLMResponse:
        """Generate a response using the configured providers.

        Args:
            messages: List of conversation messages
            config: Optional generation configuration
            has_l4_context: Whether L4 context was provided

        Returns:
            LLMResponse with the generated content

        Raises:
            RuntimeError: If no LLM provider is configured
        """
        if not self.primary:
            raise RuntimeError(
                "No LLM provider configured. "
                "Set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable."
            )

        try:
            response = self.primary.generate(messages, config)

            if has_l4_context and _should_fallback_by_content(response.content, has_l4_context):
                if self.fallback:
                    logger.warning("LLM_FALLBACK: Content quality issue, trying fallback provider")

                    fallback_config = LLMConfig(model="gpt-4o")
                    fallback_response = self.fallback.generate(messages, fallback_config)
                    fallback_response.fallback_used = True
                    fallback_response.fallback_reason = "content_quality"

                    logger.info(f"LLM_FALLBACK_SUCCESS: provider={fallback_response.provider}, "
                              f"reason=content_quality")
                    return fallback_response
                else:
                    logger.warning("LLM_FALLBACK: Content quality issue but no fallback available")

            return response

        except Exception as e:
            logger.warning(f"LLM_PRIMARY_FAILED: {type(e).__name__}: {e}")

            if self.fallback:
                logger.info("LLM_FALLBACK: Attempting exception-based fallback")

                try:
                    fallback_config = LLMConfig(model="gpt-4o")
                    fallback_response = self.fallback.generate(messages, fallback_config)
                    fallback_response.fallback_used = True
                    fallback_response.fallback_reason = "exception"

                    logger.info(f"LLM_FALLBACK_SUCCESS: provider={fallback_response.provider}, "
                              f"reason=exception")
                    return fallback_response

                except Exception as fallback_error:
                    logger.error(f"LLM_FALLBACK_FAILED: {type(fallback_error).__name__}: {fallback_error}")
                    raise

            raise

    def get_primary_provider_name(self) -> Optional[str]:
        """Get the name of the primary provider."""
        return self.primary.get_provider_name() if self.primary else None

    def get_fallback_provider_name(self) -> Optional[str]:
        """Get the name of the fallback provider."""
        return self.fallback.get_provider_name() if self.fallback else None


# Global singleton instance
llm_factory = LLMFactory()
