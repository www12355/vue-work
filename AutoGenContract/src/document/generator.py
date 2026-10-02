"""
DOCX 文档生成器 — 从 Markdown 生成格式化合同 DOCX。

替代 replacer.py 的模板替换方式，直接构建格式化的 Word 文档。

格式规范：
- 正文：小四(12pt) 宋体，英文/数字 Times New Roman，两端对齐，首行缩进 2 字符
- 一级标题（## 一、...）：四号(14pt) 黑体 + Times New Roman，加粗，段前段后各 1 行
- 二级标题（### （一）...）：小四(12pt) 黑体 + Times New Roman，加粗，段前段后各 0.5 行
- 行距 1.5 倍
- 列表：悬挂缩进 2 字符（首行顶格，后续行缩进）
- 图/表题注：居中，无缩进
- 表格：表头/表体均不加粗，自适应页面宽度，单元格边距上下 0.05cm 左右 0.1cm
- A4 纸，标准页边距（上下 2.54cm，左右 3.18cm）

用法:
    from src.document.generator import generate_docx_from_markdown
    generate_docx_from_markdown(md_text, output_path, form_data)
"""

from __future__ import annotations

import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml

logger = logging.getLogger(__name__)

# ── 字体与排版常量 ──────────────────────────────────────────

FONT_BODY_CN = "宋体"
FONT_TITLE_CN = "黑体"
FONT_LATIN = "Times New Roman"

SIZE_BODY = Pt(12)       # 小四
SIZE_TITLE_L1 = Pt(14)   # 四号（一级标题）
SIZE_TITLE_L2 = Pt(12)   # 小四（二级标题）
SIZE_COVER_TITLE = Pt(18)

LINE_SPACING = 1.5

# 标题段前段后间距
SPACE_H1_H2 = Pt(12)   # 一级/二级标题：段前段后各 1 行
SPACE_H3 = Pt(6)       # 三级及以上标题：段前段后各 0.5 行

PAGE_WIDTH = Cm(21)
PAGE_HEIGHT = Cm(29.7)
MARGIN_TOP = Cm(2.54)
MARGIN_BOTTOM = Cm(2.54)
MARGIN_LEFT = Cm(3.18)
MARGIN_RIGHT = Cm(3.18)

# Markdown 标题匹配
RE_H1 = re.compile(r"^# (.+)$")
RE_H2 = re.compile(r"^## (一、.+|二、.+|三、.+|四、.+|五、.+|六、.+|七、.+|八、.+|九、.+|十.+|十一、.+|十二、.+|十三、.+|封面信息|签章页)$")
RE_H3 = re.compile(r"^### [（(][一二三四五六七八九十\d]+[）)](.+)$")
RE_TABLE_ROW = re.compile(r"^\|(.+)\|$")

# 图/表题注检测 — 匹配 "图1" "图1-1" "表2" "表2-1" 等前缀
RE_CAPTION = re.compile(r'^(图\d|表\d)')


# ── 辅助函数 ────────────────────────────────────────────────

def _set_run_font(run, cn_font: str, latin_font: str, size: Pt, bold: bool = False):
    """设置 run 的中英文字体、字号和加粗。

    通过 OOXML 属性分别设置东亚字体和拉丁字体。
    """
    run.font.size = size
    run.bold = bold

    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = parse_xml(f'<w:rFonts {nsdecls("w")} />')
        rPr.insert(0, rFonts)

    rFonts.set(qn("w:eastAsia"), cn_font)
    rFonts.set(qn("w:ascii"), latin_font)
    rFonts.set(qn("w:hAnsi"), latin_font)
    rFonts.set(qn("w:cs"), latin_font)


def _set_paragraph_spacing(para, line_spacing: float = LINE_SPACING,
                           space_before=None, space_after=None):
    """设置段落行距和段前段后间距。"""
    pf = para.paragraph_format
    pf.line_spacing = line_spacing
    if space_before is not None:
        pf.space_before = space_before
    else:
        pf.space_before = Pt(0)
    if space_after is not None:
        pf.space_after = space_after
    else:
        pf.space_after = Pt(0)


