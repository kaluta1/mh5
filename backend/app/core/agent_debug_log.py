"""Append NDJSON debug lines for agent debug sessions."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

DEFAULT_LOG_PATH = Path(__file__).resolve().parents[2] / ".cursor" / "debug-e34593.log"


def agent_debug_log(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: Optional[dict[str, Any]] = None,
    session_id: str = "e34593",
    log_path: Path = DEFAULT_LOG_PATH,
) -> None:
    # #region agent log
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sessionId": session_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass
    # #endregion
