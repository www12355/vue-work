"""
DOCX 导出器 — 将 Markdown 标书转换为符合中文投标文档排版规范的 .docx 文件。

排版规范：
- 页面：A4, 页边距 2.5cm
- 一级标题：黑体 16pt 加粗居中
- 二级标题：黑体 14pt 加粗左对齐
- 三级标题：宋体 12pt 加粗左对齐
- 正文：宋体 11pt, 首行缩进 2 字符, 1.5 倍行距
- 表格：三线表格式
- 英文/数字：Times New Roman

用法:
    from lib.docx_exporter import DocxExporter
    exporter = DocxExporter(output_path)
    exporter.export_from_markdown(md_path, metadata)
"""

from __future__ import annotations

import sys
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from docx import Document
from docx.shared import Cm, Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn, nsdecls
# parse_xml not needed — using OxmlElement for XML construction


# ═══════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════

# 页面设置
PAGE_WIDTH_CM = 21.0
PAGE_HEIGHT_CM = 29.7
MARGIN_CM = 2.5

# 字体
FONT_CJK = "宋体"
FONT_CJK_HEADING = "黑体"  # SimHei
FONT_LATIN = "Times New Roman"

# 字号
SIZE_H1 = Pt(16)
SIZE_H2 = Pt(14)
SIZE_H3 = Pt(12)
SIZE_BODY = Pt(11)
SIZE_TABLE = Pt(10)

# 行距
LINE_SPACING = 1.5


# ═══════════════════════════════════════════════════════════════
# 导出器
# ═══════════════════════════════════════════════════════════════

