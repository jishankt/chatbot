import re
from typing import Tuple, List, Dict, Any, Optional
from app.config import Config
from app.agent.guardrails import check_post_guardrails

# Commercial claims that must be strictly grounded
COMMERCIAL_CLAIM_TERMS = [
    "warranty", "guarantee", "discount", "promo", "free delivery",
    "free shipping", "delivery charge", "refund", "vat"
]

# Banned claims regexes: strictly forbidden unless explicitly supplied by a verified tool result or retrieved chunk
BANNED_CLAIM_PATTERNS = [
    (r"\b(in[- ]stock|out[- ]of[- ]stock|stock availability|\b\d+\s+units in stock)\b", "stock"),
    (r"\b(discount|discounted|\b\d+%\s*off|special price|reduced price|promotional discount)\b", "discount"),
    (r"\b(delivered\s+(?:to\s+\w+\s+)?tomorrow|delivered\s+within|delivery\s+within|same[- ]day\s+delivery|guaranteed\s+delivery|delivery\s+guaranteed|will\s+be\s+delivered|delivery\s+to\s+\w+)\b", "delivery time"),
    (r"\b(\d+[- ]year\s+(?:comprehensive\s+)?warranty|comprehensive(?:\s+international)?\s+warranty|lifetime warranty|extended warranty)\b", "warranty"),
    (r"\b(compatible with all|works with any|universal compatibility)\b", "compatibility"),
    (r"\b(free delivery|free shipping|free samples?|free gift|free roll|free of charge)\b", "free")
]

# Standard allowed model numbers related to CX-02 product identity
ALLOWED_MODEL_NUMBERS = {"02", "2"}


def extract_numbers_and_claims(text: str) -> List[str]:
    """
    Extracts numerical figures, prices, dimensions, and percentages from text.
    Standardizes dimension formats like '4 x 6' -> '4x6'.
    """
    # Normalize dimensions: 4 x 6 -> 4x6
    norm_text = re.sub(r"(\d+)\s*[xX*]\s*(\d+)", r"\1x\2", text)

    # Replace known model name CX-02 so '02' is not extracted as an ungrounded spec
    norm_text = re.sub(r"\bcx-02\b", "CX_MODEL", norm_text, flags=re.IGNORECASE)
    norm_text = re.sub(r"\bcx02\b", "CX_MODEL", norm_text, flags=re.IGNORECASE)

    # Match patterns like 4385, 4,385, 8.4, 300x300, 5%, 490.00, 4x6
    candidates = re.findall(r"\b\d+(?:[.,]\d+)*(?:x\d+)?%?\b", norm_text)
    cleaned = []
    for c in candidates:
        clean_num = c.replace(",", "").strip()
        if clean_num in ALLOWED_MODEL_NUMBERS:
            continue
        if len(clean_num) > 1 or "." in clean_num or "x" in clean_num or "%" in clean_num:
            cleaned.append(clean_num)
        elif clean_num in ("0",):
            cleaned.append(clean_num)
    return cleaned


def validate_response(
    reply: str,
    tool_results: Optional[List[Any]] = None,
    retrieved_chunks: Optional[List[Dict[str, Any]]] = None,
    user_message: Optional[str] = None
) -> Dict[str, Any]:
    """
    Claim-level validation of system and LLM responses.
    Validates:
    1. Guardrails (banned prompts, leak checks, prompt injection)
    2. Banned commercial claims (stock, discount, delivery time, warranty, compatibility, free)
       unless explicitly present in tool_results or retrieved_chunks.
    3. Strict numerical / spec grounding (number + unit + product).
    """
    # 1. Post-guardrail safety check
    post_ok, post_err = check_post_guardrails(reply)
    if not post_ok:
        return {"is_valid": False, "reason": f"Post-guardrail failure: {post_err}"}

    import json
    tools_str = " ".join([json.dumps(t) if isinstance(t, (dict, list)) else str(t) for t in (tool_results or [])])
    chunks_str = " ".join([c.get("text", "") for c in (retrieved_chunks or [])])
    combined_grounding = f"{tools_str} {chunks_str} {user_message or ''}".lower()

    reply_lower = reply.lower()

    # 2. Check banned commercial claim categories
    for pat, claim_name in BANNED_CLAIM_PATTERNS:
        match = re.search(pat, reply_lower, re.IGNORECASE)
        if match:
            matched_phrase = match.group(0).lower()
            # If the matched phrase is not present in tools or chunks, reject!
            if matched_phrase not in tools_str.lower() and matched_phrase not in chunks_str.lower():
                return {
                    "is_valid": False,
                    "reason": f"Ungrounded banned claim detected: '{matched_phrase}' ({claim_name}) not found in verified tools or retrieved chunks."
                }

    # 3. Check numbers / prices / specs grounding (Rule 2: strictly from tool results, retrieved chunks, or user message)
    candidate_numbers = extract_numbers_and_claims(reply)
    grounded_numbers = set(extract_numbers_and_claims(combined_grounding))

    for num in candidate_numbers:
        is_grounded = False
        if num in grounded_numbers:
            is_grounded = True
        else:
            try:
                num_val = float(num.replace("%", ""))
                for gn in grounded_numbers:
                    try:
                        gn_val = float(gn.replace("%", ""))
                        if abs(num_val - gn_val) < 0.001:
                            is_grounded = True
                            break
                    except ValueError:
                        continue
            except ValueError:
                pass

        if not is_grounded:
            return {
                "is_valid": False,
                "reason": f"Ungrounded number or spec detected: '{num}' was not found in retrieved context or tools."
            }

    return {"is_valid": True, "reason": ""}


