"""Prompt 构建模块 — v3.0 完整合同版。

将用户上传文档 + source/* + 合同案例/* + 合同表单数据
组装为完整合同生成、质量审查和工作量统计的 LLM Prompt。

用法:
    builder = PromptBuilder(examples_dir, source_dir, profile_texts)
    builder.load_contexts()
    system, user = builder.build_generation_prompt(llm_ctx)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.document.reader import (
    load_contract_examples,
    load_source_context,
    format_examples_for_prompt,
    read_file_auto,
)
from src.llm.prompts import (
    SYSTEM_PROMPT_CONTRACT,
    SYSTEM_PROMPT_REVIEW,
    SYSTEM_PROMPT_STATISTICS,
    CONTRACT_GENERATION_USER,
    CONTRACT_REVIEW_USER,
    CONTRACT_STATISTICS_USER,
)

logger = logging.getLogger(__name__)

# 上下文截断限制
MAX_EXAMPLES_CHARS = 10000
MAX_SOURCE_CHARS = 12000
MAX_UPLOADS_CHARS = 20000
MAX_TOTAL_CHARS = 35000


class PromptBuilder:
    """组装完整的 LLM Prompt，注入全部参考上下文。"""

    def __init__(
        self,
        examples_dir: str,
        source_dir: str = "",
        profile_texts: Optional[List[str]] = None,
        upload_texts: Optional[List[str]] = None,
        template_texts: Optional[List[str]] = None,
    ):
        """
        Args:
            examples_dir: 合同案例/ 目录路径
            source_dir: source/ 目录路径（参考文档）
            profile_texts: session profile/ 文本列表（参考文件）
            upload_texts: session uploads/ 文本列表（核心文件，最高优先级）
            template_texts: session templates/ 文本列表（合同模板参考）
        """
        self.examples_dir = examples_dir
        self.source_dir = source_dir
        self._profile_texts: List[str] = profile_texts or []
        self._upload_texts: List[str] = upload_texts or []
        self._template_texts: List[str] = template_texts or []
        self._examples_text: str = ""
        self._source_text: str = ""
        self._context_docs: str = ""
        self._loaded = False

    def add_upload_text(self, text: str, filename: str = ""):
        """添加一条会话上传文件的文本内容（最高优先级）。

        Args:
            text: 文档的纯文本内容
            filename: 文件名（用于标注来源）
        """
        if text and not text.startswith("["):
            label = f"【用户上传：{filename}】" if filename else "【用户上传】"
            self._upload_texts.append(f"{label}\n{text}")

    def add_profile_text(self, text: str, filename: str = ""):
        """添加一条全局 profile 文件的文本内容（次高优先级）。

        Args:
            text: 文档的纯文本内容
            filename: 文件名
        """
        if text and not text.startswith("["):
            label = f"【参考模板：{filename}】" if filename else "【参考模板】"
            self._profile_texts.append(f"{label}\n{text}")

    def load_contexts(self):
        """加载所有参考文档上下文。"""
        if self._loaded:
            return

        # ── 加载合同案例 ──
        logger.info("加载合同案例...")
        examples = load_contract_examples(self.examples_dir)
        self._examples_text = format_examples_for_prompt(examples)
        if len(self._examples_text) > MAX_EXAMPLES_CHARS:
            self._examples_text = self._examples_text[:MAX_EXAMPLES_CHARS] + "\n...(合同案例已截断)..."
        logger.info(f"已加载 {len(examples)} 个合同案例 ({len(self._examples_text)} 字符)")

        # ── 加载 source/* 目录下所有文件 ──
        if self.source_dir:
            source_dir_path = Path(self.source_dir)
            if source_dir_path.exists():
                source_texts = []
                for f in sorted(source_dir_path.iterdir()):
                    if f.is_file() and not f.name.startswith(".") and not f.name.startswith("~$"):
                        try:
                            text = read_file_auto(str(f), max_chars=MAX_SOURCE_CHARS)
                            if text and not text.startswith("["):
                                labeled = f"【参考文档：{f.name}】\n{text}"
                                source_texts.append(labeled)
                                logger.info(f"已加载 source: {f.name} ({len(text)} 字符)")
                        except Exception as e:
                            logger.warning(f"无法读取 source 文件 {f.name}: {e}")
                self._source_text = "\n\n".join(source_texts)
                if len(self._source_text) > MAX_SOURCE_CHARS * 2:
                    self._source_text = self._source_text[:MAX_SOURCE_CHARS * 2] + "\n...(source文档已截断)..."
            else:
                self._source_text = "（source 目录不存在）"
                logger.warning(f"source 目录不存在: {self.source_dir}")
        else:
            self._source_text = "（未指定 source 目录）"

        # ── 构建综合上下文 ──
        context_parts = []

        # 优先级1：用户上传文件（会话级）
        if self._upload_texts:
            uploads_combined = "\n\n".join(self._upload_texts)
            if len(uploads_combined) > MAX_UPLOADS_CHARS:
                uploads_combined = uploads_combined[:MAX_UPLOADS_CHARS] + "\n...(用户上传文件已截断)..."
            context_parts.append("## 📁 用户上传文档（最高优先级）\n" + uploads_combined)
            logger.info(f"用户上传文档: {len(self._upload_texts)} 个文件 ({len(uploads_combined)} 字符)")

        # 优先级2：全局 profile
        if self._profile_texts:
            profiles_combined = "\n\n".join(self._profile_texts)
            if len(profiles_combined) > MAX_UPLOADS_CHARS // 2:
                profiles_combined = profiles_combined[:MAX_UPLOADS_CHARS // 2] + "\n...(参考模板已截断)..."
            context_parts.append("## 📁 参考模板库\n" + profiles_combined)

        # 优先级3：source 参考文档（招投标书等）
        if self._source_text and self._source_text != "（未指定 source 目录）":
            context_parts.append("## 📁 参考文档（source/）\n" + self._source_text)

        # 优先级4：合同模板参考
        if self._template_texts:
            templates_combined = "\n\n".join(self._template_texts)
            context_parts.append("## 📁 合同模板\n" + templates_combined)

        # 优先级5：合同案例
        if self._examples_text:
            context_parts.append("## 📁 合同案例\n" + self._examples_text)

        self._context_docs = "\n\n---\n\n".join(context_parts) if context_parts else "（无参考文档）"

        # 总长度控制
        if len(self._context_docs) > MAX_TOTAL_CHARS:
            self._context_docs = self._context_docs[:MAX_TOTAL_CHARS] + "\n\n...(上下文超过限制，已截断)..."

        self._loaded = True
        logger.info(f"上下文加载完成: 总计 {len(self._context_docs)} 字符")

    # ── 新 Prompt 构建方法 ──────────────────────────────────

    def build_generation_prompt(self, ctx: Dict[str, str]) -> Tuple[str, str]:
        """构建完整合同生成的 (system_prompt, user_prompt)。

        Args:
            ctx: 合同上下文字典，包含:
                - contract_id, project_name, party_a, party_b
                - signing_place, signing_date, start_date
                - duration, end_date

        Returns:
            (system_prompt, user_prompt) 元组
        """
        if not self._loaded:
            self.load_contexts()

        system_prompt = SYSTEM_PROMPT_CONTRACT.format(
            project_name=ctx.get("project_name", ""),
            context_docs=self._context_docs,
        )

        user_prompt = CONTRACT_GENERATION_USER.format(
            contract_id=ctx.get("contract_id", ""),
            project_name=ctx.get("project_name", ""),
            party_a=ctx.get("party_a", ""),
            party_b=ctx.get("party_b", ""),
            signing_place=ctx.get("signing_place", ""),
            signing_date=ctx.get("signing_date", ""),
            start_date=ctx.get("start_date", ""),
            duration=ctx.get("duration", ""),
            end_date=ctx.get("end_date", ""),
        )

        # 追加表单数据注入块（最高优先级填充源）
        form_data_block = f"""
