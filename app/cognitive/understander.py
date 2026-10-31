import re
import json
import time
import logging
from typing import Optional, List, Dict, Any, Literal, Tuple
from pydantic import BaseModel, Field
import requests

from app.config import Config
from app.agent.router import classify_intent
from app.agent.guardrails import check_pre_guardrails, COMPETITOR_BRANDS, OTHER_CITIZEN_MODELS
from app.cognitive.reader import ReadContext, UNSUPPORTED_ITEMS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic Schemas for Structured NLU
# ---------------------------------------------------------------------------

class NLUIntent(BaseModel):
    primary_intent: str
    sub_intent: Optional[str] = None
    confidence: float = 1.0


class NLUEntities(BaseModel):
    sku: Optional[str] = None
    quantity: Optional[int] = None
    delivery_destination: Optional[str] = None  # "UAE", "GCC", "outside_gcc"
    business_type: Optional[str] = None  # "photobooth", "studio", "freelance", "kiosk", "event", "unknown"
    budget: Optional[float] = None


class NLURiskFlags(BaseModel):
    competitor_mentioned: bool = False
    churn_risk: bool = False
    anger_frustration: bool = False
    legal_threat: bool = False
    prompt_injection: bool = False


class UnderstandResult(BaseModel):
    intent: NLUIntent
    commercial_readiness: Literal["high", "medium", "low"] = "medium"
    entities: NLUEntities
    sentiment: Literal["positive", "neutral", "negative", "frustrated"] = "neutral"
    urgency: Literal["urgent", "normal"] = "normal"
    risk_flags: NLURiskFlags
    source: Literal["rules", "llm", "arbitrated"] = "rules"
    arbitration_notes: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Circuit Breaker for LLM Service Resilience
# ---------------------------------------------------------------------------

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 15.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"  # "CLOSED", "OPEN", "HALF_OPEN"

    def can_attempt(self) -> bool:
        now = time.time()
        if self.state == "OPEN":
            if now - self.last_failure_time > self.cooldown_seconds:
                self.state = "HALF_OPEN"
                logger.info("CircuitBreaker transitioned to HALF_OPEN")
                return True
            return False
        return True

    def record_success(self):
        if self.state != "CLOSED":
            logger.info("CircuitBreaker transitioned to CLOSED after successful request")
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(
                f"CircuitBreaker OPENED: {self.failure_count} consecutive failures. "
                f"Cooling down for {self.cooldown_seconds}s"
            )


circuit_breaker = CircuitBreaker()


# ---------------------------------------------------------------------------
# Keyword / Entity Detection Rules
# ---------------------------------------------------------------------------

DESTINATION_UAE_PATTERNS = [
    r"\b(uae|dubai|dxb|abu\s*dhabi|sharjah|ajman|rak|ras\s*al\s*khaimah|fujairah|umm\s*al\s*quwain|uaq)\b",
    r"\b(دبي|ابوظبي|أبوظبي|الشارقة|عجمان|الفجيرة|رأس الخيمة|ام القيوين|الإمارات|الامارات)\b"
]

DESTINATION_GCC_PATTERNS = [
    r"\b(gcc|saudi|ksa|riyadh|jeddah|dammam|qatar|doha|kuwait|bahrain|manama|oman|muscat)\b",
    r"\b(السعودية|المملكة|الرياض|جدة|الدمام|قطر|الدوحة|الكويت|البحرين|المنامة|عمان|مسقط|الخليج)\b"
]

DESTINATION_OUTSIDE_GCC_PATTERNS = [
    r"\b(africa|nigeria|lagos|kenya|nairobi|ghana|accra|egypt|cairo|ethiopia|tanzania|europe|uk|usa|india|pakistan)\b",
    r"\b(أفريقيا|افريقيا|مصر|القاهرة|نيجيريا|كينيا|غانا)\b"
]

