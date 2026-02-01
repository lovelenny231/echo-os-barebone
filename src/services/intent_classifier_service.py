"""
ECHO OS Barebone: Intent Classifier Service

Classifies user query intent to route to appropriate knowledge layers.

Classification Categories:
- EXTERNAL_LEGAL: General industry knowledge queries (L1 priority)
- INTERNAL_REGULATION: Client-specific data queries (L4 priority)
- PROFESSIONAL_ADVICE: Expert judgment requests (L1+L3+L4)
- CONTEXT_FOLLOWUP: Follow-up on previous conversation (L5 priority)

Hybrid Approach:
1. Lightweight keyword filter: Fast classification for clear queries (~1ms)
2. LLM classification: High-accuracy for ambiguous queries (~500ms)
"""

import re
import logging
from enum import Enum
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger("IntentClassifier")


class QueryIntent(Enum):
    """Query intent classification categories"""
    EXTERNAL_LEGAL = "external_legal"           # L1: Industry knowledge
    INTERNAL_REGULATION = "internal_regulation"  # L4: Client-specific
    PROFESSIONAL_ADVICE = "professional_advice"  # L1+L3+L4: Expert advice
    CONTEXT_FOLLOWUP = "context_followup"        # L5: Context reference


@dataclass
class ClassificationResult:
    """Classification result"""
    intent: QueryIntent
    confidence: float  # 0.0 - 1.0
    method: str       # "keyword" or "llm"
    matched_pattern: Optional[str] = None


# =============================================================================
# Keyword Patterns (Customize for your industry)
# =============================================================================

# INTERNAL_REGULATION (L4 priority) keywords
INTERNAL_REGULATION_PATTERNS = [
    # Self-reference expressions
    r"(当社|弊社|うちの会社|御社|わが社|自社)",
    r"(うちの|弊社の|当社の|御社の)(規則|規程|ルール|制度)",
    r"(社内|会社の)(規程|規則|ルール|制度)",
    # Specific data reference
    r"(○○さん|△△部長|××課長)",
]

# CONTEXT_FOLLOWUP (L5 priority) keywords
CONTEXT_FOLLOWUP_PATTERNS = [
    # Demonstrative pronouns
    r"^(それ|その|これ|この|あれ|あの)",
    r"^(上記|前述|さっき|先ほど)",
    # Follow-up expressions
    r"(について)?(もう少し|詳しく|具体的に)",
    r"(例外|特例|ただし|but|しかし).*(ある|ない|教えて)",
    r"^(では|じゃあ|なら|ということは)",
    r"(続き|続けて|もっと)",
]

# EXTERNAL_LEGAL (L1 priority) keywords
# Note: Replace these with your industry-specific patterns
EXTERNAL_LEGAL_PATTERNS = [
    # General legal/regulatory queries
    r"(法律|法令|制度|規定).*(どう|何|いつ|誰)",
    r"(法的|法律上).*(義務|権利|要件|条件)",
    # Article references
    r"第?\d+条",
    r"(何条|何項|何号)",
]

# PROFESSIONAL_ADVICE keywords
PROFESSIONAL_ADVICE_PATTERNS = [
    # Advice/judgment requests
    r"(どうすれば|どうしたら|どのように)",
    r"(アドバイス|助言|意見|見解)",
    r"(対応|対処|対策).*(すべき|したい|必要)",
    r"(問題|トラブル|紛争).*(解決|対応)",
    # Gap analysis
    r"(法律|法令|規定).*(違反|抵触|問題)",
    r"(改定|改正|変更).*(必要|すべき|対応)",
    # Comparison
    r"(メリット|デメリット|リスク)",
    r"(比較|検討|選択)",
]


def _match_patterns(query: str, patterns: list) -> Optional[str]:
    """Match query against pattern list."""
    for pattern in patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return pattern
    return None