class DocxExporter:
    """Markdown → DOCX 转换器（中文投标文档风格）。"""

    def __init__(self):
        self.doc: Optional[Document] = None
        self._para_idx = 0

    # ── 主入口 ──────────────────────────────────────────────

    def export_from_markdown(
        self,
        md_path: Path,
        output_path: Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """
        将 Markdown 文件转换为 .docx。

        Args:
            md_path: 输入 .md 文件路径
            output_path: 输出 .docx 文件路径
            metadata: 文档元数据（标题、公司名等，可选）

        Returns:
            输出文件路径
        """
        md_text = Path(md_path).read_text(encoding="utf-8")
        return self.export_from_text(md_text, output_path, metadata)

    def export_from_text(
        self,
        md_text: str,
        output_path: Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """
        将 Markdown 文本转换为 .docx。

        Args:
            md_text: Markdown 文本内容
            output_path: 输出 .docx 文件路径
            metadata: 文档元数据

        Returns:
            输出文件路径
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self.doc = Document()
        self._para_idx = 0
        meta = metadata or {}

        # 页面设置
        self._setup_page()

        # 设置默认样式
        self._setup_styles()

        # 逐行渲染
        lines = md_text.split("\n")
        i = 0
        in_table = False
        table_lines: List[str] = []

        while i < len(lines):
            line = lines[i]

            # 表格检测（以 | 开头和结尾）
            if line.strip().startswith("|") and line.strip().endswith("|"):
                if not in_table:
                    in_table = True
                    table_lines = []
                table_lines.append(line)
                i += 1
                continue
            elif in_table:
                # 表格结束
                self._render_table(table_lines)
                table_lines = []
                in_table = False
                # 继续处理当前行

            # 分页符
            if line.strip() == "---":
                self._add_page_break()
                i += 1
                continue

            # 空行
            if not line.strip():
                i += 1
                continue

            # 标题 — Markdown # 风格
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2).strip()
                self._render_heading(text, level)
                i += 1
                continue

            # 标题 — 数字编号风格（如 13.1、13.2.1.3）
            numbered_heading_match = re.match(r'^(\d+(?:\.\d+)+)\s+(.+)', line.strip())
            if numbered_heading_match:
                num_part = numbered_heading_match.group(1)
                rest_text = numbered_heading_match.group(2).strip()
                dot_count = num_part.count(".")
                # 1个点→H2, 2个点→H3, 3+个点→H4
                if dot_count == 1:
                    level = 2
                elif dot_count == 2:
                    level = 3
                else:
                    level = 4
                full_text = f"{num_part} {rest_text}"
                self._render_heading(full_text, level)
                i += 1
                continue

            # 无序列表
            list_match = re.match(r"^(\s*)[-*+]\s+(.+)$", line)
            if list_match:
                text = list_match.group(2).strip()
                self._render_list_item(text, ordered=False)
                i += 1
                continue

            # 有序列表
            ordered_match = re.match(r"^(\s*)\d+[.)]\s+(.+)$", line)
            if ordered_match:
                text = ordered_match.group(2).strip()
                self._render_list_item(text, ordered=True)
                i += 1
                continue

            # 普通段落
            self._render_paragraph(line)
            i += 1

        # 处理末尾的表格
        if in_table and table_lines:
            self._render_table(table_lines)

        # 添加页码
        self._add_page_numbers()

        # 保存
        self.doc.save(str(output_path))
        print(f"    [DOCX] 导出完成: {output_path} ({output_path.stat().st_size} 字节)")
        return output_path

    # ── 页面设置 ────────────────────────────────────────────

    def _setup_page(self) -> None:
        """设置 A4 页面和页边距。"""
        for section in self.doc.sections:
            section.page_width = Cm(PAGE_WIDTH_CM)
            section.page_height = Cm(PAGE_HEIGHT_CM)
            section.top_margin = Cm(MARGIN_CM)
            section.bottom_margin = Cm(MARGIN_CM)
            section.left_margin = Cm(MARGIN_CM)
            section.right_margin = Cm(MARGIN_CM)

    def _setup_styles(self) -> None:
        """设置文档默认样式。"""
        style = self.doc.styles["Normal"]
        font = style.font
        font.name = FONT_LATIN
        font.size = SIZE_BODY
        style.element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CJK)

        pf = style.paragraph_format
        pf.line_spacing = LINE_SPACING
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)

    # ── 标题 ────────────────────────────────────────────────

    def _render_heading(self, text: str, level: int) -> None:
        """渲染标题，应用正确的段落格式（无首行缩进，适当段间距）。"""
        para = self.doc.add_paragraph()
        self._para_idx += 1

        # 处理加粗标记
        text = self._strip_markdown_format(text)

        run = para.add_run(text)

        if level == 1:
            run.font.size = SIZE_H1
            run.font.name = FONT_LATIN
            run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CJK_HEADING)
            run.bold = True
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif level == 2:
            run.font.size = SIZE_H2
            run.font.name = FONT_LATIN
            run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CJK_HEADING)
            run.bold = True
        elif level == 3:
            run.font.size = SIZE_H3
            run.font.name = FONT_LATIN
            run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CJK_HEADING)
            run.bold = True
        else:
            # level 4+: 黑体加粗，同三级字号
            run.font.size = SIZE_H3  # 12pt
            run.font.name = FONT_LATIN
            run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CJK_HEADING)
            run.bold = True

        # ── 段落格式：标题不缩进，1.5倍行距 ──
        pf = para.paragraph_format
        pf.first_line_indent = Cm(0)  # 标题无首行缩进
        pf.line_spacing = LINE_SPACING
        # 大标题（level 1-2）段前段后各1行(≈12pt)，小标题（level 3+）段前段后各0.5行(≈6pt)
        pf.space_before = Pt(12) if level <= 2 else Pt(6)
        pf.space_after = Pt(12) if level <= 2 else Pt(6)

    # ── 段落 ────────────────────────────────────────────────

    def _render_paragraph(self, text: str) -> None:
        """渲染普通段落（首行缩进 2 字符）。"""
        para = self.doc.add_paragraph()
        self._para_idx += 1

        # 解析 **加粗** 内联格式
        parts = self._parse_inline_format(text)
        for part_text, is_bold in parts:
            run = para.add_run(part_text)
            run.font.name = FONT_LATIN
            run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CJK)
            run.font.size = SIZE_BODY
            if is_bold:
                run.bold = True

        pf = para.paragraph_format
        pf.first_line_indent = Cm(0.74)  # 2 字符缩进
        pf.line_spacing = LINE_SPACING
        pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    # ── 列表 ────────────────────────────────────────────────

    def _render_list_item(self, text: str, ordered: bool = False) -> None:
        """渲染列表项。"""
        para = self.doc.add_paragraph()
        self._para_idx += 1

        # 从 Markdown 文本中移除加粗标记
        clean_text = self._strip_markdown_format(text)

        run = para.add_run(clean_text)
        run.font.name = FONT_LATIN
        run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CJK)
        run.font.size = SIZE_BODY

        pf = para.paragraph_format
        pf.left_indent = Cm(0.74)
        pf.first_line_indent = Cm(-0.37)
        pf.line_spacing = LINE_SPACING

    # ── 表格（三线表） ──────────────────────────────────────

    def _render_table(self, md_lines: List[str]) -> None:
        """渲染 Markdown 表格为 Word 三线表。"""
        # 解析 Markdown 表格
        rows_data = []
        for line in md_lines:
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.split("|")[1:-1]]
            # 跳过 Markdown 表头分隔线，如 | --- | :---: |
            if self._is_markdown_table_separator(cells):
                continue
            if cells:
                rows_data.append(cells)

        if not rows_data:
            return

        # 确保每行列数一致
        max_cols = max(len(r) for r in rows_data)
        for r in rows_data:
            while len(r) < max_cols:
                r.append("")

        # 创建 Word 表格
        table = self.doc.add_table(rows=len(rows_data), cols=max_cols)
        table.autofit = True

        for i, row_data in enumerate(rows_data):
            row = table.rows[i]
            for j, cell_text in enumerate(row_data):
                cell = row.cells[j]
                cell.text = ""

                # 写单元格内容
                para = cell.paragraphs[0]
                run = para.add_run(cell_text)
                run.font.name = FONT_LATIN
                run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CJK)
                run.font.size = SIZE_TABLE

                if i == 0:
                    run.bold = True
                    para.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # 三线表边框
        self._apply_three_line_borders(table)

        self.doc.add_paragraph()  # 表后空行

    def _apply_three_line_borders(self, table) -> None:
        """应用三线表格式：表头线粗、分隔线细、底线粗。"""
        tbl = table._element
        tbl_pr = tbl.tblPr

        # 清除默认边框
        for existing in tbl_pr.findall(qn("w:tblBorders")):
            tbl_pr.remove(existing)

        borders = OxmlElement("w:tblBorders")

        # 顶线 — 粗 1.5pt
        top = OxmlElement("w:top")
        top.set(qn("w:val"), "single")
        top.set(qn("w:sz"), "12")  # 1.5pt = 12 eighths
        top.set(qn("w:space"), "0")
        top.set(qn("w:color"), "000000")
        borders.append(top)

        # 底线 — 粗 1.5pt
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "12")
        bottom.set(qn("w:space"), "0")
        bottom.set(qn("w:color"), "000000")
        borders.append(bottom)

        # 内部水平线 — 细 0.5pt
        inside_h = OxmlElement("w:insideH")
        inside_h.set(qn("w:val"), "single")
        inside_h.set(qn("w:sz"), "4")  # 0.5pt = 4 eighths
        inside_h.set(qn("w:space"), "0")
        inside_h.set(qn("w:color"), "000000")
        borders.append(inside_h)

        tbl_pr.append(borders)

    # ── 分页 ────────────────────────────────────────────────

    def _add_page_break(self) -> None:
        """添加分页符。"""
        para = self.doc.add_paragraph()
        run = para.add_run()
        run._element.append(OxmlElement("w:br"))
        run._element[-1].set(qn("w:type"), "page")

    # ── 页码 ────────────────────────────────────────────────

    def _add_page_numbers(self) -> None:
        """在所有节的页脚添加居中页码。"""
        for section in self.doc.sections:
            footer = section.footer
            footer.is_linked_to_previous = False
            para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER

            # 页码域代码
            run = para.add_run()
            fld_char_begin = OxmlElement("w:fldChar")
            fld_char_begin.set(qn("w:fldCharType"), "begin")
            run._element.append(fld_char_begin)

            run2 = para.add_run()
            instr = OxmlElement("w:instrText")
            instr.text = " PAGE "
            run2._element.append(instr)

            run3 = para.add_run()
            fld_char_end = OxmlElement("w:fldChar")
            fld_char_end.set(qn("w:fldCharType"), "end")
            run3._element.append(fld_char_end)

    # ── 辅助方法 ────────────────────────────────────────────

    @staticmethod
    def _strip_markdown_format(text: str) -> str:
        """移除 Markdown 内联格式标记。"""
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"`(.+?)`", r"\1", text)
        return text

    @staticmethod
    def _parse_inline_format(text: str) -> List[tuple]:
        """解析内联格式，返回 [(text, is_bold), ...]。
        支持 **加粗** 和 *斜体*（斜体暂不特殊处理）。"""
        parts = []
        pattern = re.compile(r"(\*\*(.+?)\*\*|\*(.+?)\*)")
        last_end = 0
        for m in pattern.finditer(text):
            if m.start() > last_end:
                parts.append((text[last_end:m.start()], False))
            if m.group(2):  # **加粗**
                parts.append((m.group(2), True))
            elif m.group(3):  # *斜体*
                parts.append((m.group(3), False))
            last_end = m.end()
        if last_end < len(text):
            parts.append((text[last_end:], False))
        if not parts:
            parts.append((text, False))
        return parts


    # ── 模板创建（Stage 7-8 使用） ──────────────────────────

    @staticmethod
    def create_template_from_spec(styles: Any) -> Document:
        """
        根据 FormatSpec/DocumentStyles 创建空白 DOCX 模板。

        Args:
            styles: DocumentStyles 对象（来自 format_adapter.py）

        Returns:
            配置好样式的 python-docx Document 对象
        """
        doc = Document()
        DocxExporter.apply_document_styles(doc, styles)
        return doc

    @staticmethod
    def apply_document_styles(doc: Document, styles: Any) -> None:
        """
        将捕获的 DocumentStyles 应用到已有 Document。

        更新 Normal 样式、创建/修改 Heading 1-3 样式、设置页面尺寸。

        Args:
            doc: python-docx Document 对象
            styles: DocumentStyles 对象
        """
        # ── 页面设置 ──
        for section in doc.sections:
            section.page_width = Cm(styles.page_width_cm)
            section.page_height = Cm(styles.page_height_cm)
            section.top_margin = Cm(styles.margin_top_cm)
            section.bottom_margin = Cm(styles.margin_bottom_cm)
            section.left_margin = Cm(styles.margin_left_cm)
            section.right_margin = Cm(styles.margin_right_cm)

        # ── Normal 样式 ──
        normal_style = doc.styles["Normal"]
        if styles.body_style:
            DocxExporter._apply_text_style_to_style(normal_style, styles.body_style)
        if styles.body_para_style:
            DocxExporter._apply_para_style_to_style(normal_style, styles.body_para_style)

        # ── 标题样式 ──
        heading_names = {1: "Heading 1", 2: "Heading 2", 3: "Heading 3"}
        for level, name in heading_names.items():
            if level in styles.heading_styles:
                ts, ps = styles.heading_styles[level]
                try:
                    h_style = doc.styles[name]
                except KeyError:
                    h_style = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)

                if ts:
                    DocxExporter._apply_text_style_to_style(h_style, ts)
                if ps:
                    DocxExporter._apply_para_style_to_style(h_style, ps)

    @staticmethod
    def _apply_text_style_to_style(style, text_style: Any) -> None:
        """将 TextStyle 属性应用到 Word 样式。"""
        font = style.font
        if text_style.font_name_latin:
            font.name = text_style.font_name_latin
        if text_style.font_size_pt:
            font.size = Pt(text_style.font_size_pt)
        if text_style.bold:
            font.bold = True
        if text_style.italic:
            font.italic = True
        if text_style.font_name_cjk:
            style.element.rPr.rFonts.set(qn("w:eastAsia"), text_style.font_name_cjk)
        if text_style.color_rgb:
            from docx.shared import RGBColor
            font.color.rgb = RGBColor.from_string(text_style.color_rgb)

    @staticmethod
    def _apply_para_style_to_style(style, para_style: Any) -> None:
        """将 ParagraphStyle 属性应用到 Word 样式。"""
        pf = style.paragraph_format
        if para_style.first_line_indent_cm is not None:
            pf.first_line_indent = Cm(para_style.first_line_indent_cm)
        if para_style.line_spacing is not None:
            # 验证：行距倍数应在合理范围内 (0.5 ~ 10.0)
            ls = para_style.line_spacing
            if 0.5 <= ls <= 10.0:
                pf.line_spacing = ls
            else:
                print(f"    [WARN] _apply_para_style_to_style: 行距 {ls} 异常，使用默认值 {LINE_SPACING}")
                pf.line_spacing = LINE_SPACING
        if para_style.space_before_pt is not None:
            pf.space_before = Pt(para_style.space_before_pt)
        if para_style.space_after_pt is not None:
            pf.space_after = Pt(para_style.space_after_pt)
        if para_style.alignment:
            alignment_map = {
                "LEFT": WD_ALIGN_PARAGRAPH.LEFT,
                "CENTER": WD_ALIGN_PARAGRAPH.CENTER,
                "RIGHT": WD_ALIGN_PARAGRAPH.RIGHT,
                "JUSTIFY": WD_ALIGN_PARAGRAPH.JUSTIFY,
            }
            if para_style.alignment in alignment_map:
                pf.alignment = alignment_map[para_style.alignment]

    @staticmethod
    def _apply_text_style_to_run(run, text_style: Any) -> None:
        """将 TextStyle 属性应用到单个 Run。"""
        if text_style.font_name_latin:
            run.font.name = text_style.font_name_latin
        if text_style.font_name_cjk:
            run._element.rPr.rFonts.set(qn("w:eastAsia"), text_style.font_name_cjk)
        if text_style.font_size_pt:
            run.font.size = Pt(text_style.font_size_pt)
        if text_style.bold:
            run.bold = True
        if text_style.italic:
            run.italic = True
        if text_style.color_rgb:
            from docx.shared import RGBColor
            run.font.color.rgb = RGBColor.from_string(text_style.color_rgb)

    @staticmethod
    def _apply_para_style_to_paragraph(para: Any, para_style: Any) -> None:
        """将 ParagraphStyle 属性应用到单个段落。"""
        pf = para.paragraph_format
        if para_style.first_line_indent_cm is not None:
            pf.first_line_indent = Cm(para_style.first_line_indent_cm)
        if para_style.line_spacing is not None:
            ls = para_style.line_spacing
            if 0.5 <= ls <= 10.0:
                pf.line_spacing = ls
            else:
                print(f"    [WARN] _apply_para_style_to_paragraph: 行距 {ls} 异常，使用默认值 {LINE_SPACING}")
                pf.line_spacing = LINE_SPACING
        if para_style.space_before_pt is not None:
            pf.space_before = Pt(para_style.space_before_pt)
        if para_style.space_after_pt is not None:
            pf.space_after = Pt(para_style.space_after_pt)
        if para_style.alignment:
            alignment_map = {
                "LEFT": WD_ALIGN_PARAGRAPH.LEFT,
                "CENTER": WD_ALIGN_PARAGRAPH.CENTER,
                "RIGHT": WD_ALIGN_PARAGRAPH.RIGHT,
                "JUSTIFY": WD_ALIGN_PARAGRAPH.JUSTIFY,
            }
            if para_style.alignment in alignment_map:
                pf.alignment = alignment_map[para_style.alignment]

    # ── 占位符系统（Stage 7-8 模板填充） ────────────────────

    PLACEHOLDER_PATTERN = re.compile(r'《(TECH|IMAGE|TABLE|BUSINESS):([^:》]+):([^》]*)》')

    @staticmethod
    def insert_placeholder(doc: Document, placeholder_type: str, placeholder_id: str, title: str = "") -> Paragraph:
        """
        在文档中插入一个结构化占位符段落。

        占位符格式：《TYPE:ID:TITLE》
        Types: TECH（技术章节）, IMAGE（图片）, TABLE（表格）, BUSINESS（商务章节）

        Args:
            doc: Document 对象
            placeholder_type: 占位符类型
            placeholder_id: 占位符 ID
            title: 显示标题

        Returns:
            插入的段落对象
        """
        para = doc.add_paragraph()
        run = para.add_run(f"《{placeholder_type}:{placeholder_id}:{title}》")
        run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)  # 灰色标记
        run.font.size = Pt(9)
        return para

    @staticmethod
    def find_placeholders(doc: Document, placeholder_type: Optional[str] = None) -> List[Tuple[Paragraph, str, str, str]]:
        """
        在文档中查找所有占位符段落。

        Args:
            doc: Document 对象
            placeholder_type: 过滤类型，None 返回所有

        Returns:
            [(paragraph, type, id, title), ...]
        """
        results = []
        for para in doc.paragraphs:
            text = para.text.strip()
            m = DocxExporter.PLACEHOLDER_PATTERN.match(text)
            if m:
                ptype = m.group(1)
                if placeholder_type is None or ptype == placeholder_type:
                    results.append((para, ptype, m.group(2), m.group(3)))
        return results

    @staticmethod
    def replace_placeholder(para: Paragraph, new_text: str = "") -> None:
        """清除占位符文本，替换为新文本或移除段落。"""
        if new_text:
            para.clear()
            para.add_run(new_text)
        else:
            # 移除段落
            p_element = para._element
            p_element.getparent().remove(p_element)

    # ── 格式化内容插入（Stage 8 使用） ──────────────────────

    def insert_formatted_content(
        self,
        doc: Document,
        markdown_text: str,
        placeholder_para: Paragraph,
        styles: Any,  # DocumentStyles
    ) -> bool:
        """
        将 Markdown 文本转换为格式化 DOCX 内容，插入到占位符段落位置。

        解析 Markdown 的标题、段落、列表、表格、加粗等元素，
        使用捕获的 DocumentStyles 进行格式化。

        Args:
            doc: 目标 Document
            markdown_text: Markdown 文本内容
            placeholder_para: 占位符段落（将在此位置后插入内容）
            styles: DocumentStyles 对象

        Returns:
            True 成功
        """
        # 获取占位符段落在文档中的位置
        placeholder_element = placeholder_para._element
        parent = placeholder_element.getparent()
        placeholder_index = list(parent).index(placeholder_element)

        # 保存当前文档状态，在占位符后插入新元素
        lines = markdown_text.split("\n")

        new_elements = []  # 收集要插入的新 XML 元素
        in_table = False
        table_lines: List[str] = []

        for line in lines:
            # 表格
            if line.strip().startswith("|") and line.strip().endswith("|"):
                if not in_table:
                    in_table = True
                    table_lines = []
                table_lines.append(line)
                continue
            elif in_table:
                # 表格结束，渲染表格
                table_para, table_element = self._render_table_inline(table_lines, styles)
                if table_element is not None:
                    new_elements.append(table_element)
                table_lines = []
                in_table = False

            # 空行
            if not line.strip():
                continue

            # 标题
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading_match:
                level = len(heading_match.group(1))
                text = self._strip_markdown_format(heading_match.group(2).strip())
                para = self._render_styled_heading_inline(text, level, styles)
                if para is not None:
                    new_elements.append(para._element)
                continue

            # 无序列表
            list_match = re.match(r"^(\s*)[-*+]\s+(.+)$", line)
            if list_match:
                text = self._strip_markdown_format(list_match.group(2).strip())
                para = self._render_styled_list_inline(text, False, styles)
                if para is not None:
                    new_elements.append(para._element)
                continue

            # 有序列表
            ordered_match = re.match(r"^(\s*)\d+[.)]\s+(.+)$", line)
            if ordered_match:
                text = self._strip_markdown_format(ordered_match.group(2).strip())
                para = self._render_styled_list_inline(text, True, styles)
                if para is not None:
                    new_elements.append(para._element)
                continue

            # 分页符
            if line.strip() == "---":
                page_break_para = doc.add_paragraph()
                run = page_break_para.add_run()
                run._element.append(OxmlElement("w:br"))
                run._element[-1].set(qn("w:type"), "page")
                new_elements.append(page_break_para._element)
                continue

            # 普通段落
            para = self._render_styled_paragraph_inline(line, styles)
            if para is not None:
                new_elements.append(para._element)

        # 末尾表格
        if in_table and table_lines:
            table_para, table_element = self._render_table_inline(table_lines, styles)
            if table_element is not None:
                new_elements.append(table_element)

        # ── 在 XML 中插入元素 ──
        # 移除占位符
        parent.remove(placeholder_element)
        # 在占位符位置插入新元素
        insert_idx = placeholder_index
        for elem in new_elements:
            parent.insert(insert_idx, elem)
            insert_idx += 1

        return True

    def _render_styled_heading_inline(self, text: str, level: int, styles: Any) -> Optional[Any]:
        """创建一个带样式的新标题段落（不添加到文档）。"""
        doc_temp = Document()
        para = doc_temp.add_paragraph()

        if level in styles.heading_styles:
            ts, ps = styles.heading_styles[level]
            run = para.add_run(text)
            if ts:
                self._apply_text_style_to_run(run, ts)
            else:
                run.font.size = Pt({1: 16, 2: 14, 3: 12}.get(level, 11))
                run.bold = True
            if ps:
                self._apply_para_style_to_paragraph(para, ps)
        else:
            run = para.add_run(text)
            run.font.size = Pt(11)
            run.bold = True

        return para

    def _render_styled_paragraph_inline(self, text: str, styles: Any) -> Optional[Any]:
        """创建一个带样式的正文段落（不添加到文档）。"""
        doc_temp = Document()
        para = doc_temp.add_paragraph()

        parts = self._parse_inline_format(text)
        for part_text, is_bold in parts:
            run = para.add_run(part_text)
            if styles.body_style:
                self._apply_text_style_to_run(run, styles.body_style)
            else:
                run.font.name = FONT_LATIN
                run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CJK)
                run.font.size = SIZE_BODY
            if is_bold:
                run.bold = True

        if styles.body_para_style:
            self._apply_para_style_to_paragraph(para, styles.body_para_style)
        else:
            pf = para.paragraph_format
            pf.first_line_indent = Cm(0.74)
            pf.line_spacing = LINE_SPACING
            pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        return para

    def _render_styled_list_inline(self, text: str, ordered: bool, styles: Any) -> Optional[Any]:
        """创建一个带样式的列表项段落。"""
        doc_temp = Document()
        para = doc_temp.add_paragraph()

        run = para.add_run(text)
        if styles.body_style:
            self._apply_text_style_to_run(run, styles.body_style)
        else:
            run.font.name = FONT_LATIN
            run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CJK)
            run.font.size = SIZE_BODY

        pf = para.paragraph_format
        pf.left_indent = Cm(0.74)
        pf.first_line_indent = Cm(-0.37)
        if styles.body_para_style and styles.body_para_style.line_spacing:
            ls = styles.body_para_style.line_spacing
            if 0.5 <= ls <= 10.0:
                pf.line_spacing = ls
            else:
                pf.line_spacing = LINE_SPACING
        else:
            pf.line_spacing = LINE_SPACING

        return para

    def _render_table_inline(
        self, md_lines: List[str], styles: Any
    ) -> Tuple[Optional[Any], Optional[Any]]:
        """
        解析 Markdown 表格并创建一个 Word 表格（不添加文档）。

        Returns:
            (段落对象, 表格元素) — 段落用于容纳表格
        """
        rows_data = []
        for line in md_lines:
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.split("|")[1:-1]]
            if self._is_markdown_table_separator(cells):
                continue
            if cells:
                rows_data.append(cells)

        if not rows_data:
            return None, None

        max_cols = max(len(r) for r in rows_data)
        for r in rows_data:
            while len(r) < max_cols:
                r.append("")

        doc_temp = Document()
        table = doc_temp.add_table(rows=len(rows_data), cols=max_cols)
        table.autofit = True

        for i, row_data in enumerate(rows_data):
            row = table.rows[i]
            for j, cell_text in enumerate(row_data):
                cell = row.cells[j]
                cell.text = ""
                para = cell.paragraphs[0]
                run = para.add_run(cell_text)

                if i == 0 and styles.table_header_style:
                    self._apply_text_style_to_run(run, styles.table_header_style)
                elif styles.table_cell_style:
                    self._apply_text_style_to_run(run, styles.table_cell_style)
                else:
                    run.font.name = FONT_LATIN
                    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CJK)
                    run.font.size = SIZE_TABLE
                    if i == 0:
                        run.bold = True
                        para.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # 应用表格边框
        if styles.table_style:
            self._apply_three_line_borders_styled(table, styles.table_style)
        else:
            self._apply_three_line_borders(table)

        # 返回容纳表格的段落和表格元素
        container_para = doc_temp.add_paragraph()
        return container_para, table._element

    @staticmethod
    def _is_markdown_table_separator(cells: List[str]) -> bool:
        """识别 Markdown 表头分隔行，防止 --- 被渲染进 Word 表格。"""
        non_empty = [cell.strip() for cell in cells if cell.strip()]
        if not non_empty:
            return False
        return all(re.fullmatch(r":?-{3,}:?", cell) for cell in non_empty)

    @staticmethod
    def _apply_three_line_borders_styled(table, table_style: Any) -> None:
        """使用捕获的 TableStyle 应用三线表边框。"""
        tbl = table._element
        tbl_pr = tbl.tblPr

        for existing in tbl_pr.findall(qn("w:tblBorders")):
            tbl_pr.remove(existing)

        borders = OxmlElement("w:tblBorders")

        border_defs = {
            "top": table_style.top_border_sz,
            "bottom": table_style.bottom_border_sz,
            "insideH": table_style.inside_h_border_sz,
            "insideV": table_style.inside_v_border_sz,
        }

        for tag, sz in border_defs.items():
            if sz is not None and sz > 0:
                el = OxmlElement(f"w:{tag}")
                el.set(qn("w:val"), "single")
                el.set(qn("w:sz"), str(sz))
                el.set(qn("w:space"), "0")
                el.set(qn("w:color"), "000000")
                borders.append(el)

        tbl_pr.append(borders)

    # ── DOCX 合并（Stage 10 使用） ──────────────────────────

    @staticmethod
    def merge_docx(base_path: Path, append_path: Path, output_path: Path) -> Path:
        """
        将 append_docx 的内容追加到 base_docx 末尾。

        用于 Stage 10 将应答表合并到填充好的模板中。

        Args:
            base_path: 基础 DOCX 文件路径
            append_path: 要追加的 DOCX 文件路径
            output_path: 合并后的输出路径

        Returns:
            输出文件路径
        """
        base_doc = Document(str(base_path))
        append_doc = Document(str(append_path))

        # 在基础文档末尾添加分页符
        base_doc.add_page_break()

        # 将追加文档的 body 元素逐个添加到基础文档
        base_body = base_doc.element.body
        append_body = append_doc.element.body

        for child in list(append_body):
            # 跳过第一节的属性（sectPr），在最后单独处理
            if child.tag == qn("w:sectPr"):
                continue
            base_body.append(child)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        base_doc.save(str(output_path))

        print(f"    [DOCX] 合并完成: {output_path}")
        return output_path


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

def export_markdown_to_docx(
    md_path: Path,
    output_path: Path,
    metadata: Optional[Dict[str, Any]] = None,
) -> Path:
    """快速将 Markdown 导出为 DOCX。"""
    exporter = DocxExporter()
    return exporter.export_from_markdown(md_path, output_path, metadata)