BUSINESS_TYPE_PATTERNS = {
    "photobooth": [r"\bphoto\s*booth\b", r"\bphotobooth\b", r"\bbooth\b", r"\b360\s*booth\b", r"\bكشك\s*تصوير\b", r"\bفوتوبوث\b"],
    "studio": [r"\bstudio\b", r"\bphoto\s*studio\b", r"\bdigital\s*studio\b", r"\bاستوديو\b", r"\bاستديو\b"],
    "event": [r"\bevent\b", r"\bevents\b", r"\bwedding\b", r"\bweddings\b", r"\bparty\b", r"\bparties\b", r"\bفعاليات\b", r"\bاعراس\b", r"\bأعراس\b"],
    "freelance": [r"\bfreelance\b", r"\bfreelancer\b", r"\bphotographer\b", r"\bمصور\b", r"\bفوتوغرافي\b"],
    "kiosk": [r"\bkiosk\b", r"\bretail\b", r"\bmall\b", r"\bshop\b", r"\bكشك\b", r"\bمحل\b"]
}

URGENCY_PATTERNS = [
    r"\b(urgent|urgently|asap|today|immediately|right\s*now|rush|emergency|fastest\s*delivery)\b",
    r"\b(عاجل|ضروري|اليوم|فوراً|فورا|الان|الآن)\b"
]

SENTIMENT_FRUSTRATED_PATTERNS = [
    r"\b(ridiculous|scam|terrible|worst|unacceptable|furious|horrible|cheated|disaster|frustrated|frustrating)\b",
    r"\b(you\s*(do\s*not|don'?t)\s*understand|that'?s\s*not\s*what\s*i\s*(asked|said)|stop\s*repeating|useless\s*bot|i\s*already\s*said|not\s*listening)\b",
    r"\b(مهزلة|نصب|سيء\s*جدا|كارثة|غير\s*مقبول|ما\s*تفهم|مش\s*هذا\s*اللي\s*طلبته)\b"
]

SENTIMENT_NEGATIVE_PATTERNS = [
    r"\b(broken|faulty|not\s*working|delayed|late|disappointed|too\s*expensive|issue|problem)\b",
    r"\b(خراب|معطل|تأخير|غالي\s*جدا|مشكلة)\b"
]

SENTIMENT_POSITIVE_PATTERNS = [
    r"\b(great|excellent|perfect|good|love|awesome|wonderful|thank\s*you|thanks|shukran)\b",
    r"\b(ممتاز|رائع|شكرا|جيد\s*جدا|تمام)\b"
]

LEGAL_THREAT_PATTERNS = [
    r"\b(lawyer|attorney|sue|court|police|consumer\s*rights|legal\s*action|ded|economic\s*department)\b",
    r"\b(محامي|محكمة|حماية\s*المستهلك|شكوى\s*قضائية|شرطة|الدائرة\s*الاقتصادية)\b"
]

CHURN_RISK_PATTERNS = [
    r"\b(cancel\s*(my\s*)?order|want\s*(a\s*)?refund|refund\s*my\s*money|return\s*my\s*money|going\s*to\s*(a\s*)?competitor|never\s*buying\s*again)\b",
    r"\b(الغاء\s*الطلب|استرجاع\s*فلوسي|استرداد\s*المبلغ)\b"
]


def extract_delivery_destination(text: str) -> Optional[str]:
    lower = text.lower()
    for p in DESTINATION_OUTSIDE_GCC_PATTERNS:
        if re.search(p, lower):
            return "outside_gcc"
    for p in DESTINATION_GCC_PATTERNS:
        if re.search(p, lower):
            return "GCC"
    for p in DESTINATION_UAE_PATTERNS:
        if re.search(p, lower):
            return "UAE"
    return None


def extract_business_type(text: str) -> Optional[str]:
    lower = text.lower()
    for b_type, patterns in BUSINESS_TYPE_PATTERNS.items():
        if any(re.search(p, lower) for p in patterns):
            return b_type
    return "unknown"


def extract_urgency(text: str) -> str:
    lower = text.lower()
    if any(re.search(p, lower) for p in URGENCY_PATTERNS):
        return "urgent"
    return "normal"


def extract_sentiment(text: str) -> str:
    lower = text.lower()
    if any(re.search(p, lower) for p in SENTIMENT_FRUSTRATED_PATTERNS):
        return "frustrated"
    if any(re.search(p, lower) for p in SENTIMENT_NEGATIVE_PATTERNS):
        return "negative"
    if any(re.search(p, lower) for p in SENTIMENT_POSITIVE_PATTERNS):
        return "positive"
    return "neutral"


