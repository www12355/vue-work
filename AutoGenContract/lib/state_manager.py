"""
流水线状态管理器 — JSON 持久化，支持断点续跑。

对标 标书网页 lib/state_manager.py 的设计模式，
适配合同生成 4 阶段流水线。

用法:
    from lib.state_manager import PipelineState
    state = PipelineState(cache_dir)
    state.mark_stage_complete(0)
    if state.is_stage_complete(0): ...
"""

from __future__ import annotations

import json
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class PipelineState:
    """合同生成流水线运行状态持久化管理器。

    将流水线进度保存为 JSON 文件，支持：
    - 阶段完成标记
    - 断点续跑（跳过已完成阶段）
    - 从任意阶段重置
    - 完整的元信息记录
    """

    def __init__(self, cache_dir: Path):
        """
        Args:
            cache_dir: .cache/ 目录的路径（session 级别或全局级别）
        """
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
        """返回流水线初始状态。"""
        return {
            "completed_stages": 0,
            "stage_details": {},
            "sources": [],
            "llm_sections": {},
            "started_at": None,
            "last_updated": None,
        }

    # ── 阶段管理 ──────────────────────────────────────────

    def get_completed_stages(self) -> int:
        """获取已完成的阶段数。"""
        return int(self._state.get("completed_stages", 0))

    def set_completed_stages(self, n: int) -> None:
        """设置已完成的阶段数。"""
        self._state["completed_stages"] = n
        self._touch()

    def mark_stage_complete(self, stage_id: int, detail: Optional[Dict] = None) -> None:
        """标记某个阶段为已完成。

        Args:
            stage_id: 阶段编号 (0-3)
            detail: 可选的阶段详情字典（如生成字符数、文件名等）
        """
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
        """检查某个阶段是否已完成。

        Args:
            stage_id: 阶段编号 (0-3)

        Returns:
            True 表示该阶段已完成，可跳过
        """
        detail = self._state.get("stage_details", {}).get(str(stage_id), {})
        return bool(detail.get("completed", False))

    def get_stage_detail(self, stage_id: int) -> Dict[str, Any]:
        """获取某个阶段的详情。

        Args:
            stage_id: 阶段编号

        Returns:
            阶段详情字典，或空字典
        """
        return self._state.get("stage_details", {}).get(str(stage_id), {}).get("detail", {})

    def reset_stage(self, stage_id: int) -> None:
        """重置某个阶段及之后所有阶段。

        Args:
            stage_id: 从此阶段开始重置（含此阶段）
        """
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

    # ── LLM 章节进度 ──────────────────────────────────────

    def set_section_status(self, section_key: str, status: str, chars: int = 0) -> None:
        """记录某个 LLM 生成章节的状态。

        Args:
            section_key: 章节键（如 'aicc_service_content'）
            status: 'pending' | 'running' | 'completed' | 'failed'
            chars: 生成的字符数
        """
        self._state.setdefault("llm_sections", {})
        self._state["llm_sections"][section_key] = {
            "status": status,
            "chars": chars,
            "updated_at": datetime.datetime.now().isoformat(),
        }
        self._touch()

    def get_section_status(self, section_key: str) -> Optional[Dict]:
        """获取某个章节的生成状态。"""
        return self._state.get("llm_sections", {}).get(section_key)

    # ── 元信息 ────────────────────────────────────────────

    def add_source(self, path: str) -> None:
        """记录已加载的源文件路径。"""
        self._state.setdefault("sources", [])
        if path not in self._state["sources"]:
            self._state["sources"].append(path)
            self._touch()

    def set_started(self) -> None:
        """标记流水线已启动（仅在首次启动时设置 started_at）。"""
        if not self._state.get("started_at"):
            self._state["started_at"] = datetime.datetime.now().isoformat()
            self._touch()

    def set_output_file(self, filename: str) -> None:
        """记录最终输出文件名。"""
        self._state["output_file"] = filename
        self._touch()

    # ── 重置 ──────────────────────────────────────────────

    def reset(self) -> None:
        """完全重置所有状态，删除状态文件。"""
        self._state = self._initial_state()
        if self.state_file.exists():
            self.state_file.unlink()

    # ── 内部 ──────────────────────────────────────────────

    def _touch(self) -> None:
        """更新时间戳。"""
        self._state["last_updated"] = datetime.datetime.now().isoformat()

    @property
    def state(self) -> Dict[str, Any]:
        """返回完整的内部状态字典（只读引用）。"""
        return self._state

    def __repr__(self) -> str:
        return f"PipelineState(stages={self.get_completed_stages()})"
