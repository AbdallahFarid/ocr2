from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Dict, List, Optional


_current_profiler: ContextVar[Optional["Profiler"]] = ContextVar("current_profiler", default=None)


def get_current_profiler() -> Optional["Profiler"]:
    return _current_profiler.get()


def set_current_profiler(prof: Optional["Profiler"]) -> Optional[Token]:
    try:
        return _current_profiler.set(prof)
    except Exception:
        return None


def reset_current_profiler(token: Optional[Token]) -> None:
    try:
        if token is not None:
            _current_profiler.reset(token)
    except Exception:
        pass


class Profiler:
    """Lightweight hierarchical profiler for request/pipeline tracing.

    Enabled when env PROFILE_PIPELINE == "1". Use as:

        prof = Profiler.from_env()
        tok = set_current_profiler(prof)
        with prof.span("stage"):
            ...
        prof.dump_to_file(out_dir, bank, file_id)
        reset_current_profiler(tok)
    """

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = bool(enabled)
        self.t0 = time.perf_counter()
        self.spans: List[Dict[str, Any]] = []
        self._stack: List[int] = []  # indices of spans list representing parents
        self.meta: Dict[str, Any] = {}

    @staticmethod
    def from_env() -> Optional["Profiler"]:
        if os.getenv("PROFILE_PIPELINE", "0") == "1":
            return Profiler(enabled=True)
        return None

    def add_meta(self, **kv: Any) -> None:
        if not self or not self.enabled:
            return
        try:
            self.meta.update({k: v for k, v in kv.items() if v is not None})
        except Exception:
            pass

    @contextmanager
    def span(self, name: str, **attrs: Any):
        if not self or not self.enabled:
            # Disabled: no-op context manager
            yield
            return
        start = time.perf_counter()
        parent = self._stack[-1] if self._stack else None
        rec: Dict[str, Any] = {
            "name": str(name),
            "ts": start - self.t0,
            "dur": None,
            "parent": parent,
        }
        if attrs:
            rec.update({f"attr_{k}": v for k, v in attrs.items()})
        idx = len(self.spans)
        self.spans.append(rec)
        self._stack.append(idx)
        try:
            yield
        finally:
            end = time.perf_counter()
            rec["dur"] = end - start
            # pop only if top of stack is this span
            if self._stack and self._stack[-1] == idx:
                self._stack.pop()

    def event(self, name: str, **attrs: Any) -> None:
        if not self or not self.enabled:
            return
        now = time.perf_counter()
        parent = self._stack[-1] if self._stack else None
        rec: Dict[str, Any] = {
            "name": str(name),
            "ts": now - self.t0,
            "dur": 0.0,
            "parent": parent,
        }
        if attrs:
            rec.update({f"attr_{k}": v for k, v in attrs.items()})
        self.spans.append(rec)

    def dump_to_file(self, out_dir: Optional[str], bank: Optional[str], file_id: Optional[str]) -> None:
        if not self or not self.enabled:
            return
        try:
            root = out_dir or os.getenv("PROFILE_DUMP_DIR", os.path.join("backend", "reports", "profile"))
            if bank and file_id:
                out_dir_f = os.path.join(root, str(bank))
                os.makedirs(out_dir_f, exist_ok=True)
                out_path = os.path.join(out_dir_f, f"{file_id}.json")
            else:
                os.makedirs(root, exist_ok=True)
                out_path = os.path.join(root, f"profile_{int(time.time()*1000)}.json")
            payload = {
                "schema": 1,
                "generated_at": int(time.time()),
                "meta": self.meta,
                "spans": self.spans,
            }
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def log_summary(self) -> None:
        if not self or not self.enabled:
            return
        try:
            # Summarize top-level spans
            tops = [s for s in self.spans if s.get("parent") is None and s.get("dur")]
            tops.sort(key=lambda x: float(x.get("dur") or 0.0), reverse=True)
            summary = {
                "level": "info",
                "msg": "pipeline_profile",
                "meta": self.meta,
                "top": [{"name": t["name"], "dur_ms": int(float(t["dur"]) * 1000)} for t in tops],
            }
            print(json.dumps(summary, ensure_ascii=False))
        except Exception:
            pass