def validate_output(
    candidate_reply: str,
    context_chunks: List[Dict[str, Any]],
    user_question: str
) -> Tuple[bool, str]:
    """Adapter for existing pipeline callers."""
    res = validate_response(
        reply=candidate_reply,
        tool_results=[],
        retrieved_chunks=context_chunks,
        user_message=user_question
    )
    return res["is_valid"], res.get("reason", "")


def make_extractive_fallback(
    context_chunks: List[Dict[str, Any]],
    user_question: str,
    language: str = "en",
    slot_summary: Optional[str] = None
) -> str:
    """
    Generates a varied, conversational, grounded fallback response directly from context chunks.
    Acknowledges the customer's exact question, respects detected language, and asks at most one follow-up.
    """
    if not context_chunks:
        if language == "ar":
            return (
                "أود التأكد من تزويدك بأدق التفاصيل الفنية والتجارية المعتمدة لاحتياجك. "
                "فريقنا المتخصص في دبي يسعد بمساعدتك مباشرة:\n"
                f"📞 هاتف: {Config.KEPLER_PHONE} | 💬 واتساب: {Config.KEPLER_WHATSAPP}\n\n"
                "هل تود أن يقوم مستشار المبيعات لدينا بالتواصل معك اليوم؟"
            )
        elif language == "ml":
            return (
                "നിങ്ങളുടെ ആവശ്യങ്ങൾക്ക് കൃത്യമായ വിവരങ്ങൾ നൽകാൻ ഞങ്ങൾ ആഗ്രഹിക്കുന്നു. "
                f"ഞങ്ങളുടെ ദുബായ് കൺസൾട്ടന്റുമായി ബന്ധപ്പെടാം: 📞 {Config.KEPLER_PHONE} | 💬 {Config.KEPLER_WHATSAPP}\n\n"
                "താങ്കൾക്ക് ഒരു പ്രത്യേക കൊട്ടേഷൻ തയ്യാറാക്കി നൽകണമെന്നുണ്ടോ?"
            )
        elif language == "manglish":
            return (
                "Marhaba! For full technical specs and commercial allocation on this model, "
                f"our Dubai sales team can guide you directly: 📞 {Config.KEPLER_PHONE} | 💬 {Config.KEPLER_WHATSAPP}\n\n"
                "Would you like an official quote sent to your email or WhatsApp?"
            )
        else:
            return (
                "I want to make sure I give you completely accurate and verified information for your requirements. "
                f"Our Kepler Tech commercial team in Dubai will be happy to assist you directly:\n"
                f"📞 Phone: {Config.KEPLER_PHONE} | 💬 WhatsApp: {Config.KEPLER_WHATSAPP} | 📧 {Config.SALESPERSON_EMAIL}\n\n"
                "Would you like our technical sales specialist to prepare a detailed quotation for you?"
            )

    top_chunk = context_chunks[0]
    section = top_chunk.get("section", "Specifications")
    text = top_chunk.get("text", "")

    # Clean text lines
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")]
    
    q_low = user_question.lower()

    # Prioritize lines matching specific customer query keywords
    keywords = [w for w in re.findall(r"\w+", q_low) if len(w) > 3 and w not in ["what", "when", "where", "which", "tell", "about", "printer", "citizen", "kepler", "give"]]
    relevant_lines = [l for l in lines if any(kw in l.lower() for kw in keywords)]
    selected_lines = relevant_lines[:3] if relevant_lines else lines[:4]
    extracted_body = "\n".join(selected_lines)

    # Detect model from inquiry (defaults to flagship CX-02 if generic)
    if any(m in q_low for m in ["cx-02w", "cx02w", "cx 02w"]):
        model_en = "Citizen CX-02W"
        model_ar = "سيتيزن CX-02W"
        model_ml = "Citizen CX-02W"
    elif any(m in q_low for m in ["cy-02", "cy02", "cy 02"]):
        model_en = "Citizen CY-02"
        model_ar = "سيتيزن CY-02"
        model_ml = "Citizen CY-02"
    elif any(m in q_low for m in ["cz-01", "cz01", "cz 01"]):
        model_en = "Citizen CZ-01"
        model_ar = "سيتيزن CZ-01"
        model_ml = "Citizen CZ-01"
    else:
        model_en = "Citizen CX-02"
        model_ar = "سيتيزن CX-02"
        model_ml = "Citizen CX-02"

    # Contextual header with verified details & technical specifications
    if any(s in q_low for s in ["speed", "fast", "seconds", "how long", "سرعة", "സമയം"]):
        header_en = f"Here are the verified details and technical specifications for {model_en} print speed:"
        header_ar = f"إليك التفاصيل المعتمدة والمواصفات الفنية لسرعة طباعة {model_ar}:"
        header_ml = f"{model_ml} ഫോട്ടോ പ്രിന്ററിന്റെ പ്രിന്റ് സ്പീഡ് വിവരങ്ങൾ:"
    elif any(d in q_low for d in ["size", "dimension", "weight", "heavy", "portable", "أبعاد", "وزن", "വലിപ്പം", "ഭാരം"]):
        header_en = f"Here are the verified details and technical specifications for {model_en} dimensions and weight:"
        header_ar = f"إليك التفاصيل المعتمدة والمواصفات الفنية لأبعاد ووزن {model_ar}:"
        header_ml = f"{model_ml} പ്രിന്ററിന്റെ വലിപ്പവും ഭാരവും സംബന്ധിച്ച വിവരങ്ങൾ:"
    elif any(m in q_low for m in ["media", "paper", "roll", "yield", "box", "4x6", "5x7", "6x8", "8x10", "8x12", "ورق", "رول"]):
        header_en = f"Here are the verified details and technical specifications for genuine {model_en} media:"
        header_ar = f"إليك التفاصيل المعتمدة والمواصفات الفنية لرولات ورق {model_ar}:"
        header_ml = f"{model_ml} മീഡിയ റോളുകളും പ്രിന്റ് കപ്പാസിറ്റിയും:"
    elif any(c in q_low for c in ["clean", "pen", "maintenance", "printhead", "تنظيف", "صيانة", "ക്ലീനിംഗ്"]):
        header_en = f"Here are the verified details and technical specifications for {model_en} printhead maintenance:"
        header_ar = f"إليك التفاصيل المعتمدة والمواصفات الفنية لتنظيف رأس الطباعة وصيانة {model_ar}:"
        header_ml = f"{model_ml} പ്രിന്റ്ഹെഡ് ക്ലീനിംഗും മെയിന്റനൻസും സംബന്ധിച്ച വിവരങ്ങൾ:"
    else:
        header_en = f"Here are the verified details and technical specifications for the {model_en} ({section}):"
        header_ar = f"إليك التفاصيل المعتمدة والمواصفات الفنية لطابعة {model_ar} ({section}):"
        header_ml = f"{model_ml}-ന്റെ വിശദാംശങ്ങൾ ({section}):"

    contact_en = f"Our Kepler Tech team in Dubai is available at {Config.KEPLER_PHONE}."
    contact_ar = f"فريق كيبلر تك في دبي متاح أيضاً لمساعدتك على {Config.KEPLER_PHONE}."
    contact_ml = f"കൂടുതൽ വിവരങ്ങൾക്ക് ഞങ്ങളുടെ ദുബായ് ഓഫീസുമായി {Config.KEPLER_PHONE} എന്ന നമ്പറിൽ ബന്ധപ്പെടാം."

    if language == "ar":
        return f"{header_ar}\n\n{extracted_body}\n\n{contact_ar}"
    elif language == "ml":
        return f"{header_ml}\n\n{extracted_body}\n\n{contact_ml}"
    elif language == "manglish":
        return f"{header_en}\n\n{extracted_body}\n\n{contact_en}"
    else:
        return f"{header_en}\n\n{extracted_body}\n\n{contact_en}"