---
## ⚠️ 我方提供的基本信息（必须优先使用以下实际数据填充合同）

以下信息来自用户填写的合同表单，具有最高优先级。合同中对应用到的位置必须使用这些实际数据，不可使用占位符：

- 合同编号：{ctx.get("contract_id", "")}
- 项目名称：{ctx.get("project_name", "")}
- 甲方（委托方）全称：{ctx.get("party_a", "")}
- 乙方（服务方）全称：{ctx.get("party_b", "")}
- 签订地点：{ctx.get("signing_place", "")}
- 签订日期：{ctx.get("signing_date", "")}
- 服务开始日期：{ctx.get("start_date", "")}
- 服务期限：{ctx.get("duration", "")}
- 服务结束日期：{ctx.get("end_date", "")}

**重要：以上数据是用户实际填写的合同信息，请在合同的封面、正文条款、签章页等所有相关位置直接使用这些实际数据，仅在用户未填写的字段（如地址、联系电话、银行账户等）使用【】占位符。**
"""
        user_prompt += form_data_block
        user_prompt += "\n\n现在，开始执行任务。"

        return system_prompt, user_prompt

    def build_review_prompt(self, contract_text: str, ctx: Dict[str, str]) -> Tuple[str, str]:
        """构建合同审查的 (system_prompt, user_prompt)。

        Args:
            contract_text: 已生成合同的完整 Markdown 文本
            ctx: 合同上下文（contract_id, project_name, party_a, party_b）

        Returns:
            (system_prompt, user_prompt)
        """
        if not self._loaded:
            self.load_contexts()

        system_prompt = SYSTEM_PROMPT_REVIEW.format(
            context_docs=self._context_docs,
        )

        user_prompt = CONTRACT_REVIEW_USER.format(
            contract_id=ctx.get("contract_id", ""),
            project_name=ctx.get("project_name", ""),
            party_a=ctx.get("party_a", ""),
            party_b=ctx.get("party_b", ""),
            contract_text=contract_text,
        )

        return system_prompt, user_prompt

    def build_statistics_prompt(self, contract_text: str, ctx: Dict[str, str]) -> Tuple[str, str]:
        """构建工作量统计的 (system_prompt, user_prompt)。

        Args:
            contract_text: 已生成合同的完整 Markdown 文本
            ctx: 合同上下文

        Returns:
            (system_prompt, user_prompt)
        """
        if not self._loaded:
            self.load_contexts()

        system_prompt = SYSTEM_PROMPT_STATISTICS.format(
            context_docs=self._context_docs,
        )

        user_prompt = CONTRACT_STATISTICS_USER.format(
            contract_id=ctx.get("contract_id", ""),
            project_name=ctx.get("project_name", ""),
            party_a=ctx.get("party_a", ""),
            party_b=ctx.get("party_b", ""),
            contract_text=contract_text,
        )

        return system_prompt, user_prompt

    # ── 向后兼容方法 ────────────────────────────────────────

    def build_system_prompt(self) -> str:
        """[向后兼容] 构建旧版系统 Prompt。"""
        if not self._loaded:
            self.load_contexts()
        return SYSTEM_PROMPT_CONTRACT.format(
            project_name="（合同项目）",
            context_docs=self._context_docs,
        )

    def build_section_prompt(
        self, placeholder_name: str, context: Dict[str, str]
    ) -> Tuple[str, str]:
        """[向后兼容] 为旧版5段式调用构建 prompt。

        注意：新代码应使用 build_generation_prompt() 一次性生成完整合同。
        """
        # 转接到新的完整生成方法，但只在第一次调用时加载
        return self.build_generation_prompt(context)

    def get_section_display_name(self, placeholder_name: str) -> str:
        """[向后兼容] 返回章节显示名。"""
        from src.llm.prompts import SECTION_DISPLAY_NAMES
        return SECTION_DISPLAY_NAMES.get(placeholder_name, placeholder_name)

    def get_generation_order(self) -> List[str]:
        """[向后兼容] 返回生成顺序。"""
        return [
            "aicc_service_content",
            "aicc_searcher_protected_content",
            "aicc_provider_protected_content",
            "aicc_service_fee",
            "aicc_delete_provide_condition",
        ]
