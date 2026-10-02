#!/usr/bin/env python
"""
extract_format_section.py — 从标书文件中按分节符/分页符切分，用 DeepSeek 判断
投标文件格式章节，提取后重建为独立的 templates.docx。

用法:
    python extract_format_section.py                      # 使用默认 config.yaml
    python extract_format_section.py --config mycfg.yaml  # 指定配置文件
    python extract_format_section.py --dry-run            # 仅分段和展示，不调用 API

流程:
    1. 打开 标书文件.docx
    2. 找到所有分页符和分节符
    3. 将文档切分为段落块（chunks）
    4. 为每个块构建签名（前 N 段文字）
    5. 调用 DeepSeek API 判断每个块是否属于投标文件格式
    6. 提取中标块 → 重建 DOCX → 保存到 templates/templates.docx

依赖:
    python-docx, PyYAML, openai>=1.0
"""

from __future__ import annotations

import os
import sys
import json
import re
import copy
import argparse
import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import OrderedDict

import yaml
from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn, nsmap
from docx.oxml import OxmlElement


# ═══════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════

ROOT = Path(__file__).resolve().parent

DEFAULT_CONFIG = {
    "deepseek": {
        "api_key": "",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-pro",
        "temperature": 0.1,
        "max_tokens": 500,
        "timeout": 30,
    },
    "paths": {
        "input_docx": "标书文件.docx",
        "output_dir": "templates",
        "output_docx": "templates.docx",
    },
}


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """加载 YAML 配置，与默认值合并。"""
    if config_path is None:
        config_path = ROOT / "config.yaml"

    config = copy.deepcopy(DEFAULT_CONFIG)

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
        _deep_merge(config, user_config)
    else:
        print(f"[WARN] 配置文件不存在: {config_path}")
        print(f"       请创建 config.yaml 并填入 DeepSeek API 密钥")
        print(f"       可参考: 将 config.yaml.example 复制为 config.yaml 后编辑")

    return config


def _deep_merge(base: dict, override: dict) -> None:
    """递归合并 override 到 base（原地修改）。"""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val


# ═══════════════════════════════════════════════════════════════
# DeepSeek 分类器
# ═══════════════════════════════════════════════════════════════

def _load_cover_skill() -> str:
    """从 skills/detect-cover/SKILL.md 加载封面检测 Skill 的 prompt。"""
    skill_path = ROOT / "skills" / "detect-cover" / "SKILL.md"
    if skill_path.exists():
        content = skill_path.read_text(encoding="utf-8")
        # 移除 YAML 前置元数据
        import re as _re
        m = _re.match(r'^---\s*\n.*?\n---\s*\n', content, _re.DOTALL)
        if m:
            return content[m.end():].strip()
        return content.strip()
    # 后备：内嵌的简化 prompt
    return """你是一名专业的政府采购招标文件结构分析工程师。
你的唯一任务是判断给定的文本块是否是投标文件的封面页。
封面页特征：文字少、信息字段多（项目编号、项目名称、所投包号、投标单位名称、投标代表人姓名、投标日期、加盖电子签章、"投 标 文 件"间隔标题）。
排除条件：包含大段文字（>500字）、包含"投标邀请函""招标项目需求""投标须知""合同条款""附件"等标题。
返回严格JSON：{"is_cover_page": true/false, "confidence": 0.0-1.0, "matched_fields": [...], "total_text_length": 0, "reason": "..."}"""

SYSTEM_PROMPT = _load_cover_skill()


