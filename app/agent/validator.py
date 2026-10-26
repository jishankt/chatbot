import re
from typing import Tuple, List, Dict, Any
from app.agent.guardrails import check_post_guardrails

# Commercial claims that must be strictly grounded
COMMERCIAL_CLAIM_TERMS = [
    "warranty", "guarantee", "discount", "promo", "free delivery",
    "free shipping", "delivery charge", "refund", "vat"
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


def validate_output(
    candidate_reply: str,
    context_chunks: List[Dict[str, Any]],
    user_question: str
) -> Tuple[bool, str]:
    """
    Validates LLM candidate response:
    1. Rejects unauthorized competitor or model mentions.
    2. Rejects any number/price/spec not grounded in context or user question.
    3. Rejects ungrounded commercial claims (warranty, discount, delivery, VAT, refund).
    """
    # 1. Post-guardrail check
    post_ok, post_err = check_post_guardrails(candidate_reply)
    if not post_ok:
        return False, f"Post-guardrail failure: {post_err}"

    reply_lower = candidate_reply.lower()
    combined_grounding = user_question.lower() + " " + " ".join([c.get("text", "").lower() for c in context_chunks])

    # 2. Check commercial claims
    for term in COMMERCIAL_CLAIM_TERMS:
        if term in reply_lower:
            if term not in combined_grounding:
                return False, f"Ungrounded commercial claim detected: '{term}' is not present in context or question."

    # 3. Check numbers / prices / specs
    candidate_numbers = extract_numbers_and_claims(candidate_reply)
    grounded_numbers = set(extract_numbers_and_claims(combined_grounding))

    for num in candidate_numbers:
        is_grounded = False
        if num in grounded_numbers:
            is_grounded = True
        else:
            # Try float comparison if simple number
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
            return False, f"Ungrounded number or spec detected: '{num}' was not found in retrieved context."

    return True, ""


def make_extractive_fallback(context_chunks: List[Dict[str, Any]], user_question: str) -> str:
    """
    Generates a guaranteed grounded, extractive response directly from context chunks.
    """
    if not context_chunks:
        return (
            "I could not locate verified specifications in our official Citizen CX-02 documentation to answer your question. "
            "I have escalated your inquiry to our Kepler Tech sales team to provide accurate details."
        )

    top_chunk = context_chunks[0]
    section = top_chunk.get("section", "Specifications")
    text = top_chunk.get("text", "")

    # Clean markdown headers and present exact bullet points
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")]
    extracted_body = "\n".join(lines[:7])

    return (
        f"According to the official Citizen CX-02 technical documentation ({section}):\n\n"
        f"{extracted_body}\n\n"
        f"For further technical guidance, our Kepler Tech team in Dubai is available at 00971 4 323 1008."
    )
