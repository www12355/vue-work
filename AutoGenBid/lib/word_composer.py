"""
Word COM 内容插入引擎 — 使用 Microsoft Word 原生操作将 AI 生成内容插入模板。

用途：
    Stage 7-8 使用此模块：
    1. 在模板中定位章节标记（附件XX、X.X.X 标题）
    2. 在正确位置插入应答表和 AI 生成的技术章节
    3. 最终导出完整格式的投标文件

用法:
    from lib.word_composer import WordComposer
    composer = WordComposer(template_path, output_path)
    composer.insert_response_table("附件6", response_docx_path)
    composer.insert_technical_chapters("附件11", draft_md_path)
    composer.finalize()
"""

from __future__ import annotations

import sys
import json
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── 默认格式常量 ──────────────────────────────────────────────
# 当无法从 format_spec.json 加载时使用

DEFAULT_FORMAT = {
    "body": {
        "font_cjk": "宋体",
        "font_latin": "Times New Roman",
        "font_size_pt": 12,          # 小四
        "bold": False,
        "first_line_indent_cm": 0.74,
        "line_spacing": 1.5,
        "space_before_pt": 0,
        "space_after_pt": 6,
        "alignment": 3,              # wdAlignParagraphJustify
    },
    "heading": {
        "h1": {  # x.x / x.x.x 数字标题（大标题，段前段后各1行）
            "font_cjk": "黑体",
            "font_latin": "Times New Roman",
            "font_size_pt": 14,      # 四号
            "bold": True,
            "first_line_indent_cm": 0,
            "line_spacing": 1.5,
            "space_before_pt": 12,
            "space_after_pt": 12,
            "alignment": 0,          # wdAlignParagraphLeft
        },
        "h2": {  # x.x.x.x 更深层级（小标题，段前段后各0.5行）
            "font_cjk": "黑体",
            "font_latin": "Times New Roman",
            "font_size_pt": 12,      # 小四
            "bold": True,
            "first_line_indent_cm": 0,
            "line_spacing": 1.5,
            "space_before_pt": 6,
            "space_after_pt": 6,
            "alignment": 0,
        },
    },
    "table": {
        "font_cjk": "宋体",
        "font_latin": "Times New Roman",
        "font_size_pt": 10.5,        # 五号
        "header_bold": True,
        "alignment": 1,              # wdAlignRowCenter
    },
    "caption": {
        "font_cjk": "宋体",
        "font_latin": "Times New Roman",
        "font_size_pt": 10.5,        # 五号
        "bold": False,
        "alignment": 1,              # wdAlignParagraphCenter
    },
}


