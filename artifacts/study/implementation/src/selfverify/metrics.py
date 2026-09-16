"""Usage across all Codex conversations, including incomplete stages."""
import json
from pathlib import Path


def collect_session_usage(logs_dir):
    sessions = {}
    for path in sorted((Path(logs_dir) / "sessions").rglob("*.jsonl")):
        session_id = str(path)
        total = None
        peak = None
        for line in path.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            payload = event.get("payload") or {}
            if event.get("type") == "session_meta":
                session_id = payload.get("id", session_id)
            if event.get("type") == "event_msg" and payload.get("type") == "token_count":
                info = payload.get("info") or {}
                if info.get("total_token_usage"):
                    total = info["total_token_usage"]
                value = (info.get("last_token_usage") or {}).get("input_tokens")
                if isinstance(value, int):
                    peak = max(peak or 0, value)
        record = {"path": str(path), "total": total, "peak_context_tokens": peak}
        old = sessions.get(session_id)
        if old is None or (total or {}).get("total_tokens", -1) >= (old["total"] or {}).get("total_tokens", -1):
            sessions[session_id] = record
    recorded = [r for r in sessions.values() if r["total"] is not None]
    totals = {key: sum(r["total"].get(key, 0) or 0 for r in recorded)
              for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")}
    return {"n_sessions": len(sessions), "n_with_usage": len(recorded),
            "complete": bool(sessions) and len(recorded) == len(sessions),
            "totals": totals, "sessions": sessions,
            "peak_context_tokens": max((r["peak_context_tokens"] or 0 for r in recorded), default=0)}
