"""
Skill 管理器 — 加载 SKILL.md 文件，构建 Claude/LLM 调用 Prompt。

对标 标书网页 lib/skill_manager.py 的设计模式，
支持从 .cache/ 自动加载上下文数据注入到 Prompt 中。

用法:
    from lib.skill_manager import SkillManager
    mgr = SkillManager(Path("skills"), Path(".cache"))
    prompt = mgr.build_prompt("contract-all", context="...")
"""

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class SkillManager:
    """合同生成 Skill 加载与 Prompt 构建器。

    解析 skills/{name}/SKILL.md 文件（YAML frontmatter + Markdown body），
    自动从 .cache/ 加载上下文数据并注入到 Prompt 中。
    """

    def __init__(self, skills_dir: Path, cache_dir: Optional[Path] = None):
        """
        Args:
            skills_dir: skills/ 目录的绝对路径
            cache_dir: .cache/ 目录的绝对路径（用于自动加载上下文数据）
        """
        self.skills_dir = Path(skills_dir)
        self.cache_dir = Path(cache_dir) if cache_dir else self.skills_dir.parent / ".cache"
        self._cache: Dict[str, Dict[str, Any]] = {}

    # ── 加载 Skill ──────────────────────────────────────────

    def load_skill(self, name: str) -> Optional[Dict[str, Any]]:
        """加载指定 Skill，返回 {meta: {...}, body: "...", path: "..."}。

        Args:
            name: Skill 目录名（如 "contract-all"）

        Returns:
            包含 meta、body、path 的字典，或 None（Skill 不存在）
        """
        if name in self._cache:
            return self._cache[name]

        skill_dir = self.skills_dir / name
        skill_file = skill_dir / "SKILL.md"

        if not skill_file.exists():
            # 回退：尝试旧的平铺 .md 文件（向后兼容）
            legacy_file = self.skills_dir / f"{name}.md"
            if legacy_file.exists():
                skill_file = legacy_file

        if not skill_file.exists():
            return None

        content = skill_file.read_text(encoding="utf-8")
        meta, body = self._parse_skill_md(content)

        result = {"meta": meta, "body": body, "path": str(skill_file)}
        self._cache[name] = result
        return result

    def load_skill_body(self, name: str) -> str:
        """仅返回 Skill 的指令体（不含 YAML 前置元数据）。

        Args:
            name: Skill 目录名

        Returns:
            Markdown 格式的指令体文本，若 Skill 不存在返回空字符串
        """
        skill = self.load_skill(name)
        if skill:
            return skill["body"]
        return ""

    def load_skill_meta(self, name: str) -> Dict[str, Any]:
        """仅返回 Skill 的元数据。

        Args:
            name: Skill 目录名

        Returns:
            包含 name, description, version 等字段的字典
        """
        skill = self.load_skill(name)
        if skill:
            return skill["meta"]
        return {}

    def list_skills(self) -> List[str]:
        """列出所有可用的 Skill 名称。

        同时支持新格式（skills/{name}/SKILL.md）和旧格式（skills/{name}.md）。

        Returns:
            Skill 名称列表
        """
        if not self.skills_dir.exists():
            return []

        names = set()

        # 新格式：子目录
        for d in self.skills_dir.iterdir():
            if d.is_dir() and (d / "SKILL.md").exists():
                names.add(d.name)

        # 旧格式：平铺 .md（向后兼容）
        for f in self.skills_dir.glob("*.md"):
            names.add(f.stem)

        return sorted(names)

    # ── .cache 自动加载 ─────────────────────────────────────

    def load_cache_file(self, relative_path: str) -> Optional[str]:
        """从 .cache/ 目录加载文件内容。

        Args:
            relative_path: 相对于 .cache/ 的路径，如 "sessions/{id}/contract_config.json"

        Returns:
            文件文本内容，或 None
        """
        file_path = self.cache_dir / relative_path
        if not file_path.exists():
            return None
        try:
            return file_path.read_text(encoding="utf-8")
        except Exception as e:
            return None

    def load_cache_json(self, relative_path: str) -> Optional[Dict[str, Any]]:
        """从 .cache/ 目录加载 JSON 文件。

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
            return None

    def build_cache_context(self, files: List[str], max_chars: Optional[Dict[str, int]] = None) -> str:
        """从多个 .cache 文件构建上下文文本块。

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
        """构建完整的 LLM Prompt = Skill 指令 + 上下文数据 + 额外指令。

        Args:
            skill_name: Skill 名称
            context: 注入的上下文数据（如合同配置、参考文档等）
            extra_instructions: 额外指令（追加到末尾）

        Returns:
            完整的 prompt 字符串

        Raises:
            ValueError: Skill 不存在
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
        """构建 Prompt：Skill 指令 + 自动从 .cache 加载的上下文 + 额外上下文。

        这是通用型 Skill 的主要入口。

        Args:
            skill_name: Skill 名称
            cache_files: 需要从 .cache 加载的文件列表（相对路径）
            extra_context: 额外的非缓存上下文（如用户输入数据）
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

    def build_contract_generation_prompt(
        self,
        form_data: Dict[str, Any],
        examples_text: str = "",
        source_text: str = "",
    ) -> str:
        """为完整合同生成构建 Prompt。

        自动从 .cache 加载合同案例和 source 文档上下文。

        Args:
            form_data: 合同表单数据字典
            examples_text: 已加载的合同案例文本（可选，若不传则从 .cache 读取）
            source_text: 已加载的 source 文档文本（可选）

        Returns:
            完整 prompt 字符串
        """
        skill_body = self.load_skill_body("contract-all")
        if not skill_body:
            raise ValueError("Skill 'contract-all' 不存在")

        # 自动加载 .cache 上下文
        cache_files = [
            "01_config/contract_config.json",
            "02_examples/example_01.txt",
            "02_examples/example_02.txt",
            "02_examples/example_03.txt",
            "03_source/source_context.txt",
        ]
        cache_context = self.build_cache_context(cache_files)

        # 构建表单数据文本
        form_text = f"""```json
{json.dumps(form_data, ensure_ascii=False, indent=2)}
```"""

        # 如果调用方提供了文本但缓存中没有，则使用调用方提供的
        extra = []
        if examples_text and not cache_context:
            extra.append(f"## 合同案例\n\n{examples_text[:5000]}")
        if source_text and not cache_context:
            extra.append(f"## 参考文档\n\n{source_text[:5000]}")

        context_parts = [
            "## 合同表单数据\n",
            form_text,
        ]
        if extra:
            context_parts.append("\n---\n")
            context_parts.extend(extra)

        output_constraint = """
---
## ⚠️ 最终输出指令（最高优先级，覆盖所有其他指令）

**你必须直接输出完整的合同正文。以下行为将导致生成失败：**

1. ❌ 禁止输出「合同已生成」「以下是对各条款的说明」等过程报告或元描述
2. ❌ 禁止输出文件路径列表或文件操作报告
3. ❌ 禁止使用非标准占位符（仅允许 `【】` 格式）
4. ❌ 禁止输出空章节或仅有标题无内容的章节
5. ❌ 禁止在不同章节使用不一致的数据
6. ✅ 必须以 `# {项目名称}` 开头，直接开始合同正文
7. ✅ 必须包含全部 13 个章节 + 签章页，每章有实质性内容
8. ✅ 必须满足最低字数要求（总计 ≥ 3000 字）
9. ✅ 必须将所有待填写数据使用 `【】` 占位符标注

**现在开始输出合同正文（从 `# {项目名称}` 开始）：**"""

        return f"""{skill_body}

---
## 从 .cache 自动加载的数据

{cache_context if cache_context else "（部分缓存数据不可用，将使用上下文中的数据）"}

---
{chr(10).join(context_parts)}
{output_constraint}"""

    def build_section_prompt(
        self,
        section_skill_name: str,
        form_data: Dict[str, Any],
        examples_text: str = "",
        source_text: str = "",
    ) -> str:
        """为单个合同章节构建 Prompt。

        Args:
            section_skill_name: 章节 Skill 名称（如 "contract-service-content"）
            form_data: 合同表单数据
            examples_text: 合同案例文本
            source_text: source 文档文本

        Returns:
            完整 prompt 字符串
        """
        skill_body = self.load_skill_body(section_skill_name)
        if not skill_body:
            raise ValueError(f"Skill '{section_skill_name}' 不存在")

        # 构建简洁的上下文注入
        context_parts = []

        # 项目信息
        project = form_data.get("project_name", "（未指定）")
        party_a = form_data.get("party_a", "甲方")
        party_b = form_data.get("party_b", "乙方")
        duration_y = form_data.get("duration_years", 0)
        duration_m = form_data.get("duration_months", 0)
        duration_d = form_data.get("duration_days", 0)
        duration_parts = []
        if duration_y:
            duration_parts.append(f"{duration_y}年")
        if duration_m:
            duration_parts.append(f"{duration_m}个月")
        if duration_d:
            duration_parts.append(f"{duration_d}日")
        duration = "".join(duration_parts) if duration_parts else "（未指定）"

        context_parts.append(
            f"项目名称：{project}\n"
            f"甲方：{party_a}\n"
            f"乙方：{party_b}\n"
            f"服务期限：{duration}"
        )

        # 参考文档（限量）
        if examples_text:
            context_parts.append(f"\n## 合同案例参考\n{examples_text[:3000]}")
        if source_text:
            context_parts.append(f"\n## 项目参考文档\n{source_text[:3000]}")

        return f"""{skill_body}

---
## 项目信息

{chr(10).join(context_parts)}

---
**请直接输出条款正文，不要输出任何解释或标题。**"""

    # ── 内部方法 ────────────────────────────────────────────

    @staticmethod
    def _parse_skill_md(content: str) -> tuple:
        """解析 SKILL.md：分离 YAML 前置元数据和 Markdown 指令体。

        Args:
            content: SKILL.md 文件的完整文本内容

        Returns:
            (meta_dict, body_text) 元组
        """
        # 查找 YAML 前置元数据（--- 包裹的 YAML 块）
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

    def __repr__(self) -> str:
        return f"SkillManager({len(self.list_skills())} skills, cache={self.cache_dir})"
