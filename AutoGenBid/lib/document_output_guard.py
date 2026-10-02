"""Validation and normalization for AI-generated bid deliverables."""

from __future__ import annotations

import re
from typing import Callable


class DocumentOutputValidationError(ValueError):
    """Raised when a model response is not a publishable document."""


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def validate_export_name(name: object) -> str:
    """Validate a proposal name before it is used as a Windows filename."""
    value = str(name or "").strip()
    if not value:
        raise ValueError("方案名称不能为空")
    if len(value) > 80:
        raise ValueError("方案名称不能超过 80 个字符")
    if INVALID_FILENAME_CHARS.search(value) or value.endswith((".", " ")):
        raise ValueError("方案名称包含 Windows 文件名不支持的字符")
    if value.upper() in WINDOWS_RESERVED_NAMES:
        raise ValueError("方案名称不能使用 Windows 保留名称")
    return value


def export_basename(name: object) -> str:
    """Return a defensive filename-safe proposal name for final export."""
    value = str(name or "").strip()
    value = INVALID_FILENAME_CHARS.sub("_", value).rstrip(". ")
    return value[:80] or "未命名方案"


class DocumentOutputGuard:
    """Normalizes model text and enforces publishable Markdown contracts."""

    _TITLE_BY_KIND = {
        "proposal": "# 投标技术方案",
        "response_table": "# 技术一对一应答表",
    }
    _META_PATTERNS = (
        re.compile(r"\bnow i have all (?:the )?context\b", re.IGNORECASE),
        re.compile(r"\blet me (?:now )?generate\b", re.IGNORECASE),
        re.compile(r"\bi (?:will|have) (?:now )?(?:generate|created|written)\b", re.IGNORECASE),
        re.compile(r"\bhere (?:is|are) (?:the|a) (?:complete|technical)\b", re.IGNORECASE),
        re.compile(r"\bas an ai\b", re.IGNORECASE),
        re.compile(r"(?:以下是|下面是).{0,24}(?:生成说明|生成过程|技术方案|完整方案|文档)", re.IGNORECASE),
        re.compile(r"(?:我将|我已|现已).{0,24}(?:生成|写入|完成)", re.IGNORECASE),
        re.compile(r"(?:已生成完毕|执行完毕|生成说明|过程报告|上下文已齐全)", re.IGNORECASE),
    )
    _PLACEHOLDER_PATTERN = re.compile(
        r"\[(?:待补充|此处展开|待填写|TODO|TBD|详见[^\]]*)\]", re.IGNORECASE
    )

    @classmethod
    def validator(cls, kind: str) -> Callable[[str], str]:
        return lambda text: cls.clean_and_validate(text, kind)

    @classmethod
    def clean_and_validate(cls, text: str, kind: str) -> str:
        expected_title = cls._TITLE_BY_KIND.get(kind)
        if expected_title is None:
            raise ValueError(f"不支持的文档类型: {kind}")

        cleaned = (text or "").lstrip("\ufeff\n\r \t")
        cleaned = cls._strip_markdown_fences(cleaned)
        title_index = cleaned.find(expected_title)
        if title_index < 0:
            raise DocumentOutputValidationError(f"输出必须以 {expected_title} 开始")
        cleaned = cleaned[title_index:].lstrip()
        cleaned = cls._strip_markdown_fences(cleaned).strip()

        if not cleaned.startswith(expected_title):
            raise DocumentOutputValidationError(f"输出首行必须为 {expected_title}")
        if cls._PLACEHOLDER_PATTERN.search(cleaned):
            raise DocumentOutputValidationError("输出包含占位符")
        if cls._contains_meta_text(cleaned):
            raise DocumentOutputValidationError("输出包含模型过程说明或元描述")

        if kind == "proposal":
            cls._validate_proposal(cleaned)
        else:
            cls._validate_response_table(cleaned)
        return cleaned + "\n"

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        lines = text.splitlines()
        while lines and re.fullmatch(r"\s*```(?:markdown|md|text)?\s*", lines[0], re.IGNORECASE):
            lines.pop(0)
        while lines and re.fullmatch(r"\s*```\s*", lines[-1]):
            lines.pop()
        return "\n".join(lines)

    @classmethod
    def _contains_meta_text(cls, text: str) -> bool:
        return any(pattern.search(text) for pattern in cls._META_PATTERNS)

    @staticmethod
    def _validate_proposal(text: str) -> None:
        if len(text) < 500:
            raise DocumentOutputValidationError("技术方案正文过短")
        if not re.search(r"^##\s+.+", text, re.MULTILINE):
            raise DocumentOutputValidationError("技术方案缺少正式章节标题")

    @staticmethod
    def _validate_response_table(text: str) -> None:
        rows = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
                if cells and not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                    rows.append(cells)
        if len(rows) < 2:
            raise DocumentOutputValidationError("应答表必须包含表头和至少一条应答记录")
        if any(len(row) != 4 for row in rows):
            raise DocumentOutputValidationError("应答表必须为四列表格")
