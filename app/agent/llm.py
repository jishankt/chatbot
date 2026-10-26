import json
import logging
import requests
from typing import List, Dict, Any, Optional
from app.config import Config
from app.agent.validator import validate_output, make_extractive_fallback

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the official B2B sales assistant for Kepler Tech LLC (Dubai), dedicated exclusively to the Citizen CX-02 dye-sublimation photo printer.

STRICT CONSTRAINTS:
1. Answer ONLY using the provided retrieved context chunks below.
2. If the context does not explicitly contain the answer, reply with 'NO_ANSWER'.
3. NEVER guess, estimate, or invent numbers, dimensions, speeds, weights, warranties, delivery times, or prices.
4. Keep answers concise, factual, and strictly grounded in the official Citizen CX-02 documentation.
"""


def generate_llm_response(
    user_message: str,
    context_chunks: List[Dict[str, Any]],
    conversation_history: Optional[List[Dict[str, str]]] = None,
    timeout: float = 5.0
) -> str:
    """
    Generates response via Ollama if available, validating all outputs against retrieved context.
    If Ollama is stopped, times out, or produces ungrounded claims, falls back to extractive mode.
    """
    if Config.FORCE_EXTRACTIVE_MODE or not context_chunks:
        return make_extractive_fallback(context_chunks, user_message)

    context_str = "\n\n".join([f"[{c['section']}]\n{c['text']}" for c in context_chunks])
    prompt = (
        f"Retrieved Technical Context:\n{context_str}\n\n"
        f"Customer Question: {user_message}\n\n"
        f"Answer:"
    )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if conversation_history:
        for turn in conversation_history[-4:]:
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": prompt})

    try:
        url = f"{Config.OLLAMA_BASE_URL}/api/chat"
        payload = {
            "model": Config.OLLAMA_CHAT_MODEL,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 250
            }
        }
        res = requests.post(url, json=payload, timeout=timeout)
        if res.status_code == 200:
            candidate_reply = res.json().get("message", {}).get("content", "").strip()

            if "NO_ANSWER" in candidate_reply or not candidate_reply:
                return make_extractive_fallback(context_chunks, user_message)

            # Validate candidate reply
            is_valid, reason = validate_output(candidate_reply, context_chunks, user_message)
            if is_valid:
                return candidate_reply
            else:
                logger.warning(f"LLM output rejected by validator: {reason}. Using extractive fallback.")
                return make_extractive_fallback(context_chunks, user_message)
        else:
            logger.info(f"Ollama returned status {res.status_code}. Using extractive fallback.")
            return make_extractive_fallback(context_chunks, user_message)
    except Exception as e:
        logger.info(f"Ollama unreachable or timed out ({e}). Seamlessly falling back to extractive mode.")
        return make_extractive_fallback(context_chunks, user_message)
