import time
import threading
from datetime import datetime, date
from typing import Dict, Any, Optional
from app.config import Config
from app.tools.pricing import load_catalog

# In-memory Prometheus metric accumulators (thread-safe)
_lock = threading.Lock()

_request_counts: Dict[str, int] = {}
_guardrail_blocks: Dict[str, int] = {}
_handoffs_count: Dict[str, int] = {}
_quotes_count: int = 0
_latencies: list = []


def record_request(channel: str = "web", status: str = "200", duration_s: float = 0.0) -> None:
    key = f'channel="{channel}",status="{status}"'
    with _lock:
        _request_counts[key] = _request_counts.get(key, 0) + 1
        _latencies.append(duration_s)
        if len(_latencies) > 1000:
            _latencies.pop(0)


def record_guardrail_block(block_type: str = "pre_guardrail") -> None:
    with _lock:
        _guardrail_blocks[block_type] = _guardrail_blocks.get(block_type, 0) + 1


def record_handoff(reason: str = "unspecified") -> None:
    # Normalize reason tag
    clean_reason = reason[:40].replace('"', '').replace('\n', ' ')
    with _lock:
        _handoffs_count[clean_reason] = _handoffs_count.get(clean_reason, 0) + 1


def record_quote_created() -> None:
    global _quotes_count
    with _lock:
        _quotes_count += 1


def get_price_staleness_days() -> int:
    try:
        catalog = load_catalog()
        as_of_str = catalog.get("as_of", "")
        if as_of_str:
            as_of_date = datetime.strptime(as_of_str, "%Y-%m-%d").date()
            return (date.today() - as_of_date).days
    except Exception:
        pass
    return 0


def get_ollama_status() -> int:
    """Returns 1 if Ollama circuit is closed (healthy), 0 if open or unreachable."""
    try:
        from app.agent.llm import _circuit_open, _circuit_opened_at
        if _circuit_open:
            return 0
        return 1
    except Exception:
        return 1


def generate_prometheus_metrics() -> str:
    """Generates standard Prometheus text exposition format."""
    lines = [
        "# HELP sales_ai_requests_total Total number of chat/API requests processed",
        "# TYPE sales_ai_requests_total counter"
    ]
    with _lock:
        if not _request_counts:
            lines.append('sales_ai_requests_total{channel="web",status="200"} 0')
        else:
            for labels, count in _request_counts.items():
                lines.append(f'sales_ai_requests_total{{{labels}}} {count}')

        lines.extend([
            "# HELP sales_ai_guardrail_blocks_total Total guardrail triggers and blocked requests",
            "# TYPE sales_ai_guardrail_blocks_total counter"
        ])
        if not _guardrail_blocks:
            lines.append('sales_ai_guardrail_blocks_total{type="pre_guardrail"} 0')
        else:
            for btype, count in _guardrail_blocks.items():
                lines.append(f'sales_ai_guardrail_blocks_total{{type="{btype}"}} {count}')

        lines.extend([
            "# HELP sales_ai_handoffs_total Total human sales specialist handoffs initiated",
            "# TYPE sales_ai_handoffs_total counter"
        ])
        if not _handoffs_count:
            lines.append('sales_ai_handoffs_total{reason="unspecified"} 0')
        else:
            for reason, count in _handoffs_count.items():
                lines.append(f'sales_ai_handoffs_total{{reason="{reason}"}} {count}')

        lines.extend([
            "# HELP sales_ai_quotes_generated_total Total formal price quotations generated",
            "# TYPE sales_ai_quotes_generated_total counter",
            f"sales_ai_quotes_generated_total {_quotes_count}"
        ])

        # Latency summary
        lines.extend([
            "# HELP sales_ai_request_latency_seconds Request latency in seconds",
            "# TYPE sales_ai_request_latency_seconds summary"
        ])
        if _latencies:
            sorted_lat = sorted(_latencies)
            count = len(sorted_lat)
            p50 = sorted_lat[int(count * 0.5)]
            p95 = sorted_lat[min(int(count * 0.95), count - 1)]
            sum_lat = sum(sorted_lat)
            lines.append(f'sales_ai_request_latency_seconds{{quantile="0.5"}} {p50:.4f}')
            lines.append(f'sales_ai_request_latency_seconds{{quantile="0.95"}} {p95:.4f}')
            lines.append(f'sales_ai_request_latency_seconds_sum {sum_lat:.4f}')
            lines.append(f'sales_ai_request_latency_seconds_count {count}')
        else:
            lines.append('sales_ai_request_latency_seconds{quantile="0.5"} 0.0')
            lines.append('sales_ai_request_latency_seconds{quantile="0.95"} 0.0')
            lines.append('sales_ai_request_latency_seconds_sum 0.0')
            lines.append('sales_ai_request_latency_seconds_count 0')

    stale_days = get_price_staleness_days()
    lines.extend([
        "# HELP sales_ai_price_stale_days Days elapsed since catalog price as_of date",
        "# TYPE sales_ai_price_stale_days gauge",
        f"sales_ai_price_stale_days {stale_days}"
    ])

    ollama_stat = get_ollama_status()
    lines.extend([
        "# HELP sales_ai_ollama_status Ollama LLM daemon connectivity status (1=up, 0=down)",
        "# TYPE sales_ai_ollama_status gauge",
        f"sales_ai_ollama_status {ollama_stat}"
    ])

    return "\n".join(lines) + "\n"
