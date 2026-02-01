"""
ECHO OS Barebone: System Prompt Template

This is a template for creating industry-specific system prompts.
Customize this file for your use case.

Environment Variables:
- SERVICE_NAME: Service name (e.g., "AIアシスタント")
- PERSONA_NAME: AI persona name (e.g., "AIエキスパート")
"""

import os

# Get service identity from environment
SERVICE_NAME = os.getenv("SERVICE_NAME", "AIアシスタント")
PERSONA_NAME = os.getenv("PERSONA_NAME", "AIエキスパート")

# =============================================================================
# System Prompt Template
# =============================================================================
#
# Customize this prompt for your industry/use case.
# The following placeholders are available:
#   {company_name} - Client company name
#   {l1_context} - L1 layer context (industry knowledge)
#   {l3_context} - L3 layer context (office knowledge)
#   {l4_context} - L4 layer context (client-specific data)
#   {l5_context} - L5 layer context (conversation history)
#   {cbr_context} - Case-based reasoning context
#
# =============================================================================

SYSTEM_PROMPT = f"""
あなたは{PERSONA_NAME}です。
ユーザーからの質問に対して、専門知識を活かして丁寧に回答します。

<style>
- 質問に対して、自分の言葉で自然に答える
- **太字**や見出しで読みやすく整理する
- コンテキストに関連情報があれば、それを根拠に回答する
- 余計な前置きや締めの挨拶は不要
</style>

<knowledge>
以下の情報を参照できます。

- {{company_name}}に関する情報
- 業界知識
- 過去の会話履歴
</knowledge>

<context>
【業界知識】
{{l1_context}}

【{{company_name}}の情報】
{{l4_context}}

【参考情報】
{{l3_context}}

【会話履歴】
{{l5_context}}

【類似事例】
{{cbr_context}}
</context>
"""


def build_system_prompt(
    l1_context: str,
    l3_context: str,
    l4_context: str,
    l5_context: str,
    company_name: str,
    cbr_context: str = ""
) -> str:
    """
    Build a system prompt with embedded context.

    Args:
        l1_context: Industry knowledge
        l3_context: Office knowledge
        l4_context: Client-specific data
        l5_context: Conversation memory
        company_name: The client company name
        cbr_context: Similar case-based reasoning context

    Returns:
        Complete system prompt with all context embedded
    """
    return SYSTEM_PROMPT.format(
        company_name=company_name,
        l4_context=l4_context if l4_context and l4_context.strip() else "（該当する情報なし）",
        l3_context=l3_context if l3_context and l3_context.strip() else "（該当する情報なし）",
        l1_context=l1_context if l1_context and l1_context.strip() else "（該当する情報なし）",
        l5_context=l5_context if l5_context and l5_context.strip() else "（初回の会話）",
        cbr_context=cbr_context if cbr_context and cbr_context.strip() else "（該当する過去事例なし）"
    )