class DeepSeekClassifier:
    """使用 DeepSeek API（OpenAI 兼容接口）分类文档块。"""

    def __init__(self, config: Dict[str, Any]):
        cfg = config["deepseek"]
        self.api_key = cfg.get("api_key", "")
        self.base_url = cfg.get("base_url", "https://api.deepseek.com")
        self.model = cfg.get("model", "deepseek-v4-pro")
        self.temperature = cfg.get("temperature", 0.1)
        self.max_tokens = cfg.get("max_tokens", 500)
        self.timeout = cfg.get("timeout", 30)

    def classify(self, signature_text: str, chunk_index: int) -> Optional[Dict[str, Any]]:
        """
        调用 DeepSeek API 判断文本块是否是投标文件封面页。

        Args:
            signature_text: 段落块的前 N 段文字
            chunk_index: 块编号

        Returns:
            {"is_cover_page": bool, "confidence": float, "matched_fields": [...], "reason": str}
            或 None
        """
        if not self.api_key or self.api_key == "sk-your-api-key-here":
            print(f"  [SKIP] Chunk {chunk_index}: 未配置 API 密钥，跳过 AI 判断")
            return None

        if not signature_text.strip():
            return None

        try:
            from openai import OpenAI
        except ImportError:
            print(f"  [ERROR] 需要安装 openai 库: pip install openai>=1.0")
            return None

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        try:
            response = client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"请判断以下文本块是否是投标文件的封面页：\n\n{signature_text[:2000]}",
                    },
                ],
                timeout=self.timeout,
            )

            content = response.choices[0].message.content.strip()

            # 尝试解析 JSON（可能被 markdown 代码块包裹）
            result = self._parse_json_response(content)
            if result:
                result["_chunk_index"] = chunk_index
                result["_raw_response"] = content[:200]
                return result

            # 如果 JSON 解析失败，回退到关键词判断
            return self._keyword_fallback(signature_text, chunk_index)

        except Exception as e:
            print(f"  [ERROR] Chunk {chunk_index}: API 调用失败: {e}")
            # 回退到关键词判断
            return self._keyword_fallback(signature_text, chunk_index)

    @staticmethod
    def _parse_json_response(text: str) -> Optional[Dict[str, Any]]:
        """从 AI 响应中解析 JSON。处理被 markdown 代码块包裹的情况。"""
        import re
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试去掉 ```json ... ``` 包裹
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 尝试找到 JSON 对象
        m = re.search(r'\{[^{}]*"is_cover_page"[^{}]*\}', text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

        return None

    # ── 封面页字段模式（唯一判断标准） ──
    COVER_FIELD_PATTERNS = [
        (r'投\s*标\s*文\s*件', 0.25, "投标文件标题"),        # "投 标 文 件"
        (r'项目编号', 0.18, "项目编号"),
        (r'项目名称', 0.18, "项目名称"),
        (r'所投包号', 0.18, "所投包号"),
        (r'投标单位名称', 0.18, "投标单位名称"),
        (r'投标代表人姓名', 0.18, "投标代表人姓名"),
        (r'投标日期.*年.*月.*日', 0.18, "投标日期"),
        (r'加盖电子签章', 0.15, "电子签章"),
        (r'投标文件封面', 0.10, "封面格式"),
    ]

    # ── 排除模式 ──
    EXCLUDE_PATTERNS = [
        (r'投标邀请函', 0.80, "投标邀请函"),
        (r'招标项目需求', 0.80, "招标项目需求"),
        (r'投标须知', 0.80, "投标须知"),
        (r'合同条款', 0.80, "合同条款"),
        (r'附件\s*[1-9]', 0.50, "附件编号"),
        (r'开标一览表', 0.50, "附件-开标一览表"),
        (r'开标分项一览表', 0.50, "附件-分项一览表"),
        (r'商务要求.*应答表', 0.40, "附件-商务应答表"),
        (r'技术要求.*应答表', 0.40, "附件-技术应答表"),
        (r'中小企业声明函', 0.40, "附件-中小企业声明函"),
    ]

    @classmethod
    def _keyword_fallback(cls, signature_text: str, chunk_index: int) -> Dict[str, Any]:
        """
        封面页专用检测 — 只看封面字段，其他一概排除。

        判断逻辑：
        1. 文字量检查：封面页文字稀疏（总长度 < 500 字）
        2. 封面字段匹配：匹配数 >= 2
        3. 排除检查：命中任何排除模式则直接否决
        4. 综合置信度 = 封面得分 - 排除惩罚
        5. is_cover_page = (匹配字段 >= 2) AND (无排除) AND (文字稀疏)
        """
        text = signature_text
        total_len = len(text)

        # ── 文字量检查：封面页通常 50-300 字 ──
        if total_len > 500:
            return {
                "is_cover_page": False,
                "confidence": 0.0,
                "matched_fields": [],
                "total_text_length": total_len,
                "reason": f"文字量过大（{total_len}字），封面页不应超过500字",
                "_chunk_index": chunk_index,
                "_fallback": True,
            }

        # ── 排除检查 ──
        exclude_hits = []
        for pattern, weight, label in cls.EXCLUDE_PATTERNS:
            if re.search(pattern, text):
                exclude_hits.append((weight, label))

        if exclude_hits:
            total_penalty = sum(w for w, _ in exclude_hits)
            labels = [l for _, l in exclude_hits]
            return {
                "is_cover_page": False,
                "confidence": 0.0,
                "matched_fields": [],
                "total_text_length": total_len,
                "reason": f"命中排除模式: {', '.join(labels)}",
                "_chunk_index": chunk_index,
                "_fallback": True,
                "_exclude_hits": labels,
            }

        # ── 封面字段匹配 ──
        matched_fields = []
        cover_score = 0.0
        for pattern, weight, label in cls.COVER_FIELD_PATTERNS:
            if re.search(pattern, text):
                cover_score += weight
                matched_fields.append(label)

        # ── 判断 ──
        field_count = len(matched_fields)
        is_cover = field_count >= 2  # 至少匹配 2 个封面字段
        confidence = min(0.98, cover_score) if is_cover else max(0.0, cover_score - 0.3)

        return {
            "is_cover_page": is_cover,
            "confidence": round(confidence, 2),
            "matched_fields": matched_fields,
            "total_text_length": total_len,
            "reason": (
                f"封面字段 {field_count}/9 个: {', '.join(matched_fields[:6])}"
                if is_cover else
                f"封面字段不足（{field_count}/9 个），总字数={total_len}"
            ),
            "_chunk_index": chunk_index,
            "_fallback": True,
        }


# ═══════════════════════════════════════════════════════════════
# 文档分块器
# ═══════════════════════════════════════════════════════════════

@dataclass
class DocChunk:
    """文档中的一个段落块（两个分页符之间的内容）。"""
    chunk_index: int
    para_start: int                         # 起始段落索引（含）
    para_end: int                           # 结束段落索引（不含）
    signature: str                          # 前 N 段文字（用于 AI 判断）
    para_count: int = 0
    has_table: bool = False
    classification: Optional[Dict[str, Any]] = None


class DocxSegmenter:
    """按分页符/分节符将 DOCX 文档切分为段落块。"""

    SIGNATURE_PARA_COUNT = 10  # 每个块取前 N 段作为签名（10段内遇断点则截断）

    def __init__(self, docx_path: Path):
        self.docx_path = Path(docx_path)
        self.doc: Optional[DocxDocument] = None
        self._paragraphs: List[Paragraph] = []
        self._tables: List[Tuple[int, DocxTable]] = []  # (para_index, table)

    def segment(self) -> Tuple[List[DocChunk], List[Tuple[int, DocxTable]], Dict[int, int]]:
        """
        主入口：打开 DOCX，找到所有断点，切分为块。

        Returns:
            (chunks, tables_with_positions, table_to_chunk_map)
        """
        if not self.docx_path.exists():
            raise FileNotFoundError(f"标书文件不存在: {self.docx_path}")

        self.doc = Document(str(self.docx_path))

        # ── 第一步：建立段落和表格的全局列表 ──
        self._paragraphs = []
        self._tables = []

        for block in self._iter_block_items(self.doc):
            if isinstance(block, Paragraph):
                self._paragraphs.append(block)
            elif isinstance(block, DocxTable):
                # 表格在段落列表中的插入位置（近似为当前段落数）
                self._tables.append((len(self._paragraphs), block))

        total = len(self._paragraphs)
        print(f"  总段落数: {total}, 总表格数: {len(self._tables)}")

        # ── 第二步：找到所有断点 ──
        break_indices = self._find_all_breaks()
        print(f"  断点数: {len(break_indices)}")

        # ── 第三步：按断点切分 ──
        # 文档开始也算一个逻辑断点
        segments = [0] + sorted(break_indices) + [total]

        chunks = []
        for i in range(len(segments) - 1):
            start = segments[i]
            end = segments[i + 1]
            if start >= end:
                continue

            # 构建签名：最多取 10 段文字，但遇到块内下一个断点则截断
            effective_end = min(start + self.SIGNATURE_PARA_COUNT, end)
            # 检查 chunks 内是否有下一断点（在 10 段范围内）
            inner_breaks = [b for b in sorted(break_indices) if start < b < effective_end]
            if inner_breaks:
                effective_end = inner_breaks[0]  # 在第一个内嵌断点处截断

            sig_paras = self._paragraphs[start:effective_end]
            sig_text = "\n".join(p.text[:150] for p in sig_paras if p.text.strip())

            # 检查块中是否包含表格
            has_table = any(start <= t[0] < end for t in self._tables)

            chunk = DocChunk(
                chunk_index=len(chunks),
                para_start=start,
                para_end=end,
                signature=sig_text,
                para_count=end - start,
                has_table=has_table,
            )
            chunks.append(chunk)

        # ── 第四步：建立表格→块映射 ──
        table_to_chunk: Dict[int, int] = {}
        for t_idx, (t_pos, _) in enumerate(self._tables):
            for c in chunks:
                if c.para_start <= t_pos < c.para_end:
                    table_to_chunk[t_idx] = c.chunk_index
                    break

        return chunks, self._tables, table_to_chunk

    def get_paragraphs_in_range(self, start: int, end: int) -> List[Paragraph]:
        """获取指定范围内的段落。"""
        return self._paragraphs[start:end]

    def get_tables_in_range(self, start: int, end: int) -> List[Tuple[int, DocxTable]]:
        """获取指定范围内的表格。"""
        return [(pos, t) for pos, t in self._tables if start <= pos < end]

    def _find_all_breaks(self) -> List[int]:
        """
        找到所有断点位置（分页符和分节符之后的段落索引）。

        分页符：段落内的 w:br type="page"
        分节符：段落内的 w:sectPr（在最后一段中）

        返回：断点后第一个段落的索引列表
        """
        breaks = []

        for i, para in enumerate(self._paragraphs):
            # 检查段落内是否有手动分页符
            for run in para.runs:
                # 通过 runs 检查
                for br in run._element.findall(qn("w:br")):
                    br_type = br.get(qn("w:type"))
                    if br_type == "page":
                        breaks.append(i + 1)  # 下一个段落是新页的开始
                        break

            # 也可以通过段落属性检查
            pPr = para._element.find(qn("w:pPr"))
            if pPr is not None:
                for br in pPr.findall(qn("w:br")):
                    br_type = br.get(qn("w:type"))
                    if br_type == "page":
                        if i + 1 not in breaks:
                            breaks.append(i + 1)
                        break

        # 分节符：检查文档的 sections
        # 每个 section 的开始位置（除了第一个）
        # 注意：python-docx 中节的切换不一定反映在段落索引中
        # 我们在节的边界处也添加断点
        # 估算：每节平均段落数
        if len(self._paragraphs) > 0 and len(self.doc.sections) > 1:
            avg_per_section = len(self._paragraphs) // len(self.doc.sections)
            for s_idx in range(1, len(self.doc.sections)):
                # 估算位置
                est_pos = s_idx * avg_per_section
                # 如果该位置附近没有已有的断点，添加
                if not any(abs(b - est_pos) < 5 for b in breaks):
                    breaks.append(est_pos)

        return sorted(set(breaks))

    @staticmethod
    def _iter_block_items(parent):
        """按文档顺序迭代段落和表格。"""
        parent_elm = parent.element.body if isinstance(parent, DocxDocument) else parent._element
        for child in parent_elm.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, parent)
            elif isinstance(child, CT_Tbl):
                yield DocxTable(child, parent)