def assess_commercial_readiness(intent: str, text: str, qty: Optional[int]) -> str:
    lower = text.lower()
    if intent in ("guardrails", "small_talk", "out_of_scope"):
        return "low"
    if intent in ("quote", "link") or (qty is not None and qty > 1):
        return "high"
    if any(w in lower for w in ["buy", "order", "purchase", "quote", "payment", "bank transfer", "invoice"]):
        return "high"
    if intent in ("price", "stock", "datasheet", "media_yield_cost", "policies", "bundle_catalog"):
        return "medium"
    return "medium"


def extract_risk_flags(text: str) -> NLURiskFlags:
    lower = text.lower()
    is_safe, fail_type, _ = check_pre_guardrails(lower)

    competitor = False
    if any(re.search(r"\b" + re.escape(c) + r"\b", lower) for c in COMPETITOR_BRANDS):
        competitor = True
    if any(re.search(r"\b" + re.escape(m) + r"\b", lower) for m in OTHER_CITIZEN_MODELS):
        competitor = True

    anger = any(re.search(p, lower) for p in SENTIMENT_FRUSTRATED_PATTERNS)
    legal = any(re.search(p, lower) for p in LEGAL_THREAT_PATTERNS)
    churn = any(re.search(p, lower) for p in CHURN_RISK_PATTERNS)
    injection = not is_safe and fail_type == "prompt_injection"

    return NLURiskFlags(
        competitor_mentioned=competitor,
        churn_risk=churn,
        anger_frustration=anger,
        legal_threat=legal,
        prompt_injection=injection
    )


# ---------------------------------------------------------------------------
# Rule-Based Understanding
# ---------------------------------------------------------------------------

def understand_rule_based(read_ctx: ReadContext) -> UnderstandResult:
    text = read_ctx.normalized_text
    routing = classify_intent(text)
    primary_intent = routing["intent"]

    sub_intent = None
    if primary_intent == "policies":
        sub_intent = routing.get("policy_name", "general_policy")
    elif primary_intent == "datasheet":
        if any(w in text.lower() for w in ["speed", "fast", "seconds"]):
            sub_intent = "speed"
        elif any(w in text.lower() for w in ["dimension", "weight", "heavy", "size"]):
            sub_intent = "dimensions"
        elif any(w in text.lower() for w in ["dpi", "resolution"]):
            sub_intent = "resolution"
        else:
            sub_intent = "specs"
    elif primary_intent == "price":
        sub_intent = "single_price"
    elif primary_intent == "quote":
        sub_intent = "formal_quotation"

    dest = extract_delivery_destination(text)
    b_type = extract_business_type(text)
    urgency = extract_urgency(text)
    sentiment = extract_sentiment(text)
    readiness = assess_commercial_readiness(primary_intent, text, read_ctx.resolved_qty)
    risks = extract_risk_flags(text)

    # Budget extraction if mentioned e.g. "budget is 4000 aed"
    budget = None
    budget_m = re.search(r"budget\s+(?:is\s+)?(?:aed\s*)?([0-9]+(?:,[0-9]{3})*)", text.lower())
    if budget_m:
        budget = float(budget_m.group(1).replace(",", ""))

    entities = NLUEntities(
        sku=read_ctx.resolved_sku,
        quantity=read_ctx.resolved_qty,
        delivery_destination=dest,
        business_type=b_type,
        budget=budget
    )

    return UnderstandResult(
        intent=NLUIntent(
            primary_intent=primary_intent,
            sub_intent=sub_intent,
            confidence=1.0
        ),
        commercial_readiness=readiness,
        entities=entities,
        sentiment=sentiment,
        urgency=urgency,
        risk_flags=risks,
        source="rules",
        arbitration_notes=["Evaluated deterministically via rule engine"]
    )


# ---------------------------------------------------------------------------
# LLM NLU Extraction (with Strict JSON Schema & Timeout)
# ---------------------------------------------------------------------------