def classify_by_keyword(query: str) -> Optional[ClassificationResult]:
    """Classify by keyword filter.

    Returns result for clear pattern matches, None for LLM fallback.

    Args:
        query: User query

    Returns:
        ClassificationResult or None
    """
    query = query.strip()

    # 1. CONTEXT_FOLLOWUP: Demonstrative pronouns first
    matched = _match_patterns(query, CONTEXT_FOLLOWUP_PATTERNS)
    if matched:
        logger.debug(f"[KEYWORD] CONTEXT_FOLLOWUP matched: {matched}")
        return ClassificationResult(
            intent=QueryIntent.CONTEXT_FOLLOWUP,
            confidence=0.9,
            method="keyword",
            matched_pattern=matched
        )

    # 2. INTERNAL_REGULATION: Self-reference
    matched = _match_patterns(query, INTERNAL_REGULATION_PATTERNS)
    if matched:
        logger.debug(f"[KEYWORD] INTERNAL_REGULATION matched: {matched}")
        return ClassificationResult(
            intent=QueryIntent.INTERNAL_REGULATION,
            confidence=0.85,
            method="keyword",
            matched_pattern=matched
        )

    # 3. EXTERNAL_LEGAL: Direct legal reference
    matched = _match_patterns(query, EXTERNAL_LEGAL_PATTERNS)
    if matched:
        # Check if also requesting advice
        advice_matched = _match_patterns(query, PROFESSIONAL_ADVICE_PATTERNS)
        if advice_matched:
            logger.debug(f"[KEYWORD] PROFESSIONAL_ADVICE (legal+advice): {advice_matched}")
            return ClassificationResult(
                intent=QueryIntent.PROFESSIONAL_ADVICE,
                confidence=0.8,
                method="keyword",
                matched_pattern=f"{matched} + {advice_matched}"
            )

        logger.debug(f"[KEYWORD] EXTERNAL_LEGAL matched: {matched}")
        return ClassificationResult(
            intent=QueryIntent.EXTERNAL_LEGAL,
            confidence=0.85,
            method="keyword",
            matched_pattern=matched
        )

    # 4. PROFESSIONAL_ADVICE: Advice request only
    matched = _match_patterns(query, PROFESSIONAL_ADVICE_PATTERNS)
    if matched:
        logger.debug(f"[KEYWORD] PROFESSIONAL_ADVICE matched: {matched}")
        return ClassificationResult(
            intent=QueryIntent.PROFESSIONAL_ADVICE,
            confidence=0.75,
            method="keyword",
            matched_pattern=matched
        )

    # No match -> LLM fallback
    logger.debug(f"[KEYWORD] No pattern matched, falling back to LLM")
    return None


# =============================================================================
# LLM Classification Prompt
# =============================================================================

CLASSIFICATION_PROMPT = """あなたはクエリ分類エキスパートです。
ユーザーの質問を以下の4つのカテゴリのいずれかに分類してください。

## カテゴリ定義

1. EXTERNAL_LEGAL
   - 一般的な業界知識、法律、規則、制度についての質問
   - 例: 「○○とは？」「△△の要件は？」

2. INTERNAL_REGULATION
   - 自社の規程、データに関する質問
   - 「当社」「弊社」「うちの」などの表現を含む
   - 例: 「弊社の規則では？」「当社の制度は？」

3. PROFESSIONAL_ADVICE
   - 専門家としての判断、意見、アドバイスを求める質問
   - ギャップ分析、対応策の提案など
   - 例: 「どう対応すべき？」「改正への対応は必要？」

4. CONTEXT_FOLLOWUP
   - 直前の会話を参照するフォローアップ質問
   - 「それ」「その」「さっきの」などの指示語を含む
   - 例: 「それについて詳しく」「例外はある？」

## 分類ルール
- 必ず上記4つのうち1つだけを選んでください
- カテゴリ名のみを回答してください（説明不要）

## ユーザーの質問
{query}

## 回答（カテゴリ名のみ）:"""


def classify_by_llm(query: str) -> ClassificationResult:
    """Classify using LLM.

    Args:
        query: User query

    Returns:
        ClassificationResult
    """
    try:
        from ..api.llm import llm_factory, LLMMessage, LLMConfig

        prompt = CLASSIFICATION_PROMPT.format(query=query)
        messages = [LLMMessage(role="user", content=prompt)]

        config = LLMConfig(max_tokens=20, temperature=0.0)
        response = llm_factory.generate(messages, config)

        result_text = response.content.strip().upper()

        intent_map = {
            "EXTERNAL_LEGAL": QueryIntent.EXTERNAL_LEGAL,
            "INTERNAL_REGULATION": QueryIntent.INTERNAL_REGULATION,
            "PROFESSIONAL_ADVICE": QueryIntent.PROFESSIONAL_ADVICE,
            "CONTEXT_FOLLOWUP": QueryIntent.CONTEXT_FOLLOWUP,
        }

        for key, intent in intent_map.items():
            if key in result_text:
                logger.info(f"[LLM] Classified as {intent.value}: '{query[:50]}'")
                return ClassificationResult(
                    intent=intent,
                    confidence=0.8,
                    method="llm",
                    matched_pattern=None
                )

        # Parse failed -> default to EXTERNAL_LEGAL
        logger.warning(f"[LLM] Failed to parse response: {result_text}, defaulting to EXTERNAL_LEGAL")
        return ClassificationResult(
            intent=QueryIntent.EXTERNAL_LEGAL,
            confidence=0.5,
            method="llm",
            matched_pattern=None
        )

    except Exception as e:
        logger.error(f"[LLM] Classification failed: {e}, defaulting to EXTERNAL_LEGAL")
        return ClassificationResult(
            intent=QueryIntent.EXTERNAL_LEGAL,
            confidence=0.3,
            method="error",
            matched_pattern=None
        )