# ═══════════════════════════════════════════════════════════════
# Word COM 重建器（Windows — 完美保留格式）
# ═══════════════════════════════════════════════════════════════

class WordComRebuilder:
    """
    使用 Microsoft Word COM 自动化从源 DOCX 中提取格式章节。
    Word 原生复制/粘贴保留 100% 的格式（字体、表格、图片、页眉页脚）。
    仅适用于 Windows 且已安装 Word。
    """

    wdFormatOriginalFormatting = 16
    wdFormatSurroundingFormattingWithEmphasis = 20
    wdStory = 6          # wdMainTextStory
    wdFindContinue = 1
    wdPageBreak = 7

    def __init__(self, source_docx_path: Path):
        self.source_path = Path(source_docx_path).resolve()
        self.word = None

    # 在文档中搜索封面页的定位文本（按优先级排列）
    START_MARKERS = [
        "第五部分",
        "投标文件封面格式",
        "投 标 文 件",
    ]

    def rebuild(self, para_start_0based: int, output_path: Path) -> Path:
        """
        使用 Word COM 从封面页开始提取到文档末尾。

        通过内容搜索（而非段落索引）定位起始位置，因为 Word 的段落计数
        包含表格单元格等内容，与 python-docx 的计数不一致。

        Args:
            para_start_0based: 封面页起始段落（python-docx 0-based，仅供后备）
            output_path: 输出 .docx 路径

        Returns:
            输出文件路径
        """
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        word = None
        doc = None
        new_doc = None

        try:
            # ── 启动 Word ──
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0
            word.ScreenUpdating = False
            self.word = word

            # ── 打开源文档 ──
            doc = word.Documents.Open(str(self.source_path), ReadOnly=True)
            total_paras = doc.Paragraphs.Count
            print(f"    Word COM: 源文档已打开 (Word 计数 {total_paras} 段, python-docx 封面在第 {para_start_0based} 段)")

            # ── 通过内容搜索定位封面页起始位置 ──
            find_start = self._find_cover_start(doc)

            if find_start is None:
                # 后备：使用 python-docx 的段落索引估算
                # Word 的段落数通常比 python-docx 多（因为表格单元格中的段落也被计数）
                # 使用比例估算：ratio = python-docx_index / python-docx_total
                # Word_index ≈ ratio × Word_total
                # 但我们不知道 python-docx_total... 直接用覆盖率估算
                ratio = min(1.0, para_start_0based / max(757, 1))  # 757 = python-docx 总段数
                word_para_idx = max(1, int(ratio * total_paras))
                print(f"    Word COM: 内容搜索失败，回退到比例估算 (ratio={ratio:.2f}, Word para={word_para_idx})")
                target_para = doc.Paragraphs(word_para_idx)
                find_start = target_para.Range.Start

            # ── 选中从封面页到文档末尾 ──
            doc_range = doc.Range(find_start, doc.Content.End)
            doc_range.Select()
            word.Selection.Copy()

            print(f"    Word COM: 已复制封面页到文档末尾")

            # ── 创建新文档 ──
            new_doc = word.Documents.Add()

            # 复制页面设置
            try:
                ps_src = doc.PageSetup
                ps_new = new_doc.PageSetup
                ps_new.PageWidth = ps_src.PageWidth
                ps_new.PageHeight = ps_src.PageHeight
                ps_new.TopMargin = ps_src.TopMargin
                ps_new.BottomMargin = ps_src.BottomMargin
                ps_new.LeftMargin = ps_src.LeftMargin
                ps_new.RightMargin = ps_src.RightMargin
            except Exception:
                pass

            # 粘贴保留源格式
            new_doc.Range().PasteAndFormat(self.wdFormatOriginalFormatting)
            print(f"    Word COM: 已粘贴到新文档（保留源格式）")

            # ── 保存 ──
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass

            new_doc.SaveAs(str(output_path), FileFormat=16)
            size_kb = output_path.stat().st_size / 1024 if output_path.exists() else 0
            print(f"    Word COM: 已保存 {output_path.name} ({size_kb:.1f} KB)")

            return output_path

        except Exception as e:
            raise RuntimeError(f"Word COM 重建失败: {e}") from e

        finally:
            if new_doc is not None:
                try:
                    new_doc.Close(SaveChanges=0)
                except Exception:
                    pass
            if doc is not None:
                try:
                    doc.Close(SaveChanges=0)
                except Exception:
                    pass
            if word is not None:
                try:
                    word.ScreenUpdating = True
                    word.Quit()
                except Exception:
                    pass
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    @classmethod
    def _find_cover_start(cls, doc) -> Optional[int]:
        """
        使用 Word Find 在文档中搜索封面页的起始位置。

        按优先级搜索 START_MARKERS，返回第一个匹配文本的 Range.Start。

        Returns:
            匹配位置(start_offset) 或 None
        """
        for marker in cls.START_MARKERS:
            find = doc.Content.Find
            find.Text = marker
            find.Forward = True
            find.Wrap = 0  # wdFindStop — 不循环
            find.Format = False
            find.MatchCase = False
            find.MatchWholeWord = False
            find.MatchWildcards = False

            found = find.Execute()
            if found:
                # Find 成功后，选中了匹配的 Range
                start_pos = find.Parent.Start
                # 检查匹配的位置是否在文档前半部分之后
                #（避免在 TOC 中匹配到"第五部分"）
                if start_pos > doc.Content.End * 0.3:
                    print(f"    Word COM: 找到封面标记 '{marker}' 位于位置 {start_pos}")
                    return start_pos
                else:
                    # 在 TOC 中匹配到的，继续搜索下一个
                    print(f"    Word COM: 跳过 TOC 中的 '{marker}' (位置 {start_pos} 太靠前)")

        # 如果都找不到，尝试查找 "项目编号："
        find = doc.Content.Find
        find.Text = "项目编号："
        find.Forward = True
        find.Wrap = 0
        if find.Execute():
            start_pos = find.Parent.Start
            if start_pos > doc.Content.End * 0.3:
                print(f"    Word COM: 找到封面字段 '项目编号：' 位于位置 {start_pos}")
                return start_pos

        return None


