"""
流水线状态管理器 — JSON 持久化，支持断点续跑。

用法:
    from lib.state_manager import PipelineState
    state = PipelineState(Path(".cache"))
    state.mark_stage_complete(0)
    if state.is_stage_complete(0): ...
"""

from __future__ import annotations

import sys
import json
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class PipelineState:
    """Pipeline 运行状态持久化管理器。"""

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.state_file = self.cache_dir / "pipeline_state.json"
        self._state: Dict[str, Any] = {}

    # ── 加载/保存 ─────────────────────────────────────────

    def load(self) -> Dict[str, Any]:
        """从 JSON 文件加载状态。若不存在则返回初始状态。"""
        if self.state_file.exists():
            try:
                self._state = json.loads(self.state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                self._state = self._initial_state()
        else:
            self._state = self._initial_state()
        return self._state

    def save(self) -> None:
        """保存当前状态到 JSON 文件。"""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(
            json.dumps(self._state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _initial_state() -> Dict[str, Any]:
        return {
            "completed_stages": 0,
            "stage_details": {},
            "sources": [],
            "accompany_bids": {},
            "started_at": None,
            "last_updated": None,
        }

    # ── 阶段管理 ──────────────────────────────────────────

    def get_completed_stages(self) -> int:
        return int(self._state.get("completed_stages", 0))

    def set_completed_stages(self, n: int) -> None:
        self._state["completed_stages"] = n
        self._touch()

    def mark_stage_complete(self, stage_id: int, detail: Optional[Dict] = None) -> None:
        """标记某个阶段为已完成。"""
        self._state["stage_details"][str(stage_id)] = {
            "completed": True,
            "completed_at": datetime.datetime.now().isoformat(),
            "detail": detail or {},
        }
        self._state["completed_stages"] = max(
            self._state.get("completed_stages", 0), stage_id + 1
        )
        self._touch()

    def is_stage_complete(self, stage_id: int) -> bool:
        """检查某个阶段是否已完成。"""
        detail = self._state.get("stage_details", {}).get(str(stage_id), {})
        return bool(detail.get("completed", False))

    def reset_stage(self, stage_id: int) -> None:
        """重置某个阶段（及之后所有阶段）。"""
        keys_to_remove = [
            k for k in self._state.get("stage_details", {})
            if int(k) >= stage_id
        ]
        for k in keys_to_remove:
            del self._state["stage_details"][k]
        self._state["completed_stages"] = min(
            self._state.get("completed_stages", 0), stage_id
        )
        self._touch()

    # ── 参考文件进度 ──────────────────────────────────────────

    def set_bid_status(self, bid_index: int, status: str, output_path: Optional[str] = None) -> None:
        """记录某个参考文件的生成状态。"""
        self._state.setdefault("accompany_bids", {})
        self._state["accompany_bids"][str(bid_index)] = {
            "status": status,
            "output_path": output_path,
            "updated_at": datetime.datetime.now().isoformat(),
        }
        self._touch()

    def get_bid_status(self, bid_index: int) -> Optional[Dict]:
        return self._state.get("accompany_bids", {}).get(str(bid_index))

    def get_all_bid_statuses(self) -> Dict[str, Any]:
        return self._state.get("accompany_bids", {})

    # ── 元信息 ────────────────────────────────────────────

    def add_source(self, path: str) -> None:
        self._state.setdefault("sources", [])
        if path not in self._state["sources"]:
            self._state["sources"].append(path)
            self._touch()

    def set_started(self) -> None:
        if not self._state.get("started_at"):
            self._state["started_at"] = datetime.datetime.now().isoformat()
            self._touch()

    # ── 重置 ──────────────────────────────────────────────

    def reset(self) -> None:
        """完全重置所有状态。"""
        self._state = self._initial_state()
        if self.state_file.exists():
            self.state_file.unlink()

    # ── 内部 ──────────────────────────────────────────────

    def _touch(self) -> None:
        self._state["last_updated"] = datetime.datetime.now().isoformat()

    @property
    def state(self) -> Dict[str, Any]:
        return self._state

    def __repr__(self) -> str:
        return f"PipelineState(stages={self.get_completed_stages()})"