def _add_formatted_paragraph(doc, text: str, cn_font: str, latin_font: str,
                              size: Pt, bold: bool = False,
                              alignment: int = WD_ALIGN_PARAGRAPH.LEFT,
                              first_line_indent: Optional[Cm] = None,
                              space_before=None,
                              space_after=None):
    """添加一个格式化段落。

    Args:
        first_line_indent: 首行缩进，正文默认 2 字符（约 0.74cm = 2*12pt）
        space_before: 段前间距，None 则默认为 0pt
        space_after: 段后间距，None 则默认为 0pt
    """
    para = doc.add_paragraph()
    _set_paragraph_spacing(para, space_before=space_before, space_after=space_after)

    if alignment:
        para.alignment = alignment

    if first_line_indent:
        para.paragraph_format.first_line_indent = first_line_indent

    run = para.add_run(text)
    _set_run_font(run, cn_font, latin_font, size, bold)
    return para


def _add_cover_table(doc, form_data: Dict[str, Any]):
    """添加封面信息表格。"""
    rows_data = [
        ("项目名称", form_data.get("project_name") or "【请填写】"),
        ("合同编号", form_data.get("contract_id") or "【请填写】"),
        ("甲方（委托方）", form_data.get("party_a") or "【请填写】"),
        ("甲方地址", "【请填写】"),
        ("甲方联系人", "【请填写】"),
        ("甲方联系电话", "【请填写】"),
        ("甲方电子邮箱", "【请填写】"),
        ("甲方法定代表人", "【请填写】"),
        ("乙方（服务方）", form_data.get("party_b") or "【请填写】"),
        ("乙方地址", "【请填写】"),
        ("乙方联系人", "【请填写】"),
        ("乙方联系电话", "【请填写】"),
        ("乙方电子邮箱", "【请填写】"),
        ("乙方法定代表人", "【请填写】"),
        ("签订地点", form_data.get("signing_place") or "【请填写】"),
        ("签订日期", form_data.get("signing_date") or "【YYYY年MM月DD日】"),
    ]

    table = doc.add_table(rows=len(rows_data), cols=2, style="Table Grid")
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for i, (label, value) in enumerate(rows_data):
        # Label cell
        cell_label = table.cell(i, 0)
        cell_label.text = ""
        p = cell_label.paragraphs[0]
        _set_paragraph_spacing(p)
        run = p.add_run(label)
        _set_run_font(run, FONT_BODY_CN, FONT_LATIN, SIZE_BODY, bold=True)
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _set_cell_vertical_center(cell_label)

        # Set cell width proportions
        cell_label.width = Cm(4)

        # Value cell
        cell_value = table.cell(i, 1)
        cell_value.text = ""
        p = cell_value.paragraphs[0]
        _set_paragraph_spacing(p)
        run = p.add_run(value)
        _set_run_font(run, FONT_BODY_CN, FONT_LATIN, SIZE_BODY, bold=False)
        _set_cell_vertical_center(cell_value)

        cell_value.width = Cm(10)

    doc.add_paragraph()  # spacing after table