# ═══════════════════════════════════════════════════════════════
# python-docx 重建器（后备方案）
# ═══════════════════════════════════════════════════════════════

class DocxRebuilder:
    """从原始 DOCX 中提取指定范围的段落和表格，重建新的 DOCX 文件。"""

    def __init__(self, source_docx_path: Path):
        self.source_path = Path(source_docx_path)

    def rebuild(
        self,
        chunks: List[DocChunk],
        tables_with_pos: List[Tuple[int, DocxTable]],
        table_to_chunk: Dict[int, int],
        output_path: Path,
    ) -> Path:
        """
        提取属于"投标文件格式"的块，重建为新的 DOCX。

        Args:
            chunks: 所有段落块
            tables_with_pos: 表格及其位置
            table_to_chunk: 表格→块映射
            output_path: 输出路径

        Returns:
            输出文件路径
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 找到所有标记为格式章节的块
        format_chunks = [
            c for c in chunks
            if c.classification and c.classification.get("is_format_section")
        ]

        if not format_chunks:
            print("[WARN] 未找到投标文件格式章节，将使用关键词回退判断")
            # 回退：使用第一个签名中包含"投标文件格式"的块
            for c in chunks:
                if "投标文件格式" in c.signature or "第五部分" in c.signature:
                    format_chunks.append(c)
                    break

        if not format_chunks:
            raise RuntimeError("无法找到投标文件格式章节。请检查标书文件结构。")

        print(f"  找到 {len(format_chunks)} 个格式块（共 {sum(c.para_count for c in format_chunks)} 段）")

        # ── 重建 DOCX ──
        # 策略：复制原始文档，然后只保留格式块的 body 内容
        source_doc = Document(str(self.source_path))
        new_doc = Document()

        # ── 复制页面设置 ──
        self._copy_section_properties(source_doc, new_doc)

        # ── 复制格式块的段落和表格 ──
        new_body = new_doc.element.body

        for chunk in format_chunks:
            # 获取该范围内的所有块（段落 + 表格按顺序交错）
            items_in_range = self._collect_items_in_range(
                source_doc, chunk.para_start, chunk.para_end,
                tables_with_pos, table_to_chunk, chunk.chunk_index,
            )

            for item in items_in_range:
                # 深拷贝元素（保留所有格式）
                imported = copy.deepcopy(item)
                new_body.append(imported)

        # ── 保存 ──
        new_doc.save(str(output_path))
        size_kb = output_path.stat().st_size / 1024
        print(f"  [OK] 模板已生成: {output_path} ({size_kb:.1f} KB)")

        return output_path

    def _collect_items_in_range(
        self,
        doc: DocxDocument,
        para_start: int,
        para_end: int,
        tables_with_pos: List[Tuple[int, DocxTable]],
        table_to_chunk: Dict[int, int],
        chunk_index: int,
    ) -> List:
        """
        收集一个段落范围内的所有 XML 元素（段落+表格），保持原始文档顺序。
        """
        items = []

        # 从 source doc 获取所有 body 元素
        body = doc.element.body
        all_elements = list(body.iterchildren())

        # 找到属于该范围的元素
        para_idx = 0
        table_idx = 0
        tables_in_range = [
            (pos, t) for pos, t in tables_with_pos
            if table_to_chunk.get(tables_with_pos.index((pos, t)), -1) == chunk_index
        ]

        # 简化策略：直接从原始 body 中提取指定范围的元素
        # 记录当前遍历到的段落索引
        current_para = 0
        current_table = 0

        for elem in all_elements:
            if elem.tag == qn("w:p"):
                if para_start <= current_para < para_end:
                    items.append(elem)
                current_para += 1
            elif elem.tag == qn("w:tbl"):
                # 表格的位置近似为其前面的段落数
                if para_start <= current_para < para_end:
                    items.append(elem)
            # 跳过 sectPr（节属性，会在 _copy_section_properties 中处理）
            elif elem.tag == qn("w:sectPr"):
                pass

        return items

    @staticmethod
    def _copy_section_properties(source_doc: DocxDocument, target_doc: DocxDocument) -> None:
        """复制源文档的页面设置到目标文档。"""
        if source_doc.sections:
            src_section = source_doc.sections[0]
            tgt_section = target_doc.sections[0]

            if src_section.page_width:
                tgt_section.page_width = src_section.page_width
            if src_section.page_height:
                tgt_section.page_height = src_section.page_height
            if src_section.top_margin:
                tgt_section.top_margin = src_section.top_margin
            if src_section.bottom_margin:
                tgt_section.bottom_margin = src_section.bottom_margin
            if src_section.left_margin:
                tgt_section.left_margin = src_section.left_margin
            if src_section.right_margin:
                tgt_section.right_margin = src_section.right_margin


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════
# 可导入的函数（供 pipeline 调用）
# ═══════════════════════════════════════════════════════════════

def extract_template_docx(
    input_docx: Optional[Path] = None,
    output_docx: Optional[Path] = None,
    use_api: bool = False,
) -> Path:
    """
    从标书文件中提取投标文件格式模板（供 pipeline 调用）。

    Args:
        input_docx: 输入标书文件路径（默认: 标书文件.docx）
        output_docx: 输出模板路径（默认: templates/templates.docx）
        use_api: 是否使用 DeepSeek API 进行判断

    Returns:
        输出文件路径
    """
    input_path = Path(input_docx) if input_docx else ROOT / "标书文件.docx"
    output_path = Path(output_docx) if output_docx else ROOT / "templates" / "templates.docx"

    # 分段
    segmenter = DocxSegmenter(input_path)
    chunks, tables, table_to_chunk = segmenter.segment()

    # 分类
    classifier = DeepSeekClassifier(DEFAULT_CONFIG) if use_api else None
    for c in chunks:
        if classifier:
            result = classifier.classify(c.signature, c.chunk_index)
            c.classification = result if result else DeepSeekClassifier._keyword_fallback(c.signature, c.chunk_index)
        else:
            c.classification = DeepSeekClassifier._keyword_fallback(c.signature, c.chunk_index)

    # 找到封面页
    cover_chunk = None
    for c in chunks:
        if c.classification and c.classification.get("is_cover_page"):
            cover_chunk = c
            break

    if not cover_chunk:
        raise RuntimeError("未找到投标文件封面页")

    # Word COM 重建
    rebuilder = WordComRebuilder(input_path)
    rebuilder.rebuild(cover_chunk.para_start, output_path)

    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description='从标书文件中按分节符/分页符切分并提取投标文件格式章节',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python extract_format_section.py                    # 使用默认 config.yaml
  python extract_format_section.py --config my.yaml  # 指定配置文件
  python extract_format_section.py --dry-run         # 仅分段展示，不调用 API
  python extract_format_section.py --no-api          # 使用关键词判断，不调用 API
        """,
    )
    parser.add_argument("--config", type=str, default=None, help="配置文件路径")
    parser.add_argument("--dry-run", action="store_true", help="仅分段和展示，不生成文件")
    parser.add_argument("--no-api", action="store_true", help="不使用 AI API，仅用关键词判断")
    parser.add_argument("--chunks", type=int, default=0, help="仅展示前 N 个块的签名")
    parser.add_argument("--no-com", action="store_true", help="禁用 Word COM，使用 python-docx 重建")
    args = parser.parse_args()

    print("=" * 60)
    print("  标书文件格式章节提取工具")
    print("=" * 60)

    # ── 加载配置 ──
    config_path = Path(args.config) if args.config else None
    config = load_config(config_path)

    input_path = ROOT / config["paths"]["input_docx"]
    output_dir = ROOT / config["paths"]["output_dir"]
    output_docx = output_dir / config["paths"]["output_docx"]

    print(f"  输入文件: {input_path}")
    print(f"  输出目录: {output_dir}")

    if not input_path.exists():
        print(f"\n[ERROR] 标书文件不存在: {input_path}")
        return 1

    # ── 第一步：分段 ──
    print("\n  第一步：文档分段...")
    segmenter = DocxSegmenter(input_path)
    chunks, tables, table_to_chunk = segmenter.segment()

    print(f"  共切分为 {len(chunks)} 个段落块:")

    # 展示每个块的签名
    for c in chunks:
        sig_preview = c.signature[:120].replace("\n", " | ")
        print(f"\n  ┌─ Chunk {c.chunk_index} (段落 {c.para_start}-{c.para_end}, {c.para_count}段)")
        print(f"  └─ 签名: {sig_preview}...")

    if args.chunks > 0:
        print(f"\n[INFO] --chunks 模式：仅展示前 {args.chunks} 个块")
        return 0

    if args.dry_run:
        print("\n[INFO] --dry-run 模式：仅分段展示，不生成文件")
        return 0

    # ── 第二步：分类 ──
    print(f"\n  第二步：分类段落块...")

    if args.no_api:
        print("  [INFO] --no-api 模式：使用关键词回退判断")
        classifier = DeepSeekClassifier({"deepseek": DEFAULT_CONFIG["deepseek"]})
        for c in chunks:
            c.classification = DeepSeekClassifier._keyword_fallback(c.signature, c.chunk_index)
            is_cov = c.classification.get("is_cover_page", False)
            fields = c.classification.get("matched_fields", [])
            txt_len = c.classification.get("total_text_length", 0)
            verdict = "[COVER]" if is_cov else "[other]"
            print(f"    Chunk {c.chunk_index}: {verdict} "
                  f"置信度={c.classification['confidence']:.0%} "
                  f"字段={len(fields)}/9 字数={txt_len}")
    else:
        classifier = DeepSeekClassifier(config)
        for c in chunks:
            print(f"    正在判断 Chunk {c.chunk_index}...", end=" ")
            result = classifier.classify(c.signature, c.chunk_index)
            if result is None:
                # API 调用失败或密钥未配置，回退到关键词
                result = DeepSeekClassifier._keyword_fallback(c.signature, c.chunk_index)
            c.classification = result
            is_cov = result.get("is_cover_page", False)
            fields = result.get("matched_fields", [])
            verdict = "[COVER]" if is_cov else "[other]"
            print(f"{verdict} (置信度={result['confidence']:.0%}, 字段={len(fields)}/9)")

    # ── 第三步：重建 DOCX ──
    print(f"\n  第三步：重建模板 DOCX...")

    # 找到封面页块（只有一个封面页）
    cover_chunk = None
    for c in chunks:
        if c.classification and c.classification.get("is_cover_page"):
            cover_chunk = c
            break

    if not cover_chunk:
        print("[ERROR] 未找到投标文件封面页")
        return 1

    print(f"  封面页: Chunk {cover_chunk.chunk_index} (段落 {cover_chunk.para_start})")
    first_format_para = cover_chunk.para_start

    if args.no_com:
        print("  [INFO] --no-com 模式：使用 python-docx 重建")
        rebuilder = DocxRebuilder(input_path)
        try:
            rebuilder.rebuild(chunks, tables, table_to_chunk, output_docx)
        except RuntimeError as e:
            print(f"\n[ERROR] {e}")
            return 1
    else:
        # 默认：使用 Word COM 重建（保留完美格式）
        try:
            import win32com.client
            import pythoncom
            rebuilder = WordComRebuilder(input_path)
            rebuilder.rebuild(first_format_para, output_docx)
        except ImportError as e:
            print(f"  [WARN] win32com 不可用 ({e})，回退到 python-docx")
            rebuilder = DocxRebuilder(input_path)
            try:
                rebuilder.rebuild(chunks, tables, table_to_chunk, output_docx)
            except RuntimeError as e2:
                print(f"\n[ERROR] {e2}")
                return 1
        except RuntimeError as e:
            print(f"\n[ERROR] Word COM 重建失败: {e}")
            print("  尝试回退到 python-docx...")
            try:
                rebuilder = DocxRebuilder(input_path)
                rebuilder.rebuild(chunks, tables, table_to_chunk, output_docx)
            except RuntimeError as e2:
                print(f"\n[ERROR] python-docx 回退也失败: {e2}")
                return 1

    # ── 第四步：保存元数据 ──
    metadata_path = output_dir / "format_segments.json"
    metadata = {
        "source_file": str(input_path),
        "generated_at": datetime.datetime.now().isoformat(),
        "total_chunks": len(chunks),
        "cover_chunk": {
            "chunk_index": cover_chunk.chunk_index,
            "para_start": cover_chunk.para_start,
            "para_end": cover_chunk.para_end,
            "para_count": cover_chunk.para_count,
            "classification": cover_chunk.classification,
        } if cover_chunk else None,
        "all_classifications": [
            {
                "chunk_index": c.chunk_index,
                "is_cover_page": c.classification.get("is_cover_page") if c.classification else None,
                "confidence": c.classification.get("confidence") if c.classification else None,
                "matched_fields": c.classification.get("matched_fields") if c.classification else [],
                "total_text_length": c.classification.get("total_text_length") if c.classification else 0,
                "reason": c.classification.get("reason") if c.classification else "",
            }
            for c in chunks
        ],
    }

    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  元数据已保存: {metadata_path}")

    print("\n" + "=" * 60)
    print("  提取完成！")
    print(f"  模板文件: {output_docx}")
    print(f"  元数据: {metadata_path}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
