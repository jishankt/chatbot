import json
import logging
import requests
from typing import List, Dict, Any, Optional
from app.config import Config
from app.agent.validator import validate_output, make_extractive_fallback

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the official Kepler Tech sales consultant for Kepler Tech LLC (Dubai), assisting business customers across the UAE and GCC with commercial photo printers, media, and printing solutions.

ROLE & STYLE (Concise, Conversational, Consultative):
- Carefully read and deeply understand what the customer is asking.
- Answer ONLY what the customer asked: be direct, concise, natural, and helpful (1 to 3 clear sentences for standard inquiries, like ChatGPT or Claude Code).
- Never dump unrequested accessories, full catalog listings, or technical boilerplate unless the user specifically asked for a full overview.
- Do NOT add robotic opening headers ("Regarding...", "According to official specifications...") or unasked pushy follow-up questions on simple factual queries.
- Speak professionally, warmly, and knowledgeably, like an expert Dubai commercial technology advisor.

STRICT FACTUAL CONSTRAINTS:
1. Answer ONLY using the verified facts and retrieved context chunks provided below.
2. If the context does not explicitly contain the answer, reply with 'NO_ANSWER'.
3. NEVER guess, estimate, or invent numbers, dimensions, speeds, weights, warranties, delivery times, or prices.
4. Keep answers factual and strictly grounded in official Kepler Tech documentation.
5. Never state "I specialize exclusively in the CX-02", "We do not sell", "We do not supply", or "excl. VAT".
6. When stating prices or yields, quote the exact figures from the verified facts or retrieved context (e.g. 4,385.00 AED for CX-02, 490.00 AED for 4x6 media, 500.00 AED for 5x7 media, 500.00 AED for 6x8 media, 190.00 AED for cleaning pen, 325.00 AED for carry bag). Never alter figures.
"""


def _call_backend_llm(messages: List[Dict[str, str]], timeout: float = 15.0) -> Optional[str]:
    """
    Dispatches LLM chat request to OpenRouter (if configured) or Ollama.
    Returns generated content string or None on failure.
    """
    use_openrouter = (Config.LLM_PROVIDER == "openrouter") or (bool(Config.OPENROUTER_API_KEY) and Config.LLM_PROVIDER != "ollama")
    if use_openrouter and Config.OPENROUTER_API_KEY:
        try:
            url = f"{Config.OPENROUTER_BASE_URL}/chat/completions"
            headers = {
                "Authorization": f"Bearer {Config.OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://keplertechllc.com",
                "X-Title": "Kepler Tech Sales AI",
                "Content-Type": "application/json"
            }
            payload = {
                "model": Config.OPENROUTER_MODEL,
                "messages": messages,
                "temperature": 0.0,
                "max_tokens": 200
            }
            res = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if res.status_code == 200:
                choices = res.json().get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip()
            logger.warning(f"OpenRouter returned status {res.status_code}: {res.text[:200]}")
        except Exception as e:
            logger.warning(f"OpenRouter request failed ({e}). Attempting Ollama fallback if available.")

    # Fallback / default to Ollama
    try:
        url = f"{Config.OLLAMA_BASE_URL}/api/chat"
        payload = {
            "model": Config.OLLAMA_CHAT_MODEL,
            "messages": messages,
            "stream": False,
            "keep_alive": "24h",
            "options": {
                "temperature": 0.0,
                "num_predict": 180
            }
        }
        res = requests.post(url, json=payload, timeout=timeout)
        if res.status_code == 200:
            return res.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.info(f"Ollama call failed or timed out: {e}")

    return None


def generate_llm_response(
    user_message: str,
    context_chunks: Optional[List[Dict[str, Any]]] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    structured_facts: Optional[Dict[str, Any]] = None,
    target_language: str = "en",
    slot_summary: Optional[str] = None,
    timeout: float = 15.0
) -> str:
    """
    Generates response via OpenRouter / Ollama if available, composing from structured facts and context chunks.
    Validates output against factual constraints. On validator rejection, retries ONCE with
    the rejected claim explicitly constrained before using an extractive fallback.
    """
    context_chunks = context_chunks or []
    if Config.FORCE_EXTRACTIVE_MODE or (not context_chunks and not structured_facts):
        return make_extractive_fallback(context_chunks, user_message, language=target_language)

    from app.agent.admission import acquire_generation_slot, release_generation_slot
    lease_id = acquire_generation_slot()
    if not lease_id:
        logger.warning("LLM generation admission queue wait budget exceeded. Failing fast to humanized fallback.")
        return make_extractive_fallback(context_chunks, user_message, language=target_language)

    context_str = "\n\n".join([f"[{c.get('section', 'Details')}]\n{c.get('text', '')}" for c in context_chunks])
    facts_str = f"Verified Structured Facts:\n{json.dumps(structured_facts, indent=2, ensure_ascii=False)}\n\n" if structured_facts else ""
    slot_ctx = f"Conversation Context & Active Slots: {slot_summary}\n\n" if slot_summary else ""

    lang_instr = ""
    if target_language == "ar":
        lang_instr = "Language Instruction: Respond naturally, warmly, and professionally in Arabic (العربية).\n"
    elif target_language == "ml":
        lang_instr = "Language Instruction: Respond naturally and professionally in Malayalam (മലയാളം).\n"
    elif target_language == "manglish":
        lang_instr = "Language Instruction: Respond in natural UAE colloquial English-Arabic (Manglish/Arabizi).\n"

    prompt = (
        f"{lang_instr}"
        f"{slot_ctx}"
        f"{facts_str}"
        f"Retrieved Technical Context:\n{context_str}\n\n"
        f"Customer Question: {user_message}\n\n"
        f"Answer:"
    )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if conversation_history:
        for turn in conversation_history[-8:]:
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": prompt})

    try:
        candidate_reply = _call_backend_llm(messages, timeout=timeout)
        if candidate_reply:
            if "NO_ANSWER" in candidate_reply or not candidate_reply:
                return make_extractive_fallback(context_chunks, user_message, language=target_language)

            # Combine tool results and chunks for validation
            validation_chunks = list(context_chunks)
            if structured_facts:
                validation_chunks.append({"section": "Facts", "text": json.dumps(structured_facts)})

            is_valid, reason = validate_output(candidate_reply, validation_chunks, user_message)
            if is_valid:
                return candidate_reply

            # Rejection encountered: Retry ONCE with the rejected claims removed / constrained
            logger.info(f"LLM draft 1 rejected by validator ({reason}). Retrying once with targeted constraint...")
            retry_prompt = (
                f"Factual Correction Required: Your previous draft was rejected by the factual validator with reason:\n"
                f"'{reason}'.\n"
                f"Please regenerate the response strictly adhering to the verified facts provided above. "
                f"Do not mention any ungrounded claim or unverified numbers. Focus directly on answering the customer helpfully."
            )
            retry_messages = list(messages) + [
                {"role": "assistant", "content": candidate_reply},
                {"role": "user", "content": retry_prompt}
            ]
            retry_candidate = _call_backend_llm(retry_messages, timeout=timeout)
            if retry_candidate and "NO_ANSWER" not in retry_candidate:
                r_valid, r_reason = validate_output(retry_candidate, validation_chunks, user_message)
                if r_valid:
                    logger.info("LLM draft 2 successfully passed factual validation!")
                    return retry_candidate

            logger.warning(f"LLM output failed validation after retry: {reason}. Using humanized fallback.")
            return make_extractive_fallback(context_chunks, user_message, language=target_language)
        else:
            return make_extractive_fallback(context_chunks, user_message, language=target_language)
    except Exception as e:
        logger.info(f"LLM unreachable or timed out ({e}). Seamlessly falling back to humanized mode.")
        return make_extractive_fallback(context_chunks, user_message, language=target_language)
    finally:
        release_generation_slot(lease_id)