class WordComposer:
    """
    使用 Word COM 自动化将内容插入到投标模板中。

    支持的操作：
    - 按内容搜索定位章节标记
    - 在标记后插入 DOCX 文件（保留格式）
    - 在标记后插入格式化 Markdown 文本（标题/正文/表格/列表）
    - 最终文档保存
    """

    # 插入位置常量
    POS_BEFORE = "before"
    POS_AFTER = "after"
    POS_REPLACE = "replace"

    # 标题检测正则
    HEADING_MD_PATTERN = re.compile(r'^(#{1,6})\s+(.+)')
    HEADING_NUM_PATTERN = re.compile(r'^(\d+(?:\.\d+)+)\s+(.+)')
    TABLE_ROW_PATTERN = re.compile(r'^\|.+\|$')
    TABLE_SEP_PATTERN = re.compile(r'^\|[\s\-:|]+\|$')
    LIST_PATTERN = re.compile(r'^(\s*)[-*+]\s+(.+)')
    ORDERED_LIST_PATTERN = re.compile(r'^(\s*)\d+[.)]\s+(.+)')

    def __init__(self, template_path: Path, output_path: Path):
        self.template_path = Path(template_path).resolve()
        self.output_path = Path(output_path).resolve()
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.word = None
        self.doc = None
        self._format_spec: Optional[Dict[str, Any]] = None
        self._table_counter: int = 0

    # ── 主入口 ──────────────────────────────────────────────

    def compose(
        self,
        response_table_path: Optional[Path] = None,
        technical_draft_path: Optional[Path] = None,
        strategy_name: str = "",
        insertion_plan: Optional[List[Dict[str, Any]]] = None,
    ) -> Path:
        """
        执行完整的模板填充流程（假设 COM 已在调用方初始化）。

        Args:
            insertion_plan: 从 template_map.json 读取的插入计划，
                           优先使用计划中的目标标记，不存在时回退到默认值
        """
        import win32com.client
        import time

        # 从 insertion_plan 中提取插入目标
        resp_target = None
        tech_target = None
        if insertion_plan:
            for step in insertion_plan:
                if step.get("content") == "response_table" and resp_target is None:
                    resp_target = step.get("target")
                elif step.get("content") == "technical_chapters" and tech_target is None:
                    tech_target = step.get("target")

        # 默认回退
        if resp_target is None:
            resp_target = "附件6"
        if tech_target is None:
            tech_target = "附件11"

        try:
            self._open_template()

            # 重置表格计数器
            self._table_counter = 0

            # 预加载格式规格
            self._load_format_spec()

            if response_table_path and response_table_path.exists():
                # ── 三级回退：智能章节插入 → 总结段落 → marker 插入 ──
                inserted = False

                # 第1级：按章节关键词智能插入（找到"总体技术架构设计"等章节末尾）
                section_keywords = [
                    "项目概述", "概述", "项目背景与需求分析",
                    "总体技术架构设计", "总体技术架构", "技术方案概述",
                    "方案总体设计", "总体架构", "总体设计方案",
                    "技术架构设计", "建设方案",
                    "总体建设方案", "系统总体设计", "技术方案总体",
                ]
                for kw in section_keywords:
                    if self._insert_response_table_at_section_end(
                        kw, response_docx_path, column_ratio=(1, 2, 7, 2)
                    ):
                        inserted = True
                        break

                # 第2级：在前 10 段内搜索总结性段落
                if not inserted:
                    summary_point = self._find_summary_insertion_point(max_paragraphs=10)
                    if summary_point:
                        print(f"    WordComposer: 在总结段落后插入应答表 ({summary_point[:40]}...)")
                        inserted = self._insert_docx_at_marker(summary_point, response_docx_path)

                # 第3级：回退到 insertion_plan 目标标记（默认 "附件6"）
                if not inserted:
                    print(f"    WordComposer: 插入应答表 → {resp_target}（默认 marker）")
                    self._insert_docx_at_marker(resp_target, response_docx_path)
                time.sleep(0.3)

            if technical_draft_path and technical_draft_path.exists():
                print(f"    WordComposer: 插入技术方案 → {tech_target}")
                if technical_draft_path.suffix.lower() == '.docx':
                    self._insert_docx_at_marker(tech_target, technical_draft_path)
                else:
                    self._insert_markdown_at_marker(tech_target, technical_draft_path)
                time.sleep(0.3)

            self._save()
            if self.doc:
                self.doc.Close()
                self.doc = None

            print(f"    WordComposer: 完成 → {self.output_path.name}")
            return self.output_path

        except Exception as e:
            if self.doc:
                try:
                    self.doc.Close(SaveChanges=0)
                except Exception:
                    pass
            raise RuntimeError(f"WordComposer 填充失败: {e}") from e

    # ── 格式规格加载 ──────────────────────────────────────────

    def _load_format_spec(self) -> Dict[str, Any]:
        """从 .cache/06_format/ 加载格式规格，失败则使用默认值。"""
        if self._format_spec is not None:
            return self._format_spec

        spec_paths = [
            ROOT / ".cache" / "06_format" / "format_spec.json",
            ROOT / ".cache" / "06_format" / "captured_styles.json",
        ]

        for spec_path in spec_paths:
            if spec_path.exists():
                try:
                    data = json.loads(spec_path.read_text(encoding="utf-8"))
                    if data:
                        self._format_spec = self._merge_format_spec(data)
                        return self._format_spec
                except Exception:
                    pass

        # 使用默认格式
        self._format_spec = DEFAULT_FORMAT
        return self._format_spec

    def _merge_format_spec(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """将 format_spec.json 的原始数据转换为 WordComposer 可以使用的格式。"""
        merged = dict(DEFAULT_FORMAT)  # 浅拷贝顶层，深层引用默认值

        # 深拷贝默认值以避免修改 DEFAULT_FORMAT
        import copy
        merged = copy.deepcopy(DEFAULT_FORMAT)

        # 尝试从 document_styles 提取
        ds = raw.get("document_styles", {})
        if ds:
            # 正文样式
            body_style = ds.get("body_style", {})
            body_para = ds.get("body_para_style", {})
            if body_style:
                merged["body"]["font_cjk"] = body_style.get("font_name_cjk", merged["body"]["font_cjk"])
                merged["body"]["font_latin"] = body_style.get("font_name_latin", merged["body"]["font_latin"])
                merged["body"]["font_size_pt"] = body_style.get("font_size_pt", merged["body"]["font_size_pt"])
                merged["body"]["bold"] = body_style.get("bold", merged["body"]["bold"])
            if body_para:
                merged["body"]["first_line_indent_cm"] = body_para.get(
                    "first_line_indent_cm", merged["body"]["first_line_indent_cm"]
                )
                merged["body"]["line_spacing"] = body_para.get(
                    "line_spacing", merged["body"]["line_spacing"]
                )
                merged["body"]["space_before_pt"] = body_para.get(
                    "space_before_pt", merged["body"]["space_before_pt"]
                )
                merged["body"]["space_after_pt"] = body_para.get(
                    "space_after_pt", merged["body"]["space_after_pt"]
                )

            # 标题样式
            heading_styles = ds.get("heading_styles", {})
            for level_str in ("1", "2"):
                hkey = f"h{level_str}"
                if level_str in heading_styles:
                    h_data = heading_styles[level_str]
                    if isinstance(h_data, list) and len(h_data) >= 1:
                        # (text_style, para_style) tuple
                        text_style = h_data[0] if isinstance(h_data[0], dict) else {}
                        para_style = h_data[1] if len(h_data) > 1 and isinstance(h_data[1], dict) else {}
                    elif isinstance(h_data, dict):
                        text_style = h_data
                        para_style = {}
                    else:
                        continue

                    if text_style:
                        merged["heading"][hkey]["font_cjk"] = text_style.get(
                            "font_name_cjk", merged["heading"][hkey]["font_cjk"]
                        )
                        merged["heading"][hkey]["font_latin"] = text_style.get(
                            "font_name_latin", merged["heading"][hkey]["font_latin"]
                        )
                        merged["heading"][hkey]["font_size_pt"] = text_style.get(
                            "font_size_pt", merged["heading"][hkey]["font_size_pt"]
                        )
                        merged["heading"][hkey]["bold"] = text_style.get(
                            "bold", merged["heading"][hkey]["bold"]
                        )
                    if para_style:
                        merged["heading"][hkey]["first_line_indent_cm"] = para_style.get(
                            "first_line_indent_cm", merged["heading"][hkey]["first_line_indent_cm"]
                        )
                        merged["heading"][hkey]["line_spacing"] = para_style.get(
                            "line_spacing", merged["heading"][hkey]["line_spacing"]
                        )
                        merged["heading"][hkey]["space_before_pt"] = para_style.get(
                            "space_before_pt", merged["heading"][hkey]["space_before_pt"]
                        )
                        merged["heading"][hkey]["space_after_pt"] = para_style.get(
                            "space_after_pt", merged["heading"][hkey]["space_after_pt"]
                        )

            # 表格样式
            table_style = ds.get("table_style", {})
            table_cell = ds.get("table_cell_style", {})
            if table_cell:
                merged["table"]["font_cjk"] = table_cell.get("font_name_cjk", merged["table"]["font_cjk"])
                merged["table"]["font_latin"] = table_cell.get("font_name_latin", merged["table"]["font_latin"])
                merged["table"]["font_size_pt"] = table_cell.get("font_size_pt", merged["table"]["font_size_pt"])

        return merged

    # ── 模板操作 ────────────────────────────────────────────

    def _open_template(self) -> None:
        """打开模板文档（使用已有的 Word 实例或创建新的）。"""
        if self.word is None:
            import win32com.client
            self.word = win32com.client.Dispatch("Word.Application")
            self.word.Visible = False
            self.word.DisplayAlerts = 0
            self.word.ScreenUpdating = False
        self.doc = self.word.Documents.Open(str(self.template_path))

    def _find_marker(self, text: str) -> bool:
        """
        在文档中搜索标记文本，将光标定位到该位置。

        Returns:
            True 找到, False 未找到
        """
        # 从文档开头开始搜索
        rng = self.doc.Range(0, 0)
        rng.Select()

        find = self.word.Selection.Find
        find.ClearFormatting()
        find.Text = text
        find.Forward = True
        find.Wrap = 0  # wdFindStop
        find.Format = False
        find.MatchCase = False
        find.MatchWholeWord = False

        return find.Execute()

    def _type_newline(self) -> None:
        """插入一个段落换行（Enter），不是分页符。"""
        self.word.Selection.TypeParagraph()

    def _move_to_end(self) -> None:
        """移动光标到文档末尾。"""
        self.word.Selection.EndKey(Unit=6)  # wdStory

    # ── 智能插入点查找 ──────────────────────────────────────

    def _find_summary_insertion_point(self, max_paragraphs: int = 10) -> Optional[str]:
        """
        在前 N 段内搜索总结性/概述性段落，返回段落文本作为 marker。

        用于在无法通过 insertion_plan 定位时，自动寻找合适的应答表插入点。
        """
        keywords = [
            "总体", "概述", "总结", "概要", "总述",
            "架构设计", "方案概述", "技术架构", "项目概述",
            "总体设计", "总体方案", "建设方案", "技术方案概述",
        ]
        count = min(max_paragraphs, self.doc.Paragraphs.Count)
        for i in range(1, count + 1):
            try:
                text = self.doc.Paragraphs(i).Range.Text.strip()
                if not text:
                    continue
                for kw in keywords:
                    if kw in text:
                        # 返回前 80 个字符作为 marker（过长的文本不利于 Find 精确匹配）
                        return text[:80]
            except Exception:
                continue
        return None

    def _find_section_by_keyword(self, keyword: str) -> Optional[Tuple[int, int]]:
        """
        在文档中搜索包含指定关键词的段落，返回 (段落索引, OutlineLevel)。

        用于定位"总体技术架构设计"等目标章节。
        """
        count = self.doc.Paragraphs.Count
        for i in range(1, count + 1):
            try:
                text = self.doc.Paragraphs(i).Range.Text.strip()
                if keyword in text:
                    level = self.doc.Paragraphs(i).OutlineLevel
                    return (i, level)
            except Exception:
                continue
        return None

    def _find_next_heading_same_level(
        self, start_idx: int, level: int
    ) -> Optional[int]:
        """
        从 start_idx+1 开始向后搜索，找到第一个同级或更高级标题。

        Word OutlineLevel:
          1=Heading1, 2=Heading2, ..., 9=Heading9, 10=BodyText

        返回值 ≤ level 表示同级或更高级标题（数值越小级别越高）。
        返回段落索引，找不到则返回 None（表示到文档末尾）。
        """
        count = self.doc.Paragraphs.Count
        for i in range(start_idx + 1, count + 1):
            try:
                para_level = self.doc.Paragraphs(i).OutlineLevel
                # 同级标题（level 相等）或更高级标题（数值更小）
                if para_level <= level and para_level < 10:
                    return i
            except Exception:
                continue
        return None  # 未找到 → 插入到文档末尾

    # ── DOCX 文件插入（移除分页符，改用换行） ────────────────

    def _insert_docx_at_marker(self, marker: str, docx_path: Path) -> bool:
        """
        在指定标记后插入另一个 DOCX 文件的内容。
        在内容前后使用换行（Enter），而非分页符。
        """
        if not docx_path.exists():
            print(f"    [WARN] 文件不存在: {docx_path}")
            return False

        found = self._find_marker(marker)

        if not found:
            print(f"    [WARN] 未找到标记 '{marker}'，在文档末尾插入")
            self._move_to_end()
        else:
            # 光标已在标记位置，移动到段落末尾
            try:
                self.word.Selection.MoveEnd(Unit=5)  # wdParagraph
                self.word.Selection.Collapse(Direction=0)  # wdCollapseEnd
            except Exception:
                pass

        # 用换行代替分页符
        self._type_newline()

        # 插入 DOCX 文件
        try:
            self.word.Selection.InsertFile(
                str(docx_path),
                Range="",
                ConfirmConversions=False,
                Link=False,
                Attachment=False,
            )
        except Exception as e:
            print(f"    [ERROR] 插入文件失败: {e}")
            return False

        self._type_newline()
        return True

    # ── 应答表智能插入（无标题、1:2:8:2 列宽比）────────────

    def _extract_table_from_response_docx(
        self,
        docx_path: Path,
        column_ratio: Tuple[int, ...] = (1, 2, 7, 2),
    ) -> Optional[Path]:
        """
        从应答表 DOCX 中提取表格，移除标题段落，按比例调整列宽。

        返回仅包含表格的临时 DOCX 路径（无题注/标题）。
        列宽按给定比例分配页面可用宽度。
        """
        try:
            from docx import Document as DocxDoc
            from docx.shared import Cm
            from docx.oxml.ns import qn
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from copy import deepcopy
        except ImportError:
            print("    [WARN] python-docx 未安装，无法提取表格")
            return None

        try:
            source_doc = DocxDoc(str(docx_path))
        except Exception as e:
            print(f"    [WARN] 无法打开应答表 DOCX: {e}")
            return None

        if not source_doc.tables:
            print("    [WARN] 应答表 DOCX 中未找到表格")
            return None

        source_table = source_doc.tables[0]

        # ── 计算列宽（基于页面可用宽度和比例）──
        section = source_doc.sections[0]
        page_width_cm = (section.page_width.cm if section.page_width else 29.7)
        margin_left_cm = (section.left_margin.cm if section.left_margin else 2.0)
        margin_right_cm = (section.right_margin.cm if section.right_margin else 2.0)
        usable_width_cm = page_width_cm - margin_left_cm - margin_right_cm
        total_ratio = sum(column_ratio)

        num_cols = len(source_table.columns)
        col_widths_cm = [
            usable_width_cm * column_ratio[j] / total_ratio
            for j in range(min(num_cols, len(column_ratio)))
        ]
        # 补全超出 ratio 定义的列（使用平均宽度）
        if num_cols > len(column_ratio):
            avg_width = usable_width_cm / num_cols
            col_widths_cm.extend([avg_width] * (num_cols - len(column_ratio)))

        # ── 创建仅含表格的临时文档 ──
        temp_doc = DocxDoc()
        temp_section = temp_doc.sections[0]
        temp_section.page_width = section.page_width
        temp_section.page_height = section.page_height
        temp_section.left_margin = section.left_margin
        temp_section.right_margin = section.right_margin
        temp_section.top_margin = Cm(1.0)
        temp_section.bottom_margin = Cm(1.0)

        # 深拷贝表格 XML 元素以保留全部格式
        table_element = deepcopy(source_table._element)
        temp_doc.element.body.append(table_element)

        # ── 调整列宽 ──
        new_table = temp_doc.tables[0]
        new_table.autofit = False
        new_table.alignment = WD_ALIGN_PARAGRAPH.CENTER

        for row in new_table.rows:
            for j in range(num_cols):
                try:
                    row.cells[j].width = Cm(col_widths_cm[j])
                except Exception:
                    pass

        # ── 确保单元格内容左对齐（表头居中）──
        for i, row in enumerate(new_table.rows):
            for j, cell in enumerate(row.cells):
                for para in cell.paragraphs:
                    if i == 0 and j == 0:
                        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    elif j == 0:
                        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    else:
                        para.alignment = WD_ALIGN_PARAGRAPH.LEFT

        # ── 保存临时文件 ──
        tmp_path = Path(tempfile.mktemp(suffix=".docx"))
        temp_doc.save(str(tmp_path))
        return tmp_path

    def _insert_response_table_at_section_end(
        self,
        section_keyword: str,
        response_docx_path: Path,
        column_ratio: Tuple[int, ...] = (1, 2, 7, 2),
    ) -> bool:
        """
        智能插入应答表：找到目标章节末尾，在下一个同级标题之前插入。

        算法：
        1. 在文档中搜索包含 section_keyword 的段落
        2. 确定其 OutlineLevel
        3. 向后查找下一个同级或更高级标题
        4. 在该标题之前（即目标章节末尾）插入无标题表格

        Args:
            section_keyword: 目标章节关键词（如"总体技术架构设计"）
            response_docx_path: 应答表 DOCX 文件路径
            column_ratio: 表格列宽比例，默认 1:2:8:2

        Returns:
            True 插入成功, False 失败（调用方应尝试下一个关键词或回退方案）
        """
        if not response_docx_path.exists():
            return False

        # Step 1: 查找目标章节
        found = self._find_section_by_keyword(section_keyword)
        if found is None:
            return False

        para_idx, outline_level = found
        print(f"    WordComposer: 找到目标章节 '{section_keyword}' → 第 {para_idx} 段 "
              f"(OutlineLevel={outline_level})")

        # Step 2: 查找下一个同级/更高级标题
        next_heading_idx = self._find_next_heading_same_level(para_idx, outline_level)

        # Step 3: 提取无标题表格（按指定列宽比）
        table_docx_path = self._extract_table_from_response_docx(
            response_docx_path, column_ratio
        )
        if table_docx_path is None:
            return False

        try:
            if next_heading_idx is not None:
                # 在下一个标题之前插入
                # 定位到 next_heading_idx - 1 段落的末尾
                insert_after_idx = next_heading_idx - 1
                if insert_after_idx < 1:
                    insert_after_idx = para_idx

                print(f"    WordComposer: 在段落 {insert_after_idx} 末尾插入应答表 "
                      f"(下一标题: 第 {next_heading_idx} 段)")

                para_range = self.doc.Paragraphs(insert_after_idx).Range
                para_range.Collapse(Direction=0)  # wdCollapseEnd
                para_range.Select()
            else:
                # 未找到下一标题 → 插入到文档末尾
                print(f"    WordComposer: 未找到下一标题，在文档末尾插入应答表")
                self._move_to_end()

            # 插入换行再插入表格文件
            self._type_newline()
            self.word.Selection.InsertFile(
                str(table_docx_path),
                Range="",
                ConfirmConversions=False,
                Link=False,
                Attachment=False,
            )
            self._type_newline()

            print(f"    WordComposer: 应答表插入成功 (列宽比 "
                  f"{':'.join(str(r) for r in column_ratio)})")
            return True

        except Exception as e:
            print(f"    [WARN] 应答表章节插入失败: {e}")
            return False
        finally:
            # 清理临时文件
            if table_docx_path and table_docx_path.exists():
                try:
                    table_docx_path.unlink()
                except Exception:
                    pass

    # ── 格式化 Markdown 插入 ──────────────────────────────────

    def _insert_markdown_at_marker(self, marker: str, md_path: Path) -> bool:
        """
        在指定标记后插入格式化的 Markdown 内容。

        处理逻辑：
        1. 检测并累积表格行（|...| 格式）
        2. 检测标题（# 或 x.x.x 格式），应用标题格式
        3. 检测列表（-/* 开头），应用正文格式 + 悬挂缩进
        4. 其余为正文段落，应用正文格式
        5. 跳过空行和 --- 分隔线
        6. 所有元素间使用 Enter 换行，不使用分页符
        """
        if not md_path.exists():
            print(f"    [WARN] 文件不存在: {md_path}")
            return False

        # 定位
        found = self._find_marker(marker)
        if not found:
            print(f"    [WARN] 未找到标记 '{marker}'，在文档末尾插入")
            self._move_to_end()
        else:
            try:
                self.word.Selection.MoveEnd(Unit=5)
                self.word.Selection.Collapse(Direction=0)
            except Exception:
                pass

        self._type_newline()

        # 确保格式已加载
        fmt = self._load_format_spec()

        # 读取并解析 Markdown
        lines = md_path.read_text(encoding="utf-8").split("\n")
        self._process_markdown_lines(lines, fmt)

        self._type_newline()
        return True

    def _process_markdown_lines(
        self, lines: List[str], fmt: Dict[str, Any]
    ) -> None:
        """逐行处理 Markdown，分发到对应的插入方法。"""
        table_buffer: List[str] = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # ── 空行：刷新表格缓冲，然后跳过 ──
            if not line.strip():
                if table_buffer:
                    self._flush_table(table_buffer, fmt)
                    table_buffer = []
                i += 1
                continue

            # ── 表格行（|...| 格式） ──
            if self.TABLE_ROW_PATTERN.match(line.strip()):
                table_buffer.append(line)
                i += 1
                continue

            # ── 非表格行：先刷新表格缓冲 ──
            if table_buffer:
                self._flush_table(table_buffer, fmt)
                table_buffer = []

            # ── 分隔线（---）→ 跳过 ──
            if line.strip() == "---" or line.strip() == "***":
                self._type_newline()
                i += 1
                continue

            # ── 纯数字或符号行 → 跳过 ──
            if re.match(r'^[\d\s\-_=#*]+$', line.strip()) and len(line.strip()) > 5:
                i += 1
                continue

            # ── Markdown 标题（# ...） ──
            md_heading = self.HEADING_MD_PATTERN.match(line)
            if md_heading:
                level = len(md_heading.group(1))
                text = md_heading.group(2).strip()
                # 移除内联加粗/斜体标记
                text = self._strip_inline_markers(text)
                heading_level = min(level, 2)
                self._insert_formatted_heading(text, heading_level, fmt)
                i += 1
                continue

            # ── 数字标题（x.x.x ...） ──
            num_heading = self.HEADING_NUM_PATTERN.match(line.strip())
            if num_heading:
                # 数字部分 + 标题文本
                num_part = num_heading.group(1)
                text_part = num_heading.group(2).strip()
                text_part = self._strip_inline_markers(text_part)
                full_text = f"{num_part} {text_part}"
                # 根据层级深度确定 heading level
                dot_count = num_part.count(".")
                heading_level = 1 if dot_count <= 2 else 2
                self._insert_formatted_heading(full_text, heading_level, fmt)
                i += 1
                continue

            # ── 列表项 ──
            list_match = self.LIST_PATTERN.match(line) or self.ORDERED_LIST_PATTERN.match(line)
            if list_match:
                text = list_match.group(2).strip()
                text = self._strip_inline_markers(text)
                self._insert_formatted_list(text, fmt)
                i += 1
                continue

            # ── 默认：正文段落 ──
            clean_text = self._strip_inline_markers(line.strip())
            if clean_text:
                self._insert_formatted_body(clean_text, fmt)

            i += 1

        # ── 处理末尾可能残留的表格缓冲 ──
        if table_buffer:
            self._flush_table(table_buffer, fmt)

    def _strip_inline_markers(self, text: str) -> str:
        """移除 Markdown 内联格式标记（**bold**, *italic*, `code`）。"""
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'`(.+?)`', r'\1', text)
        text = re.sub(r'~~(.+?)~~', r'\1', text)
        return text

    # ── 格式化段落插入（COM） ─────────────────────────────────

    def _apply_body_format_to_selection(self, fmt: Dict[str, Any]) -> None:
        """将 Selection 的字体和段落格式设置为正文样式。"""
        b = fmt["body"]
        sel = self.word.Selection

        # 字体
        sel.Font.Name = b["font_cjk"]
        try:
            sel.Font.NameFarEast = b["font_cjk"]
        except Exception:
            pass
        sel.Font.NameAscii = b["font_latin"]
        sel.Font.Size = b["font_size_pt"]
        sel.Font.Bold = b["bold"]

        # 段落格式
        pf = sel.ParagraphFormat
        try:
            pf.FirstLineIndent = self.word.CentimetersToPoints(b["first_line_indent_cm"])
        except Exception:
            pass
        pf.LineSpacingRule = 0  # wdLineSpaceMultiple
        line_spacing = b["line_spacing"]
        if not (0.5 <= line_spacing <= 10.0):
            print(f"    [WARN] WordComposer._apply_body_format_to_selection: "
                  f"行距 {line_spacing} 异常，已修正为默认值 1.5")
            line_spacing = 1.5
        pf.LineSpacing = line_spacing
        try:
            pf.SpaceBefore = b["space_before_pt"]
            pf.SpaceAfter = b["space_after_pt"]
        except Exception:
            pass
        pf.Alignment = b["alignment"]

    def _apply_heading_format_to_selection(
        self, level: int, fmt: Dict[str, Any]
    ) -> None:
        """将 Selection 的字体和段落格式设置为标题样式。"""
        hkey = f"h{min(level, 2)}"
        h = fmt["heading"][hkey]
        sel = self.word.Selection

        # 字体
        sel.Font.Name = h["font_cjk"]
        try:
            sel.Font.NameFarEast = h["font_cjk"]
        except Exception:
            pass
        sel.Font.NameAscii = h["font_latin"]
        sel.Font.Size = h["font_size_pt"]
        sel.Font.Bold = h["bold"]

        # 段落格式（标题不首行缩进）
        pf = sel.ParagraphFormat
        pf.FirstLineIndent = 0
        pf.LineSpacingRule = 0
        h_line_spacing = h["line_spacing"]
        if not (0.5 <= h_line_spacing <= 10.0):
            print(f"    [WARN] WordComposer._apply_heading_format_to_selection: "
                  f"行距 {h_line_spacing} 异常，已修正为默认值 1.5")
            h_line_spacing = 1.5
        pf.LineSpacing = h_line_spacing
        try:
            pf.SpaceBefore = h["space_before_pt"]
            pf.SpaceAfter = h["space_after_pt"]
        except Exception:
            pass
        pf.Alignment = h["alignment"]

    def _apply_caption_format_to_selection(self, fmt: Dict[str, Any]) -> None:
        """将 Selection 的格式设置为题注样式。"""
        c = fmt["caption"]
        sel = self.word.Selection

        sel.Font.Name = c["font_cjk"]
        try:
            sel.Font.NameFarEast = c["font_cjk"]
        except Exception:
            pass
        sel.Font.NameAscii = c["font_latin"]
        sel.Font.Size = c["font_size_pt"]
        sel.Font.Bold = c["bold"]
        pf = sel.ParagraphFormat
        pf.Alignment = c["alignment"]
        pf.FirstLineIndent = 0

    def _insert_formatted_body(self, text: str, fmt: Dict[str, Any]) -> None:
        """以正文格式插入一段文本。"""
        self._apply_body_format_to_selection(fmt)
        self.word.Selection.TypeText(text)
        self._type_newline()

    def _insert_formatted_heading(
        self, text: str, level: int, fmt: Dict[str, Any]
    ) -> None:
        """以标题格式插入标题文本。"""
        self._apply_heading_format_to_selection(level, fmt)
        self.word.Selection.TypeText(text)
        self._type_newline()

    def _insert_formatted_list(self, text: str, fmt: Dict[str, Any]) -> None:
        """以正文格式插入列表项（悬挂缩进）。"""
        self._apply_body_format_to_selection(fmt)
        # 列表项使用悬挂缩进（左缩进而非首行缩进）
        pf = self.word.Selection.ParagraphFormat
        try:
            pf.FirstLineIndent = self.word.CentimetersToPoints(-0.37)
            pf.LeftIndent = self.word.CentimetersToPoints(0.74)
        except Exception:
            pass
        self.word.Selection.TypeText(text)
        self._type_newline()

    # ── 表格处理 ──────────────────────────────────────────────

    def _flush_table(self, rows: List[str], fmt: Dict[str, Any]) -> None:
        """
        将累积的 Markdown 表格行转换为 Word 表格并插入。

        使用 python-docx 创建临时 DOCX（含题注+表格），
        然后通过 COM InsertFile 插入。
        """
        parsed = self._parse_markdown_table(rows)
        if not parsed or len(parsed) < 1:
            return

        header_row = parsed[0]
        data_rows = parsed[1:] if len(parsed) > 1 else []

        # 用第一行数据生成题注摘要
        caption_text = self._generate_table_caption(header_row, data_rows)

        try:
            tmp_path = self._create_table_docx(header_row, data_rows, caption_text, fmt)
            if tmp_path and tmp_path.exists():
                self.word.Selection.InsertFile(
                    str(tmp_path),
                    Range="",
                    ConfirmConversions=False,
                    Link=False,
                    Attachment=False,
                )
                self._type_newline()
                # 清理临时文件
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
        except Exception as e:
            # 回退：以格式化文本方式插入表格内容
            print(f"    [WARN] 表格插入失败，回退到文本模式: {e}")
            self._insert_table_as_text(header_row, data_rows, caption_text, fmt)

    def _parse_markdown_table(
        self, rows: List[str]
    ) -> List[List[str]]:
        """
        解析 Markdown 表格行。

        Args:
            rows: 形如 ["| A | B |", "|---|---|", "| 1 | 2 |"] 的行列表

        Returns:
            [[cell, cell, ...], ...] — 已移除分隔行，trim 每个单元格
        """
        result = []
        for row in rows:
            stripped = row.strip()
            if self.TABLE_SEP_PATTERN.match(stripped):
                continue  # 跳过分隔行
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if cells:
                result.append(cells)
        return result

    def _generate_table_caption(
        self, header_row: List[str], data_rows: List[List[str]]
    ) -> str:
        """生成表格题注文字。"""
        self._table_counter += 1
        seq = self._table_counter

        # 尝试从表头和数据中生成摘要
        if header_row:
            header_text = " ".join(h for h in header_row if h)[:30]
        else:
            header_text = "数据表"

        # 从数据第一行提取主题词
        if data_rows and data_rows[0]:
            sample = data_rows[0][0] if data_rows[0] else ""
        else:
            sample = ""

        if sample and len(sample) < 20:
            caption = f"表{seq} {sample}{header_text}"
        else:
            caption = f"表{seq} {header_text}"

        return caption[:60]  # 限制长度

    def _create_table_docx(
        self,
        header_row: List[str],
        data_rows: List[List[str]],
        caption_text: str,
        fmt: Dict[str, Any],
    ) -> Optional[Path]:
        """
        使用 python-docx 创建包含格式化表格和题注的临时 DOCX。

        Returns:
            临时文件路径，失败时返回 None
        """
        try:
            from docx import Document
            from docx.shared import Cm, Pt, RGBColor
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.enum.table import WD_ALIGN_VERTICAL
            from docx.oxml import OxmlElement
            from docx.oxml.ns import qn
        except ImportError:
            print("    [WARN] python-docx 未安装，无法创建格式化表格")
            return None

        doc = Document()

        # ── 页面设置 ──
        section = doc.sections[0]
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

        # ── 题注段落 ──
        caption_para = doc.add_paragraph()
        caption_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        caption_para.paragraph_format.space_after = Pt(6)
        caption_para.paragraph_format.first_line_indent = Cm(0)
        caption_run = caption_para.add_run(caption_text)
        caption_run.font.size = Pt(fmt["caption"]["font_size_pt"])
        caption_run.font.name = fmt["caption"]["font_latin"]
        try:
            caption_run.font.element.rPr.rFonts.set(qn('w:eastAsia'), fmt["caption"]["font_cjk"])
        except Exception:
            pass

        # ── 创建表格 ──
        num_rows = len(data_rows) + 1  # +1 for header
        num_cols = len(header_row)
        table = doc.add_table(rows=num_rows, cols=num_cols)
        table.autofit = True

        # 表格水平居中
        table.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # 表头行
        for j, cell_text in enumerate(header_row):
            cell = table.rows[0].cells[j]
            cell.text = ""
            run = cell.paragraphs[0].add_run(cell_text)
            run.bold = True
            run.font.size = Pt(fmt["table"]["font_size_pt"])
            run.font.name = fmt["table"]["font_latin"]
            try:
                run.font.element.rPr.rFonts.set(qn('w:eastAsia'), fmt["table"]["font_cjk"])
            except Exception:
                pass
            # 单元格水平居中 + 垂直居中
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            try:
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            except Exception:
                pass

        # 数据行
        for i, row_data in enumerate(data_rows):
            row = table.rows[i + 1]
            for j, cell_text in enumerate(row_data):
                # 补齐列数不足的情况
                if j >= num_cols:
                    break
                cell = row.cells[j]
                cell.text = ""
                run = cell.paragraphs[0].add_run(cell_text[:500])
                run.font.size = Pt(fmt["table"]["font_size_pt"])
                run.font.name = fmt["table"]["font_latin"]
                try:
                    run.font.element.rPr.rFonts.set(qn('w:eastAsia'), fmt["table"]["font_cjk"])
                except Exception:
                    pass
                cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                try:
                    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                except Exception:
                    pass

        # 补齐不足的列（如果数据行列数少于表头）
        for row in table.rows:
            while len(row.cells) < num_cols:
                row.add_cell()

        # ── 应用三线表边框 ──
        self._apply_three_line_borders_docx(table)

        # ── 设置表格内边距 ──
        for row in table.rows:
            for cell in row.cells:
                try:
                    tc_pr = cell._tc.get_or_add_tcPr()
                    tc_mar = OxmlElement('w:tcMar')
                    for side in ('top', 'start', 'bottom', 'end'):
                        node = OxmlElement(f'w:{side}')
                        node.set(qn('w:w'), '28')  # ~0.5mm
                        node.set(qn('w:type'), 'dxa')
                        tc_mar.append(node)
                    tc_pr.append(tc_mar)
                except Exception:
                    pass

        # ── 保存到临时文件 ──
        tmp_path = Path(tempfile.mktemp(suffix=".docx"))
        doc.save(str(tmp_path))
        return tmp_path

    def _apply_three_line_borders_docx(self, table) -> None:
        """对 python-docx 表格应用三线表边框。"""
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Pt

        tbl = table._tbl
        tbl_pr = tbl.tblPr if tbl.tblPr is not None else OxmlElement('w:tblPr')

        borders = OxmlElement('w:tblBorders')

        # 顶部粗线 1.5pt
        top = OxmlElement('w:top')
        top.set(qn('w:val'), 'single')
        top.set(qn('w:sz'), '12')  # 1.5pt = 12 eighths
        top.set(qn('w:space'), '0')
        top.set(qn('w:color'), '000000')
        borders.append(top)

        # 底部粗线 1.5pt
        bottom = OxmlElement('w:bottom')
        bottom.set(qn('w:val'), 'single')
        bottom.set(qn('w:sz'), '12')
        bottom.set(qn('w:space'), '0')
        bottom.set(qn('w:color'), '000000')
        borders.append(bottom)

        # 内部水平细线 0.5pt
        inside_h = OxmlElement('w:insideH')
        inside_h.set(qn('w:val'), 'single')
        inside_h.set(qn('w:sz'), '4')  # 0.5pt = 4 eighths
        inside_h.set(qn('w:space'), '0')
        inside_h.set(qn('w:color'), '000000')
        borders.append(inside_h)

        # 无竖线
        inside_v = OxmlElement('w:insideV')
        inside_v.set(qn('w:val'), 'none')
        inside_v.set(qn('w:sz'), '0')
        inside_v.set(qn('w:space'), '0')
        inside_v.set(qn('w:color'), 'auto')
        borders.append(inside_v)

        # 左右无边框
        left = OxmlElement('w:left')
        left.set(qn('w:val'), 'none')
        left.set(qn('w:sz'), '0')
        left.set(qn('w:space'), '0')
        left.set(qn('w:color'), 'auto')
        borders.append(left)

        right = OxmlElement('w:right')
        right.set(qn('w:val'), 'none')
        right.set(qn('w:sz'), '0')
        right.set(qn('w:space'), '0')
        right.set(qn('w:color'), 'auto')
        borders.append(right)

        tbl_pr.append(borders)

    def _insert_table_as_text(
        self,
        header_row: List[str],
        data_rows: List[List[str]],
        caption_text: str,
        fmt: Dict[str, Any],
    ) -> None:
        """回退方案：以格式化文本方式插入表格内容。"""
        # 题注
        self._apply_caption_format_to_selection(fmt)
        self.word.Selection.TypeText(caption_text)
        self._type_newline()

        # 表头
        self._apply_heading_format_to_selection(2, fmt)
        self.word.Selection.TypeText(" | ".join(header_row))
        self._type_newline()

        # 分隔线
        self._apply_body_format_to_selection(fmt)
        self.word.Selection.TypeText("-" * 60)
        self._type_newline()

        # 数据行
        for row in data_rows:
            self._apply_body_format_to_selection(fmt)
            self.word.Selection.TypeText(" | ".join(row))
            self._type_newline()

    # ── 页码 ──────────────────────────────────────────────────

    def _add_page_numbers(self) -> None:
        """添加页码。"""
        try:
            for section in self.doc.Sections:
                footer = section.Footers(1)  # wdHeaderFooterPrimary
                footer.LinkToPrevious = False
                footer.PageNumbers.Add(2)  # wdAlignPageNumberCenter
        except Exception:
            pass

    # ── 保存与清理 ────────────────────────────────────────────

    def _save(self) -> None:
        """保存文档。"""
        if self.output_path.exists():
            try:
                self.output_path.unlink()
            except Exception:
                pass
        self.doc.SaveAs(str(self.output_path), FileFormat=16)

    def _cleanup(self) -> None:
        """清理 Word 进程。"""
        if self.doc is not None:
            try:
                self.doc.Close(SaveChanges=0)
            except Exception:
                pass
        if self.word is not None:
            try:
                self.word.ScreenUpdating = True
                self.word.Quit()
            except Exception:
                pass
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

def compose_bid_document(
    template_path: Path,
    output_path: Path,
    response_table_path: Optional[Path] = None,
    technical_draft_path: Optional[Path] = None,
    strategy_name: str = "",
) -> Path:
    """快速填充投标模板。"""
    composer = WordComposer(template_path, output_path)
    return composer.compose(
        response_table_path=response_table_path,
        technical_draft_path=technical_draft_path,
        strategy_name=strategy_name,
    )
