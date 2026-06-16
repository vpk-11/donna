import json
import logging
from models.schemas import IntentResult, JudgeResult
from intelligence.judge_rules import (
    ALWAYS_ESCALATE_INTENTS,
    ALWAYS_AUTONOMOUS_INTENTS,
    AUTONOMOUS_WITH_NOTIFY_INTENTS,
    CONFIDENCE_THRESHOLD,
    UNKNOWN_ESCALATION_TURN,
    NEW_CLIENT_STATUSES,
)
from intelligence.llm_client import call_llm
from intelligence.prompts import JUDGE_SYSTEM, JUDGE_USER_TEMPLATE

logger = logging.getLogger(__name__)


async def evaluate(
    intent_result: IntentResult,
    role: str,
    turn_count: int,
    context: dict,
    client_status: str | None = None,
    is_new_client: bool = False,
) -> JudgeResult:
    intent = intent_result.intent
    confidence = intent_result.confidence

    if confidence < CONFIDENCE_THRESHOLD:
        return JudgeResult(
            decision="escalate_to_admin",
            reason=f"Intent confidence {confidence:.2f} below threshold {CONFIDENCE_THRESHOLD}",
            confidence=confidence,
        )

    if intent == "UNKNOWN" and turn_count >= UNKNOWN_ESCALATION_TURN:
        return JudgeResult(
            decision="escalate_to_admin",
            reason=f"UNKNOWN intent persisted for {turn_count} turns",
            confidence=1.0,
        )

    if intent in ALWAYS_ESCALATE_INTENTS:
        return JudgeResult(
            decision="escalate_to_admin",
            reason=f"Intent {intent} always requires admin involvement",
            confidence=1.0,
        )

    if intent == "BOOK_REQUEST" and role == "client":
        if is_new_client or client_status in NEW_CLIENT_STATUSES:
            return JudgeResult(
                decision="escalate_to_admin",
                reason="New client booking requires admin confirmation",
                confidence=1.0,
            )

    if intent in ALWAYS_AUTONOMOUS_INTENTS:
        return JudgeResult(
            decision="autonomous",
            reason=f"Intent {intent} is always handled autonomously",
            confidence=1.0,
        )

    if intent in AUTONOMOUS_WITH_NOTIFY_INTENTS:
        return JudgeResult(
            decision="notify_admin",
            reason=f"Intent {intent} is autonomous but admin is notified",
            confidence=1.0,
        )

    if intent == "BOOK_REQUEST" and role == "client":
        return JudgeResult(
            decision="autonomous",
            reason="Existing client booking — agent will check auto_book config",
            confidence=1.0,
        )

    if role == "admin" and intent in ("CONFIRM", "DECLINE"):
        return JudgeResult(
            decision="autonomous",
            reason="Admin confirmation or decline is always executed",
            confidence=1.0,
        )

    logger.info(
        "judge.llm_fallback",
        extra={"intent": intent, "role": role, "turn_count": turn_count},
    )
    return await _llm_judge(intent_result, role, turn_count, context)


async def _llm_judge(
    intent_result: IntentResult,
    role: str,
    turn_count: int,
    context: dict,
) -> JudgeResult:
    user_prompt = JUDGE_USER_TEMPLATE.format(
        intent=intent_result.intent,
        entities=json.dumps(intent_result.entities),
        confidence=intent_result.confidence,
        role=role,
        turn_count=turn_count,
        context=json.dumps({k: v for k, v in context.items() if not k.startswith("_")}),
    )
    try:
        raw = await call_llm(
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        data = json.loads(raw)
        return JudgeResult(
            decision=data.get("decision", "escalate_to_admin"),
            reason=data.get("reason", "LLM judge fallback"),
            confidence=float(data.get("confidence", 0.5)),
        )
    except Exception as e:
        logger.warning(f"judge.llm_fallback failed: {e} — defaulting to escalate")
        return JudgeResult(
            decision="escalate_to_admin",
            reason=f"LLM judge failed: {e}",
            confidence=0.0,
        )
