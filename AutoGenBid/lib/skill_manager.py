"""
Skill 管理器 — 加载 SKILL.md 文件，构建 Claude 调用 Prompt。

支持通用型 Skill：自动从 .cache/ 读取上下文数据注入到 Prompt 中。

用法:
    from lib.skill_manager import SkillManager
    mgr = SkillManager(Path("skills"), Path(".cache"))
    prompt = mgr.build_prompt("summarize-bid", context_data="...")
"""

from __future__ import annotations

import sys
import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

class SkillManager:
    """Claude Code Skill 加载与 Prompt 构建器。"""

    def __init__(self, skills_dir: Path, cache_dir: Optional[Path] = None):
        self.skills_dir = Path(skills_dir)
        self.cache_dir = Path(cache_dir) if cache_dir else ROOT / ".cache"
        self._cache: Dict[str, Dict[str, Any]] = {}

    # ── 加载 Skill ──────────────────────────────────────────

    def load_skill(self, name: str) -> Optional[Dict[str, Any]]:
        """
        加载指定 Skill，返回 {meta: {...}, body: "..."}。

        Args:
            name: Skill 目录名（如 "summarize-bid"）

        Returns:
            包含 meta 和 body 的字典，或 None
        """
        if name in self._cache:
            return self._cache[name]

        skill_dir = self.skills_dir / name
        skill_file = skill_dir / "SKILL.md"

        if not skill_file.exists():
            print(f"    [SkillManager] 未找到 Skill: {name} ({skill_file})")
            return None

        content = skill_file.read_text(encoding="utf-8")
        meta, body = self._parse_skill_md(content)

        result = {"meta": meta, "body": body, "path": str(skill_file)}
        self._cache[name] = result
        return result

    def load_skill_body(self, name: str) -> str:
        """仅返回 Skill 的指令体（不含前置元数据）。"""
        skill = self.load_skill(name)
        if skill:
            return skill["body"]
        return ""

    def list_skills(self) -> List[str]:
        """列出所有可用的 Skill 名称。"""
        if not self.skills_dir.exists():
            return []
        return [
            d.name
            for d in self.skills_dir.iterdir()
            if d.is_dir() and (d / "SKILL.md").exists()
        ]

    # ── .cache 自动加载 ─────────────────────────────────────

    def load_cache_file(self, relative_path: str) -> Optional[str]:
        """
        从 .cache/ 目录加载文件内容。

        Args:
            relative_path: 相对于 .cache/ 的路径，如 "01_parsed/full_text.md"

        Returns:
            文件文本内容，或 None
        """
        file_path = self.cache_dir / relative_path
        if not file_path.exists():
            return None
        try:
            return file_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"    [SkillManager] 读取缓存文件失败: {file_path} — {e}")
            return None

    def load_cache_json(self, relative_path: str) -> Optional[Dict[str, Any]]:
        """
        从 .cache/ 目录加载 JSON 文件。

        Args:
            relative_path: 相对于 .cache/ 的路径

        Returns:
            解析后的字典，或 None
        """
        file_path = self.cache_dir / relative_path
        if not file_path.exists():
            return None
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"    [SkillManager] 解析缓存 JSON 失败: {file_path} — {e}")
            return None

    def build_cache_context(self, files: List[str], max_chars: Optional[Dict[str, int]] = None) -> str:
        """
        从多个 .cache 文件构建上下文文本块。

        Args:
            files: 相对于 .cache/ 的文件路径列表
            max_chars: 每个文件的最大字符数限制 {file_path: max_chars}

        Returns:
            拼接后的上下文字符串，每段标注来源文件
        """
        if max_chars is None:
            max_chars = {}

        parts = []
        for rel_path in files:
            content = self.load_cache_file(rel_path)
            if content is None:
                parts.append(f"<!-- [SkillManager] 缓存文件不存在: {rel_path} -->")
                continue

            limit = max_chars.get(rel_path, len(content))
            if len(content) > limit:
                content = content[:limit] + f"\n\n<!-- ... (截断，原文件 {len(content)} 字符) -->"

            parts.append(f"---\n## 📁 .cache/{rel_path}\n")
            parts.append(content)

        return "\n".join(parts) if parts else ""

    # ── 构建 Prompt ─────────────────────────────────────────

    def build_prompt(
        self,
        skill_name: str,
        context: Optional[str] = None,
        extra_instructions: Optional[str] = None,
    ) -> str:
        """
        构建完整的 Claude Prompt = Skill 指令 + 上下文数据。

        Args:
            skill_name: Skill 名称
            context: 注入的上下文数据（如解析后的文档、需求清单等）
            extra_instructions: 额外指令（追加到末尾）

        Returns:
            完整的 prompt 字符串
        """
        skill = self.load_skill(skill_name)
        if not skill:
            raise ValueError(f"Skill '{skill_name}' 不存在")

        parts = [skill["body"]]

        if context:
            parts.append("\n---\n## 上下文数据\n")
            parts.append(context)

        if extra_instructions:
            parts.append("\n---\n## 额外指令\n")
            parts.append(extra_instructions)

        return "\n".join(parts)

    def build_prompt_with_cache(
        self,
        skill_name: str,
        cache_files: List[str],
        extra_context: Optional[str] = None,
        max_chars: Optional[Dict[str, int]] = None,
    ) -> str:
        """
        构建 Prompt：Skill 指令 + 自动从 .cache 加载的上下文 + 额外上下文。

        这是通用型 Skill 的主要入口。

        Args:
            skill_name: Skill 名称
            cache_files: 需要从 .cache 加载的文件列表（相对路径）
            extra_context: 额外的非缓存上下文（如策略配置）
            max_chars: 每个缓存文件的最大字符数

        Returns:
            完整 prompt
        """
        skill = self.load_skill(skill_name)
        if not skill:
            raise ValueError(f"Skill '{skill_name}' 不存在")

        parts = [skill["body"]]

        # 自动加载 .cache 上下文
        cache_context = self.build_cache_context(cache_files, max_chars)
        if cache_context:
            parts.append("\n---\n## 从 .cache 自动加载的上下文数据\n")
            parts.append(cache_context)
            parts.append("\n**注意：以上数据从 .cache/ 自动加载，请优先使用这些数据作为生成依据。**")

        if extra_context:
            parts.append("\n---\n## 额外上下文\n")
            parts.append(extra_context)

        return "\n".join(parts)

    def build_accompany_prompt(
        self,
        strategy_dict: Dict[str, Any],
        requirements_text: str,
        parsed_content: str,
    ) -> str:
        """兼容旧调用；新版本只生成主方案。"""
        return self.build_winning_prompt(strategy_dict, requirements_text, parsed_content)

    def build_solution_prompt(
        self,
        strategy_dict: Dict[str, Any],
        requirements_text: str,
        parsed_content: str,
        task_info: str = "",
    ) -> str:
        """为三方案包中的任一方案组合固定 Skill 与会话配置。"""
        return self.build_winning_prompt(strategy_dict, requirements_text, parsed_content, task_info)

    def build_winning_prompt(
        self,
        strategy_dict: Dict[str, Any],
        requirements_text: str,
        parsed_content: str,
        task_info: str = "",
    ) -> str:
        """
        为独立技术方案构建完整的生成 Prompt。

        支持通用型：自动从 .cache 加载模板分析和格式规格。

        Args:
            strategy_dict: 当前方案策略字典
            requirements_text: 需求清单文本
            parsed_content: 解析后的标书内容
            task_info: 目标任务描述

        Returns:
            完整 prompt
        """
        skill_body = self.load_skill_body("generate-winning")
        if not skill_body:
            raise ValueError("Skill 'generate-winning' 不存在")

        # 自动加载 .cache 上下文
        cache_files = [
            "04_template/template_map.json",
            "04_template/technical_section_map.json",
            "04_template/chapter_number_map.json",
            "05_format/technical_section_map.json",
            "05_format/chapter_number_map.json",
        ]
        cache_context = self.build_cache_context(cache_files)

        strategy_text = self._format_strategy_for_prompt(strategy_dict)

        # 强制输出约束
        output_constraint = """
---
## ⚠️ 最终输出指令（最高优先级，覆盖所有其他指令）

**你必须直接输出完整的投标技术方案正文。以下行为将导致生成失败：**

1. ❌ 禁止输出"文档已生成完毕""以下是对各规则的执行情况核实""共生成XX章节"等总结性文字
2. ❌ 禁止输出过程报告、验证报告、元描述
3. ❌ 禁止将内容写入其他文件或写"详见XX文件""保存在XX路径"
4. ❌ 禁止使用占位符如"[待补充]""[此处展开]"
5. ✅ 必须以 `# 投标技术方案` 开头，直接开始正文
6. ✅ 必须包含全部章节，总字数不少于8000字
7. ✅ 每个章节必须有实质性技术内容
8. ✅ 章节编号必须逐字使用 pipeline 算法生成的 technical_section_map；不得自行生成或猜测编号

**现在开始输出投标技术方案正文（从 # 投标技术方案 开始）：**"""

        return f"""{skill_body}

---
## 从 .cache 自动加载的数据

{cache_context if cache_context else "（部分缓存数据不可用，将使用上下文中的数据）"}

---
## 当前方案配置（唯一的技术栈、团队和工期依据）

{strategy_text}

---
## 目标任务信息

{task_info if task_info else "详见需求清单和标书内容"}

---
## 需求清单（需要完整回应）

{requirements_text[:6000]}

---
## 原标书技术内容（结构参考）

{parsed_content[:5000]}
{output_constraint}"""

    def build_adapt_format_prompt(
        self,
        full_text: str,
        format_section_context: str,
        ref_docx_info: str = "",
        ref_txt_info: str = "",
    ) -> str:
        """
        为格式适配 Skill 构建完整的 Prompt。

        通用型：自动从 .cache 加载模板分析结果。

        Args:
            full_text: 完整的解析后标书文本
            format_section_context: 格式规格章节的上下文文本
            ref_docx_info: 参考 DOCX 的样式信息（可选）
            ref_txt_info: 参考 TXT 的叙述模式信息（可选）

        Returns:
            完整 prompt 字符串
        """
        skill_body = self.load_skill_body("adapt-format")
        if not skill_body:
            raise ValueError("Skill 'adapt-format' 不存在")

        # 自动加载 .cache 上下文
        cache_files = [
            "04_template/template_map.json",
        ]
        cache_context = self.build_cache_context(cache_files)

        return f"""{skill_body}

---
## 从 .cache 自动加载的数据

{cache_context if cache_context else "（模板结构分析尚未完成）"}

---
## 标书格式规格章节

{format_section_context[:8000]}

---
## 参考 DOCX 样式信息

{ref_docx_info if ref_docx_info else "（未提供参考 DOCX，将使用默认中文投标文档样式）"}

---
## 参考 TXT 叙述模式

{ref_txt_info if ref_txt_info else "（未提供参考 TXT，将使用默认叙述模式）"}"""

    def build_response_table_prompt(
        self,
        technical_draft_text: str,
        project_name: str = "",
        package_id: str = "",
        proposal_metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        为应答表生成构建完整的 Prompt。

        通用型：自动从 .cache 加载需求清单和模板分析。

        Args:
            technical_draft_text: 已生成的技术方案全文（Markdown）
            project_name: 项目名称
            package_id: 包号

        Returns:
            完整 prompt
        """
        skill_body = self.load_skill_body("generate-response-table")
        if not skill_body:
            raise ValueError("Skill 'generate-response-table' 不存在")

        # 自动加载 .cache 上下文
        cache_files = [
            "03_requirements/requirements.json",
            "04_template/template_map.json",
            "04_template/technical_section_map.json",
            "05_format/chapter_number_map.json",
        ]
        cache_context = self.build_cache_context(cache_files)

        output_constraint = """
---
## ⚠️ 最终输出指令（最高优先级）

**你必须直接输出完整的技术一对一应答表。以下行为将导致生成失败：**

1. ❌ 禁止输出总结、摘要或元描述
2. ❌ 禁止输出过程报告
3. ❌ 禁止遗漏任何子需求
4. ❌ 禁止使用占位符
5. ❌ 禁止提及"偏离"（无偏离/正偏离/负偏离等字眼）
6. ❌ 禁止使用"完全满足""基本满足"等评价性措辞
7. ❌ 禁止使用超链接格式
8. ✅ 必须以 `# 技术一对一应答表` 开头
9. ✅ 必须覆盖从 requirements.json 提取的所有 FUNC/TECH 子需求
10. ✅ 功能参数要求列必须详细描述我方技术方案（100-300字/条）
11. ✅ 应答章节列仅填写章节位置（格式：对应技术方案章节：XX.XX.XX 章节名称）
12. ✅ 模块结构从 requirements.json 动态提取，不使用硬编码的模块列表

**现在开始输出技术一对一应答表：**"""

        proposal_metadata = proposal_metadata or {}
        proposal_lines = [
            f"方案名称：{proposal_metadata.get('name', '当前技术方案')}",
            f"方案 ID：{proposal_metadata.get('id', '')}",
            f"技术栈 ID：{proposal_metadata.get('tech_stack_id', '')}",
            f"团队模板 ID：{proposal_metadata.get('team_profile_id', '')}",
            f"交付工期：{proposal_metadata.get('delivery_days', '')} 天",
        ]
        tech_stack = proposal_metadata.get("tech_stack", {})
        if isinstance(tech_stack, dict):
            for row in tech_stack.get("rows", []):
                if isinstance(row, dict) and row.get("label"):
                    proposal_lines.append(f"技术栈：{row['label']} = {row.get('value', '')}")
        team_profile = proposal_metadata.get("team_profile", {})
        if isinstance(team_profile, dict):
            for role in team_profile.get("roles", []):
                if isinstance(role, dict) and role.get("role"):
                    proposal_lines.append(
                        f"团队角色：{role['role']} {role.get('count', 0)} 人，{role.get('focus', '')}"
                    )
        proposal_context = "\n".join(proposal_lines)

        return f"""{skill_body}

---
## 从 .cache 自动加载的数据

{cache_context if cache_context else "（部分缓存数据不可用）"}

---
## 技术方案全文

{technical_draft_text[:15000]}

---
## 当前方案元数据（仅可对应此方案，不得混用其他方案信息）

{proposal_context}

---
## 项目信息

项目名称：{project_name or '详见招标文件'}
包号：{package_id or '详见招标文件'}
{output_constraint}"""

    # ── 内部方法 ────────────────────────────────────────────

    @staticmethod
    def _parse_skill_md(content: str) -> tuple:
        """
        解析 SKILL.md：分离 YAML 前置元数据和 Markdown 指令体。

        Returns:
            (meta_dict, body_text)
        """
        # 查找 YAML 前置元数据
        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if frontmatter_match:
            yaml_text = frontmatter_match.group(1)
            body = content[frontmatter_match.end():].strip()
            try:
                meta = yaml.safe_load(yaml_text) or {}
            except yaml.YAMLError:
                meta = {}
        else:
            meta = {}
            body = content.strip()

        return meta, body

    @staticmethod
    def _format_strategy_for_prompt(strategy: Dict[str, Any]) -> str:
        """将策略字典格式化为可供 Claude 理解的文本。"""
        lines = []

        lines.append(f"策略ID: {strategy.get('strategy_id', 'N/A')}")
        lines.append(f"策略名称: {strategy.get('strategy_name', 'N/A')}")
        lines.append(f"需求满足率: {strategy.get('satisfaction_rate', 'N/A')}")
        if strategy.get("strategy_prompt"):
            lines.append("方案写作规则:")
            for rule in str(strategy.get("strategy_prompt")).splitlines():
                if rule.strip():
                    lines.append(f"- {rule.strip()}")
        lines.append("")

        # 技术栈
        ts = strategy.get("tech_stack", {})
        if ts:
            lines.append("## 技术栈限定（来自 pipeline_config.yaml）")
            if ts.get("name"):
                lines.append(f"- 技术栈名称: {ts.get('name')}")
            if ts.get("summary"):
                lines.append(f"- 技术栈说明: {ts.get('summary')}")
            rows = ts.get("rows", [])
            if isinstance(rows, list) and rows:
                for row in rows:
                    if isinstance(row, dict):
                        lines.append(f"- {row.get('label') or row.get('key')}: {row.get('value', '')}")
            else:
                for key, label in [
                    ("backend_lang", "后端语言"),
                    ("backend_framework", "后端框架"),
                    ("web_server", "Web服务器"),
                    ("orm", "ORM/迁移"),
                    ("database", "数据库"),
                    ("build_tool", "构建工具"),
                    ("data_processing", "数据处理"),
                    ("ai_ml", "AI/ML"),
                    ("frontend", "前端"),
                    ("deployment", "部署"),
                    ("containerization", "容器化"),
                ]:
                    if ts.get(key):
                        lines.append(f"- {label}: {ts.get(key)}")
            lines.append("")

        # 团队
        tp = strategy.get("team_plan", {})
        if tp:
            lines.append("## 团队配置")
            lines.append(f"总人数: {tp.get('total', 'N/A')}")
            for role in tp.get("roles", []):
                notes = role.get("focus") or role.get("notes") or ""
                suffix = f" - {notes}" if notes else ""
                lines.append(f"- {role.get('role', '')}: {role.get('count', 0)}人{suffix}")
            lines.append("")

        # 时间线
        tl = strategy.get("timeline", {})
        if tl:
            lines.append("## 时间线")
            if tl.get("total_days"):
                lines.append(f"总周期: {tl.get('total_days')} 天")
            else:
                lines.append(f"总周期: {tl.get('total_months', 'N/A')} 个月")
            for phase in tl.get("phases", []):
                span = phase.get("days") or phase.get("months") or [0, 0]
                unit = "天" if phase.get("days") else "个月"
                lines.append(f"- {phase.get('phase', '')}: 第{span[0]}-{span[1]}{unit}")
            if tl.get("notes"):
                lines.append(f"备注: {tl['notes']}")
            lines.append("")

        # 需求劣化 — 只输出摘要统计（避免prompt过长导致模型走捷径）
        reqs = strategy.get("requirement_degradations", [])
        if reqs:
            # 统计各类型数量
            full_count = sum(1 for r in reqs if r.get("degradation_type") == "full_satisfy")
            partial_count = sum(1 for r in reqs if r.get("degradation_type") == "partial")
            omit_count = sum(1 for r in reqs if r.get("degradation_type") == "omit")
            lines.append("## 需求劣化清单（摘要统计）")
            lines.append(f"总需求数: {len(reqs)}")
            lines.append(f"- 完全满足: {full_count}条 → 正常回应，写'完全满足'，扩展技术优势")
            lines.append(f"- 部分满足: {partial_count}条 → 写'基本满足'或'部分满足'，弱化技术能力或仅描述基础功能")
            lines.append(f"- 省略: {omit_count}条 → 段落极短（1-2句）或写'将在后续开发中调整'")
            # 仅列出省略和部分满足的前10条作为示例
            degraded_examples = [r for r in reqs if r.get("degradation_type") in ("partial", "omit")][:10]
            if degraded_examples:
                lines.append("劣化需求示例（前10条）:")
                for r in degraded_examples:
                    dtype = r.get("degradation_type", "partial")
                    label = {"partial": "部分满足", "omit": "省略"}
                    lines.append(f"  - {r.get('req_id', '')}: {label.get(dtype, dtype)} — {r.get('degraded_response_hint', '')}")
                if partial_count + omit_count > 10:
                    lines.append(f"  ... 其余 {partial_count + omit_count - 10} 条按同等方式处理")
            lines.append("**注意：所有完全满足的需求需在正文中全面回应，不需要在prompt中逐条列出。**")
            lines.append("")

        # 删除清单
        dels = strategy.get("content_deletion_sections", [])
        if dels:
            lines.append("## 内容删除/简化清单")
            for d in dels:
                lines.append(f"- {d}")
            lines.append("")

        # 写作规则
        rules = strategy.get("writing_rules", [])
        if rules:
            lines.append("## 写作规则")
            for r in rules:
                lines.append(f"- {r}")
            lines.append("")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"SkillManager({len(self.list_skills())} skills, cache={self.cache_dir})"