LLM_NLU_PROMPT = """You are a precise NLU intent and entity classifier for a photo printer sales assistant.
Analyze the user message and extract structured JSON matching the exact schema.

Allowed primary_intent:
["guardrails", "small_talk", "human_demo_reserve", "out_of_scope", "datasheet", "policies", "discount_negotiation", "quote", "stock", "media_yield_cost", "bundle_catalog", "price", "link", "rag"]

Allowed commercial_readiness: ["high", "medium", "low"]
Allowed sentiment: ["positive", "neutral", "negative", "frustrated"]
Allowed urgency: ["urgent", "normal"]
Allowed business_type: ["photobooth", "studio", "freelance", "kiosk", "event", "unknown"]

JSON FORMAT REQUIRED:
{
  "primary_intent": "string",
  "sub_intent": "string or null",
  "commercial_readiness": "string",
  "business_type": "string",
  "delivery_destination": "UAE" | "GCC" | "outside_gcc" | null,
  "sentiment": "string",
  "urgency": "string",
  "risk_flags": {
    "competitor_mentioned": boolean,
    "churn_risk": boolean,
    "anger_frustration": boolean,
    "legal_threat": boolean,
    "prompt_injection": boolean
  }
}
"""


def extract_llm_nlu(user_text: str, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
    """Calls OpenRouter or Ollama with 5.0s timeout. Returns parsed JSON dict or None."""
    if Config.FORCE_EXTRACTIVE_MODE or not circuit_breaker.can_attempt():
        return None

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
                "messages": [
                    {"role": "system", "content": LLM_NLU_PROMPT},
                    {"role": "user", "content": f"Message: {user_text}\nJSON:"}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
                "max_tokens": 180
            }
            res = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if res.status_code == 200:
                circuit_breaker.record_success()
                choices = res.json().get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "").strip()
                    return json.loads(content)
            elif res.status_code >= 500:
                circuit_breaker.record_failure()
        except requests.exceptions.ConnectionError:
            circuit_breaker.record_failure()
        except Exception as e:
            logger.info(f"OpenRouter NLU call failed: {e}")

    # Fallback to Ollama
    url = f"{Config.OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": Config.OLLAMA_CHAT_MODEL,
        "messages": [
            {"role": "system", "content": LLM_NLU_PROMPT},
            {"role": "user", "content": f"Message: {user_text}\nJSON:"}
        ],
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 180
        }
    }

    try:
        t0 = time.time()
        res = requests.post(url, json=payload, timeout=timeout)
        if res.status_code == 200:
            circuit_breaker.record_success()
            content = res.json().get("message", {}).get("content", "").strip()
            return json.loads(content)
        elif res.status_code >= 500:
            circuit_breaker.record_failure()
            return None
        else:
            return None
    except requests.exceptions.ConnectionError:
        circuit_breaker.record_failure()
        return None
    except Exception as e:
        logger.debug(f"LLM NLU extraction skipped/timed out: {e}")
        return None


# ---------------------------------------------------------------------------
# Dual-Track Conservative Disagreement Arbitration
# ---------------------------------------------------------------------------