# =============================================================================
# Hybrid Classifier
# =============================================================================

AMBIGUOUS_QUERY_PATTERNS = [
    r"(どう思|どうお考え|ご意見)",
    r"(〜ですか|〜でしょうか)$",
    r"(教えて|説明して|解説して)$",
    r"\?$|？$",
]


def _is_ambiguous_query(query: str) -> bool:
    """Check if query is ambiguous."""
    if len(query) < 20:
        return False

    for pattern in AMBIGUOUS_QUERY_PATTERNS:
        if re.search(pattern, query):
            return True
    return False


def classify_query(query: str, use_llm_fallback: bool = True) -> ClassificationResult:
    """Hybrid intent classifier.

    Args:
        query: User query
        use_llm_fallback: Whether to use LLM fallback

    Returns:
        ClassificationResult
    """
    logger.info(f"[CLASSIFY] Starting classification: '{query[:50]}...'")

    # Step 1: Keyword filter
    result = classify_by_keyword(query)
    if result:
        logger.info(f"[CLASSIFY] Keyword match: {result.intent.value} (confidence={result.confidence})")
        return result

    # Step 2: Conditional LLM fallback
    if use_llm_fallback and _is_ambiguous_query(query):
        logger.info(f"[CLASSIFY] Ambiguous query detected, using LLM fallback")
        result = classify_by_llm(query)
        logger.info(f"[CLASSIFY] LLM result: {result.intent.value} (confidence={result.confidence})")
        return result

    # Step 3: Default classification (EXTERNAL_LEGAL)
    logger.info(f"[CLASSIFY] No pattern match, defaulting to EXTERNAL_LEGAL")
    return ClassificationResult(
        intent=QueryIntent.EXTERNAL_LEGAL,
        confidence=0.5,
        method="default",
        matched_pattern=None
    )


# =============================================================================
# Layer Routing Helper
# =============================================================================

def get_layer_priorities(intent: QueryIntent) -> dict:
    """Get layer priorities based on intent.

    Args:
        intent: Classified intent

    Returns:
        dict with layer names and their priorities/settings
    """
    if intent == QueryIntent.EXTERNAL_LEGAL:
        return {
            "L1": {"enabled": True, "priority": "high", "limit": None},
            "L3": {"enabled": True, "priority": "low", "limit": 500},
            "L4": {"enabled": True, "priority": "low", "limit": 5000},
            "L5": {"enabled": True, "priority": "low", "limit": 1000},
        }

    elif intent == QueryIntent.INTERNAL_REGULATION:
        return {
            "L1": {"enabled": True, "priority": "low", "limit": 1500},
            "L3": {"enabled": True, "priority": "medium", "limit": 1000},
            "L4": {"enabled": True, "priority": "high", "limit": None},
            "L5": {"enabled": True, "priority": "medium", "limit": 2000},
        }

    elif intent == QueryIntent.PROFESSIONAL_ADVICE:
        return {
            "L1": {"enabled": True, "priority": "high", "limit": None},
            "L3": {"enabled": True, "priority": "high", "limit": None},
            "L4": {"enabled": True, "priority": "high", "limit": None},
            "L5": {"enabled": True, "priority": "medium", "limit": 2000},
        }

    elif intent == QueryIntent.CONTEXT_FOLLOWUP:
        return {
            "L1": {"enabled": True, "priority": "low", "limit": 1000},
            "L3": {"enabled": True, "priority": "low", "limit": 500},
            "L4": {"enabled": True, "priority": "low", "limit": 1000},
            "L5": {"enabled": True, "priority": "high", "limit": None},
        }

    # Default: all layers enabled
    return {
        "L1": {"enabled": True, "priority": "medium", "limit": None},
        "L3": {"enabled": True, "priority": "medium", "limit": None},
        "L4": {"enabled": True, "priority": "medium", "limit": None},
        "L5": {"enabled": True, "priority": "medium", "limit": None},
    }