def _add_cover_page(doc: Document, form_data: Dict[str, Any]):
    """添加合同封面页。"""
    # 顶部留白
    for _ in range(5):
        _add_formatted_paragraph(doc, "", FONT_BODY_CN, FONT_LATIN, Pt(14))

    # 合同类型标题
    _add_formatted_paragraph(
        doc, "技 术 服 务 合 同",
        FONT_TITLE_CN, FONT_LATIN, Pt(28), bold=True,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
    )
    _add_formatted_paragraph(doc, "", FONT_BODY_CN, FONT_LATIN, Pt(6))

    # 项目名称
    project_name = form_data.get("project_name") or "【请填写】"
    _add_formatted_paragraph(
        doc, f"项目名称：{project_name}",
        FONT_TITLE_CN, FONT_LATIN, Pt(16), bold=True,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
    )

    for _ in range(4):
        _add_formatted_paragraph(doc, "", FONT_BODY_CN, FONT_LATIN, Pt(12))

    # 合同编号
    contract_id = form_data.get("contract_id") or "【请填写】"
    _add_formatted_paragraph(
        doc, f"合同编号：{contract_id}",
        FONT_BODY_CN, FONT_LATIN, Pt(13), bold=False,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
    )
    _add_formatted_paragraph(doc, "", FONT_BODY_CN, FONT_LATIN, Pt(8))

    # 甲乙方信息表（居中，等宽列）
    cover_rows = [
        ("甲方（委托方）", form_data.get("party_a") or "【请填写】"),
        ("甲方地址", "【请填写】"),
        ("甲方联系人/电话", "【请填写】 / 【请填写】"),
        ("", ""),
        ("乙方（服务方）", form_data.get("party_b") or "【请填写】"),
        ("乙方地址", "【请填写】"),
        ("乙方联系人/电话", "【请填写】 / 【请填写】"),
        ("", ""), ("", ""), ("", ""),
        ("签订地点", form_data.get("signing_place") or "【请填写】"),
        ("签订日期", form_data.get("signing_date") or "【YYYY年MM月DD日】"),
    ]

    table = doc.add_table(rows=len(cover_rows), cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # 设置列宽：标签列 4cm，值列 7cm
    LABEL_W = Cm(4.5)
    VALUE_W = Cm(9.5)

    for i, (label, value) in enumerate(cover_rows):
        # 空行跳过
        if not label and not value:
            for j in range(2):
                cell = table.cell(i, j)
                cell.text = ""
                p = cell.paragraphs[0]
                _set_paragraph_spacing(p)
                _set_cell_vertical_center(cell)
            continue

        cell_label = table.cell(i, 0)
        cell_label.text = ""
        cell_label.width = LABEL_W
        p = cell_label.paragraphs[0]
        _set_paragraph_spacing(p)
        if label:
            run = p.add_run(label)
            _set_run_font(run, FONT_BODY_CN, FONT_LATIN, Pt(12), bold=True)
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _set_cell_vertical_center(cell_label)
        # 固定行高 0.8cm
        _set_row_height(table.rows[i], Cm(0.8))

        cell_value = table.cell(i, 1)
        cell_value.text = ""
        cell_value.width = VALUE_W
        p = cell_value.paragraphs[0]
        _set_paragraph_spacing(p)
        if value:
            run = p.add_run(value)
            _set_run_font(run, FONT_BODY_CN, FONT_LATIN, Pt(12), bold=False)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        _set_cell_vertical_center(cell_value)

    # 底部留白
    for _ in range(3):
        _add_formatted_paragraph(doc, "", FONT_BODY_CN, FONT_LATIN, Pt(12))


def _add_signature_page(doc, form_data: Optional[Dict[str, Any]] = None):
    if form_data is None:
        form_data = {}
    signing_date = form_data.get("signing_date") or "【YYYY年MM月DD日】"
    signing_place = form_data.get("signing_place") or "【签订地点】"
    """添加签章页（紧接正文，不分页）。"""
    _add_formatted_paragraph(doc, "", FONT_BODY_CN, FONT_LATIN, Pt(6))

    # 签章表格（4行：表头 + 1行盖章区域 + 签字行 + 日期行）
    table = doc.add_table(rows=4, cols=2, style="Table Grid")
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # 设置列宽
    for j in range(2):
        for i in range(4):
            table.cell(i, j).width = Cm(7.5)

    headers = ["甲方（盖章）", "乙方（盖章）"]
    for j, h in enumerate(headers):
        cell = table.cell(0, j)
        cell.text = ""
        p = cell.paragraphs[0]
        _set_paragraph_spacing(p)
        run = p.add_run(h)
        _set_run_font(run, FONT_TITLE_CN, FONT_LATIN, SIZE_BODY, bold=True)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_cell_vertical_center(cell)
        # 固定行高 1cm
        _set_row_height(table.rows[0], Cm(1))

    # 空行（盖章区域，固定 3cm）—— 仅 1 行
    for i in range(1, 2):
        for j in range(2):
            cell = table.cell(i, j)
            cell.text = ""
            p = cell.paragraphs[0]
            _set_paragraph_spacing(p)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _set_cell_vertical_center(cell)
        _set_row_height(table.rows[i], Cm(3))

    # 代表人签字行（固定 2.2cm）, 左对齐且上方段落 0.5 行
    for j in range(2):
        cell = table.cell(2, j)
        cell.text = ""
        p = cell.paragraphs[0]
        _set_paragraph_spacing(p)
        p.paragraph_format.space_before = Pt(6) # ← 0.5 行 ≈ 6pt（小四 12pt 的一半）
        run = p.add_run("法定代表人（签字）：")
        _set_run_font(run, FONT_BODY_CN, FONT_LATIN, SIZE_BODY)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _set_row_height(table.rows[2], Cm(2.2))

    # 日期行（固定 1cm）
    for j in range(2):
        cell = table.cell(3, j)
        cell.text = ""
        p = cell.paragraphs[0]
        _set_paragraph_spacing(p)
        run = p.add_run(f"日期：{signing_date}")
        _set_run_font(run, FONT_BODY_CN, FONT_LATIN, SIZE_BODY)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_cell_vertical_center(cell)
    _set_row_height(table.rows[3], Cm(1))

    signing_text = f"本合同于{signing_date}在{signing_place}签订。"
    _add_formatted_paragraph(
        doc, signing_text,
        FONT_BODY_CN, FONT_LATIN, SIZE_BODY,
        alignment=WD_ALIGN_PARAGRAPH.CENTER
    )


def _set_row_height(row, height):
    """设置表格行固定高度。"""
    tr = row._tr
    trPr = tr.get_or_add_trPr()
    trHeight = parse_xml(f'<w:trHeight {nsdecls("w")} w:val="{int(height.pt * 20)}" w:hRule="exact"/>')
    trPr.append(trHeight)


def _set_cell_vertical_center(cell):
    """设置表格单元格垂直居中对齐。"""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    # 移除已有的垂直对齐设置
    for existing in tcPr.findall(qn('w:vAlign')):
        tcPr.remove(existing)
    vAlign = parse_xml(f'<w:vAlign {nsdecls("w")} w:val="center"/>')
    tcPr.append(vAlign)


def _apply_content_table_formatting(table):
    """对内容表格应用统一格式：自动适应页面宽度、单元格边距。

    仅在内容表格（非封面/签章专用表格）上调用。
    """
    tbl = table._tbl
    tblPr = tbl.tblPr
    if tblPr is None:
        tblPr = parse_xml(f'<w:tblPr {nsdecls("w")} />')
        tbl.insert(0, tblPr)

    # 自动适应页面宽度 (w:type="pct" w:w="5000" = 100%)
    for existing in tblPr.findall(qn('w:tblW')):
        tblPr.remove(existing)
    tblW = parse_xml(
        f'<w:tblW {nsdecls("w")} w:w="5000" w:type="pct"/>'
    )
    tblPr.insert(0, tblW)

    # 单元格边距：上下 0.05cm ≈ 28 twips，左右 0.1cm ≈ 57 twips
    for existing in tblPr.findall(qn('w:tblCellMar')):
        tblPr.remove(existing)
    tblCellMar = parse_xml(
        f'<w:tblCellMar {nsdecls("w")}>'
        f'  <w:top w:w="28" w:type="dxa"/>'
        f'  <w:bottom w:w="28" w:type="dxa"/>'
        f'  <w:left w:w="57" w:type="dxa"/>'
        f'  <w:right w:w="57" w:type="dxa"/>'
        f'</w:tblCellMar>'
    )
    tblPr.append(tblCellMar)


# ── 主解析与生成函数 ─────────────────────────────────────────

def generate_docx_from_markdown(
    md_text: str,
    output_path: str,
    form_data: Optional[Dict[str, Any]] = None,
) -> str:
    """从 Markdown 文本生成格式化 DOCX 合同文档。

    Args:
        md_text: 完整的合同 Markdown 文本
        output_path: 输出 DOCX 文件路径
        form_data: 合同表单数据（用于封面信息）

    Returns:
        输出文件的绝对路径

    Raises:
        ValueError: Markdown 文本为空或格式无效
    """
    if not md_text or not md_text.strip():
        raise ValueError("Markdown 文本为空，无法生成 DOCX")

    if form_data is None:
        form_data = {}

    # 确保输出目录存在
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = Document()

    # ── 页面设置 ──
    section = doc.sections[0]
    section.page_width = PAGE_WIDTH
    section.page_height = PAGE_HEIGHT
    section.top_margin = MARGIN_TOP
    section.bottom_margin = MARGIN_BOTTOM
    section.left_margin = MARGIN_LEFT
    section.right_margin = MARGIN_RIGHT

    # ── 封面页 ──
    _add_cover_page(doc, form_data)
    doc.add_page_break()

    # ── 解析 Markdown 并生成 DOCX ──
    lines = md_text.strip().split("\n")
    _parse_and_render(doc, lines, form_data)

    # ── 签章页 ──
    _add_signature_page(doc, form_data)

    # ── 保存 ──
    doc.save(output_path)
    logger.info(f"合同 DOCX 已生成: {output_path}")

    return str(Path(output_path).resolve())


def _parse_and_render(doc: Document, lines: List[str], form_data: Dict[str, Any]):
    """状态机解析 Markdown → 格式化 DOCX。

    状态: NORMAL | TABLE | CODE
    - NORMAL: 标题/正文/分隔线
    - TABLE: 收集行 → 创建 Word 表格
    - CODE: 收集行 → 创建灰色底段落
    """
    STATE_NORMAL, STATE_TABLE, STATE_CODE = 0, 1, 2
    state = STATE_NORMAL
    buf: List[str] = []  # TABLE/CODE 缓冲
    seen_h2 = set()
    in_cover = False

    def _flush_table():
        """将缓冲的 markdown 表格行渲染为 Word 表格。"""
        nonlocal buf
        if len(buf) < 2:  # 至少需要表头+分隔行
            # 不够，按普通文本输出
            for bline in buf:
                _add_paragraph_with_bold(doc, bline)
            buf = []
            return
        # 解析行
        rows = []
        for row_line in buf:
            cells = [c.strip() for c in row_line.strip().strip('|').split('|')]
            rows.append(cells)
        # 第一行是表头，第二行是 |---| 分隔符，跳过
        if len(rows) >= 2 and all(re.match(r'^[-:]+$', c) for c in rows[1]):
            header = rows[0]
            data = rows[2:]
        else:
            header = None
            data = rows

        if not data and header and len(header) == 1 and not header[0]:
            buf = []; return

        col_count = max(len(r) for r in ([header] if header else []) + data) if (header or data) else 1
        if col_count < 1: col_count = 1
        table = doc.add_table(rows=len(data) + (1 if header else 0), cols=col_count, style="Table Grid")
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _apply_content_table_formatting(table)
        row_idx = 0
        if header:
            for ci, cell_text in enumerate(header):
                if ci >= col_count: break
                _set_table_cell(table.cell(row_idx, ci), cell_text, bold=False)
            row_idx = 1
        for row_data in data:
            for ci, cell_text in enumerate(row_data):
                if ci >= col_count: break
                _set_table_cell(table.cell(row_idx, ci), cell_text, bold=False)
            row_idx += 1
        _add_formatted_paragraph(doc, "", FONT_BODY_CN, FONT_LATIN, Pt(4))
        buf = []

    def _flush_code():
        """将缓冲的代码块渲染为灰色底段落。"""
        nonlocal buf
        code_text = "\n".join(buf)
        para = doc.add_paragraph()
        _set_paragraph_spacing(para)
        # 灰色底色
        shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="F0F0F0" w:val="clear"/>')
        para._element.get_or_add_pPr().append(shading)
        run = para.add_run(code_text)
        _set_run_font(run, "Consolas", "Consolas", Pt(10), bold=False)
        _add_formatted_paragraph(doc, "", FONT_BODY_CN, FONT_LATIN, Pt(4))
        buf = []

    def _is_table_sep(line: str) -> bool:
        return bool(re.match(r'^\|?[\s]*[-:]+\|', line)) or bool(re.match(r'^\|[-:\s|]+\|$', line))

    def _is_table_row(line: str) -> bool:
        return line.startswith('|') and '|' in line[1:]

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # ── 状态转换 ──
        if state == STATE_TABLE:
            if _is_table_sep(line):
                buf.append(line); i += 1; continue
            elif _is_table_row(line):
                buf.append(line); i += 1; continue
            else:
                _flush_table()
                state = STATE_NORMAL
                continue  # re-process current line

        if state == STATE_CODE:
            if line.strip().startswith("```"):
                _flush_code()
                state = STATE_NORMAL
                i += 1; continue
            buf.append(line); i += 1; continue

        # ── STATE_NORMAL ──
        if not line:
            i += 1; continue

        # H1 — skip (already on cover page)
        # But render the contract number line that follows it as left-aligned
        if RE_H1.match(line):
            i += 1
            # Skip blank lines and look for contract number line
            while i < len(lines) and not lines[i].strip():
                i += 1
            # If next non-empty line is a contract number line, render it left-aligned without indent
            if i < len(lines) and ("合同编号" in lines[i] or lines[i].strip().startswith("**合同编号")):
                _add_paragraph_no_indent(doc, lines[i].strip())
                i += 1
            continue

        # H2
        h2m = RE_H2.match(line)
        if h2m:
            stitle = h2m.group(1)
            # Skip cover info and signature — generator adds them automatically
            if stitle == "封面信息" or stitle == "签章页":
                # Skip until next H2 or end of section
                i += 1
                while i < len(lines):
                    if RE_H2.match(lines[i].rstrip()):
                        break
                    i += 1
                continue
            if stitle not in seen_h2:
                seen_h2.add(stitle)
                _add_formatted_paragraph(doc, stitle, FONT_TITLE_CN, FONT_LATIN, SIZE_TITLE_L1,
                                         bold=True, space_before=SPACE_H1_H2, space_after=SPACE_H1_H2)
            i += 1; continue

        # H3
        h3m = RE_H3.match(line)
        if h3m:
            ht = line.strip()
            if ht.startswith("### "): ht = ht[4:]
            _add_formatted_paragraph(doc, ht, FONT_TITLE_CN, FONT_LATIN, SIZE_TITLE_L2,
                                     bold=True, space_before=SPACE_H3, space_after=SPACE_H3)
            i += 1; continue

        # Separator
        if line.strip() in ("---", "***", "___"):
            _add_formatted_paragraph(doc, "", FONT_BODY_CN, FONT_LATIN, Pt(6))
            i += 1; continue

        # Code block start
        if line.strip().startswith("```"):
            state = STATE_CODE; buf = []; i += 1; continue

        # Table start
        if _is_table_row(line):
            state = STATE_TABLE; buf = [line]; i += 1; continue

        # Figure/Table caption — 图题注/表题注：居中、无缩进
        stripped = line.strip()
        if RE_CAPTION.match(stripped):
            _add_formatted_paragraph(doc, stripped, FONT_BODY_CN, FONT_LATIN,
                                     SIZE_BODY, bold=False,
                                     alignment=WD_ALIGN_PARAGRAPH.CENTER)
            i += 1
            continue

        # Normal paragraph (with inline bold)
        # 合同编号行取消首行缩进，左对齐，正确解析 **粗体** 标记
        if stripped.startswith("合同编号") or stripped.startswith("**合同编号"):
            _add_paragraph_no_indent(doc, stripped)
        else:
            _add_paragraph_with_bold(doc, stripped)
        i += 1

    # Flush remaining buffers
    if state == STATE_TABLE: _flush_table()
    if state == STATE_CODE: _flush_code()


def _set_table_cell(cell, text: str, bold: bool = False):
    """设置 Word 表格单元格的文本和格式，支持 **加粗** 标记。

    表头/表体统一不加粗，仅保留行内 **加粗** 标记。
    """
    cell.text = ""
    p = cell.paragraphs[0]
    _set_paragraph_spacing(p)
    _set_cell_vertical_center(cell)
    # 解析 **加粗** 标记
    parts = re.split(r'(\*\*.*?\*\*)', text)
    for part in parts:
        if part.startswith('**') and part.endswith('**'):
            run = p.add_run(part[2:-2])
            _set_run_font(run, FONT_BODY_CN, FONT_LATIN, Pt(10.5), bold=True)
        else:
            run = p.add_run(part)
            _set_run_font(run, FONT_BODY_CN, FONT_LATIN, Pt(10.5), bold=False)


def _add_paragraph_with_bold(doc: Document, text: str):
    """添加段落，解析行内 **粗体** 标记。"""
    para = doc.add_paragraph()
    _set_paragraph_spacing(para)
    para.paragraph_format.first_line_indent = Cm(0.74)
    para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    # Split by **bold** markers
    parts = re.split(r'(\*\*.*?\*\*)', text)
    for part in parts:
        if part.startswith('**') and part.endswith('**'):
            run = para.add_run(part[2:-2])
            _set_run_font(run, FONT_BODY_CN, FONT_LATIN, SIZE_BODY, bold=True)
        else:
            run = para.add_run(part)
            _set_run_font(run, FONT_BODY_CN, FONT_LATIN, SIZE_BODY, bold=False)


def _add_paragraph_no_indent(doc: Document, text: str):
    """添加段落，解析行内 **粗体** 标记，无首行缩进，左对齐。

    用于合同编号等不需要首行缩进的特殊行。
    """
    para = doc.add_paragraph()
    _set_paragraph_spacing(para)
    para.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Split by **bold** markers
    parts = re.split(r'(\*\*.*?\*\*)', text)
    for part in parts:
        if part.startswith('**') and part.endswith('**'):
            run = para.add_run(part[2:-2])
            _set_run_font(run, FONT_BODY_CN, FONT_LATIN, SIZE_BODY, bold=True)
        else:
            run = para.add_run(part)
            _set_run_font(run, FONT_BODY_CN, FONT_LATIN, SIZE_BODY, bold=False)


# ── 便捷函数 ────────────────────────────────────────────────

def generate_contract_docx(
    contract_md: str,
    output_dir: str,
    contract_id: str,
    form_data: Optional[Dict[str, Any]] = None,
) -> str:
    """便捷函数：从合同 Markdown 生成合同 DOCX。

    Args:
        contract_md: 合同 Markdown 文本
        output_dir: 输出目录
        contract_id: 合同编号（用于文件名）
        form_data: 表单数据

    Returns:
        输出文件路径
    """
    output_path = str(Path(output_dir) / f"{contract_id}.docx")
    return generate_docx_from_markdown(contract_md, output_path, form_data)


def generate_review_report_docx(
    review_md: str,
    output_dir: str,
    contract_id: str,
) -> str:
    """便捷函数：生成审查报告 DOCX。

    Args:
        review_md: 审查报告 Markdown 文本
        output_dir: 输出目录
        contract_id: 合同编号

    Returns:
        输出文件路径
    """
    output_path = str(Path(output_dir) / f"{contract_id}_审查报告.docx")
    return _generate_simple_docx(review_md, output_path, "合同质量审查报告")


def _generate_simple_docx(md_text: str, output_path: str, title: str = "") -> str:
    """生成格式化 DOCX（用于审查报告、工作量统计等辅助文档）。

    支持完整的 Markdown 子集：
    - # ## ### 三级标题
    - **加粗** 行内格式
    - | 表格 |
    - - / 1. 列表项
    - --- 分页符
    - ``` 代码块（自动跳过）
    """
    if not md_text or not md_text.strip():
        raise ValueError("文本为空，无法生成 DOCX")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    doc = Document()

    # 页面设置
    section = doc.sections[0]
    section.page_width = PAGE_WIDTH
    section.page_height = PAGE_HEIGHT
    section.top_margin = MARGIN_TOP
    section.bottom_margin = MARGIN_BOTTOM
    section.left_margin = MARGIN_LEFT
    section.right_margin = MARGIN_RIGHT

    lines = md_text.strip().split("\n")

    # ── Helper: parse **bold** in paragraphs ──
    def _add_para_bold(text: str, first_line_indent=Cm(0.74), left_indent=None):
        para = doc.add_paragraph()
        _set_paragraph_spacing(para)
        para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        if left_indent is not None:
            para.paragraph_format.left_indent = left_indent
        if first_line_indent is not None:
            para.paragraph_format.first_line_indent = first_line_indent
        parts = re.split(r'(\*\*.*?\*\*)', text)
        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                run = para.add_run(part[2:-2])
                _set_run_font(run, FONT_BODY_CN, FONT_LATIN, SIZE_BODY, bold=True)
            else:
                run = para.add_run(part)
                _set_run_font(run, FONT_BODY_CN, FONT_LATIN, SIZE_BODY, bold=False)
        return para

    # ── Helper: flush buffered table rows ──
    def _flush_simple_table(buf_rows):
        if len(buf_rows) < 2:
            return
        # Parse: each row is | cell | cell |
        rows = []
        for rline in buf_rows:
            cells = [c.strip() for c in rline.strip().strip('|').split('|')]
            rows.append(cells)
        # Row 1 is |---|---| separator
        if len(rows) >= 2 and all(re.match(r'^[-:]+$', c) for c in rows[1]):
            header = rows[0]
            data = rows[2:]
        else:
            header = None
            data = rows
        if not data:
            return
        col_count = max((len(r) for r in ([header] if header else []) + data), default=1)
        if col_count < 1:
            col_count = 1
        table = doc.add_table(rows=len(data) + (1 if header else 0),
                              cols=col_count, style="Table Grid")
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _apply_content_table_formatting(table)
        ri = 0
        if header:
            for ci, ct in enumerate(header):
                if ci >= col_count: break
                _set_table_cell(table.cell(ri, ci), ct, bold=False)
            ri = 1
        for row_data in data:
            for ci, ct in enumerate(row_data):
                if ci >= col_count: break
                _set_table_cell(table.cell(ri, ci), ct, bold=False)
            ri += 1
        # spacer after table
        _add_formatted_paragraph(doc, "", FONT_BODY_CN, FONT_LATIN, Pt(4))

    # ── State-machine parser ──
    STATE_NORMAL, STATE_TABLE, STATE_CODE = 0, 1, 2
    state = STATE_NORMAL
    table_buf = []

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # ── STATE_TABLE ──
        if state == STATE_TABLE:
            is_sep = bool(re.match(r'^\|?[\s]*[-:]+\|', line))
            is_row = line.startswith('|') and '|' in line[1:]
            if is_sep or is_row:
                table_buf.append(line); i += 1; continue
            else:
                _flush_simple_table(table_buf)
                table_buf = []
                state = STATE_NORMAL
                continue  # re-process this line

        # ── STATE_CODE ──
        if state == STATE_CODE:
            if line.strip().startswith("```"):
                state = STATE_NORMAL
            i += 1; continue

        # ── STATE_NORMAL ──
        if not line:
            i += 1; continue

        # Code block start → skip entire block
        if line.strip().startswith("```"):
            state = STATE_CODE; i += 1; continue

        # H1
        if line.startswith("# ") and not line.startswith("## "):
            _add_formatted_paragraph(doc, line[2:], FONT_TITLE_CN, FONT_LATIN,
                                     SIZE_TITLE_L1, bold=True,
                                     alignment=WD_ALIGN_PARAGRAPH.CENTER,
                                     space_before=SPACE_H1_H2, space_after=SPACE_H1_H2)
            i += 1; continue

        # H2
        if line.startswith("## ") and not line.startswith("### "):
            _add_formatted_paragraph(doc, line[3:], FONT_TITLE_CN, FONT_LATIN,
                                     SIZE_TITLE_L1, bold=True,
                                     space_before=SPACE_H1_H2, space_after=SPACE_H1_H2)
            i += 1; continue

        # H3
        if line.startswith("### "):
            _add_formatted_paragraph(doc, line[4:], FONT_TITLE_CN, FONT_LATIN,
                                     SIZE_TITLE_L2, bold=True,
                                     space_before=SPACE_H3, space_after=SPACE_H3)
            i += 1; continue

        # --- → page break (blank paragraph with spacing)
        if line.strip() == "---":
            _add_formatted_paragraph(doc, "", FONT_BODY_CN, FONT_LATIN, Pt(10))
            i += 1; continue

        # Table row
        if line.startswith('|') and '|' in line[1:]:
            state = STATE_TABLE; table_buf = [line]; i += 1; continue

        # Ordered list: "1. text" — 悬挂缩进：首行顶格，后续行缩进 2 字符
        m_ol = re.match(r'^(\d+)\.\s+(.+)$', line)
        if m_ol:
            _add_para_bold(f"{m_ol.group(1)}. {m_ol.group(2)}",
                           left_indent=Cm(0.74), first_line_indent=Cm(-0.74))
            i += 1; continue

        # Unordered list: "- text" or "* text" — 悬挂缩进：首行顶格，后续行缩进 2 字符
        if line.startswith("- ") or line.startswith("* "):
            _add_para_bold(f"• {line[2:]}",
                           left_indent=Cm(0.74), first_line_indent=Cm(-0.74))
            i += 1; continue

        # Figure/Table caption — 图题注/表题注：居中、无缩进
        if RE_CAPTION.match(line):
            _add_formatted_paragraph(doc, line, FONT_BODY_CN, FONT_LATIN,
                                     SIZE_BODY, bold=False,
                                     alignment=WD_ALIGN_PARAGRAPH.CENTER)
            i += 1; continue

        # Normal paragraph with inline bold
        _add_para_bold(line)
        i += 1

    # Flush remaining buffers
    if state == STATE_TABLE:
        _flush_simple_table(table_buf)

    doc.save(output_path)
    return str(Path(output_path).resolve())