def arbitrate_understanding(
    rule_res: UnderstandResult,
    llm_dict: Optional[Dict[str, Any]]
) -> UnderstandResult:
    """
    Combines rule-based safety-first result with optional LLM NLU extraction.
    Non-negotiable operational rules take precedence:
      1. Guardrails, discounts, and out-of-scope from rules ALWAYS win.
      2. Any risk flag detected by rules ALWAYS remains True.
      3. Rule-based entity SKU restrictions (e.g. unsupported items) cannot be overridden.
      4. LLM can refine generic classifications (sub_intent, business_type).
    """
    if not llm_dict:
        return rule_res

    notes = list(rule_res.arbitration_notes)
    notes.append("Dual-track comparison evaluated with LLM NLU")

    final_intent = rule_res.intent.primary_intent
    final_sub_intent = rule_res.intent.sub_intent
    llm_intent = llm_dict.get("primary_intent")

    # Hard rules priority arbitration:
    if rule_res.intent.primary_intent in ("guardrails", "discount_negotiation", "out_of_scope"):
        final_intent = rule_res.intent.primary_intent
        notes.append(f"Hard rule override: kept rule-based '{final_intent}' over LLM '{llm_intent}'")
    elif llm_intent and llm_intent != rule_res.intent.primary_intent:
        # If rules classified as general 'rag' or 'price', allow LLM refinement if valid
        if rule_res.intent.primary_intent in ("rag", "price") and llm_intent in (
            "stock", "datasheet", "policies", "quote", "media_yield_cost", "bundle_catalog"
        ):
            final_intent = llm_intent
            notes.append(f"LLM refined generic intent '{rule_res.intent.primary_intent}' -> '{llm_intent}'")
        else:
            notes.append(f"Conservative choice: kept rule intent '{rule_res.intent.primary_intent}' over LLM '{llm_intent}'")

    if llm_dict.get("sub_intent") and not final_sub_intent:
        final_sub_intent = llm_dict.get("sub_intent")

    # Risk flags: Union of rules and LLM (either detecting a risk triggers the risk)
    llm_risks = llm_dict.get("risk_flags", {})
    merged_risks = NLURiskFlags(
        competitor_mentioned=rule_res.risk_flags.competitor_mentioned or bool(llm_risks.get("competitor_mentioned")),
        churn_risk=rule_res.risk_flags.churn_risk or bool(llm_risks.get("churn_risk")),
        anger_frustration=rule_res.risk_flags.anger_frustration or bool(llm_risks.get("anger_frustration")),
        legal_threat=rule_res.risk_flags.legal_threat or bool(llm_risks.get("legal_threat")),
        prompt_injection=rule_res.risk_flags.prompt_injection or bool(llm_risks.get("prompt_injection"))
    )

    # Business type refinement
    b_type = rule_res.entities.business_type
    if b_type == "unknown" and llm_dict.get("business_type") in BUSINESS_TYPE_PATTERNS:
        b_type = llm_dict.get("business_type")
        notes.append(f"LLM identified business_type: '{b_type}'")

    # Destination refinement
    dest = rule_res.entities.delivery_destination
    if not dest and llm_dict.get("delivery_destination") in ("UAE", "GCC", "outside_gcc"):
        dest = llm_dict.get("delivery_destination")

    # Commercial readiness
    readiness = rule_res.commercial_readiness
    if llm_dict.get("commercial_readiness") in ("high", "medium", "low"):
        # If LLM detects higher commercial readiness and intent allows, upgrade
        if llm_dict.get("commercial_readiness") == "high" and readiness == "medium":
            readiness = "high"

    # Urgency: if either says urgent, treat as urgent
    urgency = "urgent" if (rule_res.urgency == "urgent" or llm_dict.get("urgency") == "urgent") else "normal"

    # Sentiment: if either says frustrated, flag as frustrated
    sentiment = rule_res.sentiment
    if llm_dict.get("sentiment") in ("positive", "neutral", "negative", "frustrated"):
        if rule_res.sentiment == "neutral":
            sentiment = llm_dict.get("sentiment")

    return UnderstandResult(
        intent=NLUIntent(
            primary_intent=final_intent,
            sub_intent=final_sub_intent,
            confidence=0.95
        ),
        commercial_readiness=readiness,
        entities=NLUEntities(
            sku=rule_res.entities.sku,
            quantity=rule_res.entities.quantity,
            delivery_destination=dest,
            business_type=b_type,
            budget=rule_res.entities.budget
        ),
        sentiment=sentiment,
        urgency=urgency,
        risk_flags=merged_risks,
        source="arbitrated" if llm_dict else "rules",
        arbitration_notes=notes
    )


def understand_message(read_ctx: ReadContext) -> UnderstandResult:
    """
    Main entry point for Cognitive Step 2: UNDERSTAND.
    Runs rule-based extraction, optionally queries LLM with fast timeout and circuit breaker,
    and performs conservative disagreement arbitration.
    """
    rule_res = understand_rule_based(read_ctx)

    # Cut LLM calls to one per turn when rule confidence is high:
    # Skip slow NLU LLM when rules are confident (price, stock, quotes, specs, policies)
    if rule_res.intent.confidence >= 0.85 and rule_res.intent.primary_intent != "unknown":
        return rule_res

    # Attempt fast LLM extraction only when intent is ambiguous / unknown
    llm_dict = None
    if not Config.FORCE_EXTRACTIVE_MODE and circuit_breaker.can_attempt():
        llm_dict = extract_llm_nlu(read_ctx.normalized_text, timeout=5.0)

    return arbitrate_understanding(rule_res, llm_dict)
