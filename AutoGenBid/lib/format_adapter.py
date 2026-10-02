"""
格式适配器 — 提取标书格式规格、捕获参考文档样式、解析叙述模式。

用途：
    Stage 6 使用此模块从原始招标文件中提取"投标文件格式"章节，
    从参考 DOCX 中捕获字体/段落/表格样式，从参考 TXT 中提取叙述模式，
    构建完整的 FormatSpec 供 Stage 7-10 使用。

用法:
    from lib.format_adapter import FormatAdapter, FormatSpec
    adapter = FormatAdapter(config)
    spec = adapter.build_format_spec(full_text, ref_docx, ref_txt)
"""

from __future__ import annotations

import sys
import json
import re
import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH


# ═══════════════════════════════════════════════════════════════
# 格式值校验常量
# ═══════════════════════════════════════════════════════════════

LINE_SPACING_MIN = 0.5
LINE_SPACING_MAX = 10.0
LINE_SPACING_DEFAULT = 1.5
LINE_SPACING_EXACT_PT_MIN = 6.0
LINE_SPACING_EXACT_PT_MAX = 72.0
FONT_SIZE_MIN_PT = 6.0
FONT_SIZE_MAX_PT = 72.0
FONT_SIZE_DEFAULT_BODY_PT = 12.0   # 小四
FONT_SIZE_DEFAULT_HEADING_PT = 14.0  # 四号
FIRST_LINE_INDENT_MAX_CM = 5.0
FIRST_LINE_INDENT_DEFAULT_CM = 0.74  # 约2字符
SPACE_BEFORE_AFTER_MAX_PT = 100.0

# ═══════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════

@dataclass
class TextStyle:
    """从参考 DOCX run 中捕获的文字样式属性。"""
    font_name_cjk: Optional[str] = None       # 中文字体名（如 "宋体", "黑体"）
    font_name_latin: Optional[str] = None      # 西文字体名（如 "Times New Roman"）
    font_size_pt: Optional[float] = None       # 字号（磅）
    bold: bool = False
    italic: bool = False
    color_rgb: Optional[str] = None            # 十六进制颜色（如 "000000"）
    alignment: Optional[str] = None            # LEFT, CENTER, RIGHT, JUSTIFY


@dataclass
class ParagraphStyle:
    """从参考 DOCX 段落中捕获的段落格式属性。"""
    first_line_indent_cm: Optional[float] = None   # 首行缩进（厘米）
    line_spacing: Optional[float] = None            # 行距倍数
    line_spacing_exact_pt: Optional[float] = None   # 固定行距（磅）
    space_before_pt: Optional[float] = None
    space_after_pt: Optional[float] = None
    outline_level: Optional[int] = None
    alignment: Optional[str] = None                 # LEFT, CENTER, RIGHT, JUSTIFY


@dataclass
class TableStyle:
    """从参考 DOCX 表格中捕获的表格边框和布局属性。"""
    top_border_sz: Optional[int] = None        # 顶线宽度（八分之一点，1pt=8）
    bottom_border_sz: Optional[int] = None     # 底线宽度
    inside_h_border_sz: Optional[int] = None   # 内部水平线宽度
    inside_v_border_sz: Optional[int] = None   # 内部垂直线宽度
    left_border_sz: Optional[int] = None
    right_border_sz: Optional[int] = None
    cell_padding_top_cm: Optional[float] = None
    cell_padding_bottom_cm: Optional[float] = None
    cell_padding_left_cm: Optional[float] = None
    cell_padding_right_cm: Optional[float] = None
    header_bold: bool = True
    header_alignment: str = "CENTER"


@dataclass
class DocumentStyles:
    """从参考 DOCX 中捕获的完整文档排版样式集。"""
    page_width_cm: float = 21.0
    page_height_cm: float = 29.7
    margin_top_cm: float = 2.5
    margin_bottom_cm: float = 2.5
    margin_left_cm: float = 2.5
    margin_right_cm: float = 2.5
    heading_styles: Dict[int, Tuple[Optional[TextStyle], Optional[ParagraphStyle]]] = field(default_factory=dict)
    body_style: Optional[TextStyle] = None
    body_para_style: Optional[ParagraphStyle] = None
    table_style: Optional[TableStyle] = None
    table_cell_style: Optional[TextStyle] = None
    table_header_style: Optional[TextStyle] = None
    header_footer_style: Optional[TextStyle] = None

    def to_dict(self) -> Dict[str, Any]:
        """转为可 JSON 序列化的字典。"""
        result = {
            "page_width_cm": self.page_width_cm,
            "page_height_cm": self.page_height_cm,
            "margin_top_cm": self.margin_top_cm,
            "margin_bottom_cm": self.margin_bottom_cm,
            "margin_left_cm": self.margin_left_cm,
            "margin_right_cm": self.margin_right_cm,
        }
        # 标题样式
        heading_dict = {}
        for level, (text_style, para_style) in self.heading_styles.items():
            heading_dict[str(level)] = {
                "text": asdict(text_style) if text_style else None,
                "paragraph": asdict(para_style) if para_style else None,
            }
        result["heading_styles"] = heading_dict

        result["body_style"] = asdict(self.body_style) if self.body_style else None
        result["body_para_style"] = asdict(self.body_para_style) if self.body_para_style else None
        result["table_style"] = asdict(self.table_style) if self.table_style else None
        result["table_cell_style"] = asdict(self.table_cell_style) if self.table_cell_style else None
        result["table_header_style"] = asdict(self.table_header_style) if self.table_header_style else None
        result["header_footer_style"] = asdict(self.header_footer_style) if self.header_footer_style else None
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentStyles":
        """从字典恢复 DocumentStyles。"""
        ds = cls(
            page_width_cm=data.get("page_width_cm", 21.0),
            page_height_cm=data.get("page_height_cm", 29.7),
            margin_top_cm=data.get("margin_top_cm", 2.5),
            margin_bottom_cm=data.get("margin_bottom_cm", 2.5),
            margin_left_cm=data.get("margin_left_cm", 2.5),
            margin_right_cm=data.get("margin_right_cm", 2.5),
        )
        headings = data.get("heading_styles", {})
        for level_str, styles in headings.items():
            level = int(level_str)
            ts = TextStyle(**styles["text"]) if styles.get("text") else None
            ps = ParagraphStyle(**styles["paragraph"]) if styles.get("paragraph") else None
            ds.heading_styles[level] = (ts, ps)

        if data.get("body_style"):
            ds.body_style = TextStyle(**data["body_style"])
        if data.get("body_para_style"):
            ds.body_para_style = ParagraphStyle(**data["body_para_style"])
        if data.get("table_style"):
            ds.table_style = TableStyle(**data["table_style"])
        if data.get("table_cell_style"):
            ds.table_cell_style = TextStyle(**data["table_cell_style"])
        if data.get("table_header_style"):
            ds.table_header_style = TextStyle(**data["table_header_style"])
        if data.get("header_footer_style"):
            ds.header_footer_style = TextStyle(**data["header_footer_style"])
        return ds


@dataclass
class FormatAttachment:
    """投标文件格式中的单个附件定义。"""
    attachment_id: str                      # "附件1", "附件2", ...
    name: str                               # 附件名称
    section_type: str                       # "business" | "technical" | "toc" | "cover"
    body_text: str = ""                     # 附件正文（商务附件为原样文本）
    fields: Dict[str, str] = field(default_factory=dict)  # 待填字段 {字段名: 默认值}
    source_start_offset: int = 0            # 在 full_text.md 中的起始偏移
    source_end_offset: int = 0


@dataclass
class FormatSpec:
    """完整的标书格式规格。"""
    spec_version: str = "1.0"
    generated_at: str = ""
    source_section: str = ""                # "第五部分 投标文件格式"
    source_found: bool = False              # 是否在招标文件中找到格式章节
    attachments: List[Dict[str, Any]] = field(default_factory=list)  # 12个附件
    technical_section_map: Dict[str, str] = field(default_factory=dict)  # 技术章节映射
    document_styles: Optional[DocumentStyles] = None
    narrative_patterns: Dict[str, Any] = field(default_factory=dict)
    toc_config: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# 格式适配器
# ═══════════════════════════════════════════════════════════════

class FormatAdapter:
    """从招标文件和参考文档中提取并适配标书格式规格。"""

    # ── 默认格式常量 ────────────────────────────────────────

    DEFAULT_ATTACHMENTS = [
        {"id": "封面", "name": "投标文件封面", "type": "cover"},
        {"id": "目录", "name": "投标文件总目录", "type": "toc"},
        {"id": "评分索引", "name": "评分因素及评标标准页码检索", "type": "toc"},
        {"id": "附件1", "name": "投标书", "type": "business"},
        {"id": "附件2", "name": "供应商资格声明函", "type": "business"},
        {"id": "附件2-1", "name": "供应商资格要求的证件", "type": "business"},
        {"id": "附件3", "name": "开标一览表", "type": "business"},
        {"id": "附件4", "name": "开标分项一览表", "type": "business"},
        {"id": "附件5", "name": "商务要求点对点应答表", "type": "business"},
        {"id": "附件6", "name": "技术一对一应答表", "type": "technical"},
        {"id": "附件7", "name": "主要相关项目业绩一览表", "type": "business"},
        {"id": "附件8", "name": "投标代表人授权书", "type": "business"},
        {"id": "附件9-1", "name": "中小企业声明函", "type": "business"},
        {"id": "附件9-2", "name": "残疾人福利性单位声明函", "type": "business"},
        {"id": "附件10", "name": "政府采购政策情况表", "type": "business"},
        {"id": "附件11", "name": "证明材料及方案", "type": "technical"},
        {"id": "附件12", "name": "其他资料", "type": "business"},
    ]

    # 默认技术章节映射
    DEFAULT_TECH_SECTION_MAP = {
        "项目背景与需求分析": "11.1",
        "总体技术架构设计": "11.2",
        "核心功能模块技术方案": "11.3",
        "AI模型与智能化能力": "11.4",
        "项目重点难点与应对": "11.5",
        "人员配置方案": "11.6",
        "项目进度安排": "11.7",
        "服务质量保证与验收": "11.8",
    }

    # 中文数字 → 阿拉伯数字映射
    CHINESE_NUMERALS = ["一", "二", "三", "四", "五", "六", "七", "八"]

    @classmethod
    def build_chapter_number_map(cls, section_map: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        构建章节编号映射：中文数字 → 模板编号。

        Args:
            section_map: 章节名称→编号映射，默认使用 DEFAULT_TECH_SECTION_MAP

        Returns:
            {"一": "13.1", "二": "13.2", ...} 及子章节前缀映射
        """
        smap = section_map or cls.DEFAULT_TECH_SECTION_MAP
        result = {}

        # 获取有序的章节列表（按 DEFAULT_TECH_SECTION_MAP 顺序）
        ordered_names = list(cls.DEFAULT_TECH_SECTION_MAP.keys())
        for i, name in enumerate(ordered_names):
            if i < len(cls.CHINESE_NUMERALS) and name in smap:
                cn = cls.CHINESE_NUMERALS[i]
                result[cn] = smap[name]

        # 添加子章节前缀映射：用于将 "1.1" → "13.1.1" 这类转换
        result["_ordered_sections"] = [smap.get(n, "") for n in ordered_names]
        result["_chinese_numerals"] = list(cls.CHINESE_NUMERALS)

        # 提取编号前缀（如 "13" 从 "13.1"）
        first_num = result.get("一", "")
        prefix_match = first_num.rsplit(".", 1)[0] if "." in first_num else first_num
        result["_prefix"] = prefix_match

        return result

    @staticmethod
    def safe_line_spacing(value: Optional[float]) -> float:
        """返回经过校验的行距倍数，异常时回退到默认值 LINE_SPACING_DEFAULT。"""
        if value is None:
            return LINE_SPACING_DEFAULT
        if LINE_SPACING_MIN <= value <= LINE_SPACING_MAX:
            return value
        print(f"    [WARN] FormatAdapter.safe_line_spacing: 行距 {value} 超出合理范围"
              f" [{LINE_SPACING_MIN}, {LINE_SPACING_MAX}]，使用默认值 {LINE_SPACING_DEFAULT}")
        return LINE_SPACING_DEFAULT

    def __init__(self, config: Any = None):
        """
        Args:
            config: BidPipelineConfig 实例，用于读取 format 配置节
        """
        self.config = config

    # ── 格式规格提取 ────────────────────────────────────────

    def extract_format_spec_from_text(self, full_text: str) -> Dict[str, Any]:
        """
        从 full_text.md 中搜索"投标文件格式"或"第五部分"章节，
        提取所有12个附件的定义和模板文本。

        Returns:
            包含 attachments, technical_section_map, source_section 的字典
        """
        result = {
            "source_found": False,
            "source_section": "",
            "attachments": [],
            "technical_section_map": dict(self.DEFAULT_TECH_SECTION_MAP),
        }

        # 查找格式章节
        start, end = self._locate_format_section(full_text)
        if start < 0:
            return result

        result["source_found"] = True
        section_text = full_text[start:end]
        result["source_section"] = "第五部分 投标文件格式"

        # 提取附件
        attachments = self._parse_attachments(section_text)
        result["attachments"] = attachments

        return result

    def _locate_format_section(self, full_text: str) -> Tuple[int, int]:
        """
        查找"第五部分 投标文件格式"章节的起止字符偏移。

        Returns:
            (start_offset, end_offset)，未找到返回 (-1, -1)
        """
        # 多种搜索模式
        patterns = [
            r"第五部分\s+投标文件格式",
            r"第[五5]部分\s+投标文件格式",
            r"投标文件格式\s*\n",
            r"#+\s*投标文件格式",
            r"#+\s*第五部分.*投标文件格式",
        ]

        start = -1
        for pattern in patterns:
            m = re.search(pattern, full_text)
            if m:
                start = m.start()
                break

        if start < 0:
            return (-1, -1)

        # 从找到的位置向后查找章节正文开始处
        # 跳过标题行，找到第一个实质性内容
        content_start = full_text.find("\n", start)
        if content_start < 0:
            content_start = start

        # 查找结束位置：下一个主要部分或文件末尾
        # 通常 投标文件格式 后面不会有更高的章节标记
        next_section_patterns = [
            r"\n第六部分",
            r"\n第[六6]部分",
            r"\n附件1[2-9]",
            r"\n#{1,3}\s*附件1[2-9]",
        ]

        end = len(full_text)
        for pattern in next_section_patterns:
            m = re.search(pattern, full_text[content_start:])
            if m:
                candidate_end = content_start + m.start()
                if candidate_end < end:
                    end = candidate_end

        return (start, end)

    def _parse_attachments(self, section_text: str) -> List[Dict[str, Any]]:
        """
        从格式章节文本中解析各个附件定义。

        识别附件编号（附件1-12）、名称、类型（商务/技术），
        并提取正文模板文本。
        """
        attachments = []

        # 先使用默认附件列表作为基础
        for default_att in self.DEFAULT_ATTACHMENTS:
            att_id = default_att["id"]
            att_name = default_att["name"]
            att_type = default_att["type"]

            # 在文本中查找对应附件
            body_text = ""
            fields = {}

            if att_id == "封面":
                body_text, start, end = self._extract_cover_text(section_text)
            else:
                body_text, start, end = self._extract_attachment_text(
                    section_text, att_id, att_name
                )

            # 提取附件中的待填字段
            fields = self._extract_fields(body_text)

            attachments.append({
                "attachment_id": att_id,
                "name": att_name,
                "section_type": att_type,
                "body_text": body_text,
                "fields": fields,
                "source_start_offset": start if start >= 0 else 0,
                "source_end_offset": end if end >= 0 else 0,
            })

        return attachments

    def _extract_cover_text(self, text: str) -> Tuple[str, int, int]:
        """提取封面模板文本。"""
        patterns = [
            r"(投标文件封面格式[^\n]*\n)(.*?)(?=\n投标文件总目录|\n附件1|\n评分因素)",
            r"(投\s*标\s*文\s*件\s*\n.*?)(?=\n投标文件总目录|\n附件1|\n评分因素)",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.DOTALL)
            if m:
                return m.group(0), m.start(), m.end()
        return "", -1, -1

    def _extract_attachment_text(
        self, text: str, att_id: str, att_name: str
    ) -> Tuple[str, int, int]:
        """
        从格式文本中提取指定附件的正文。

        使用附件编号和名称进行多模式匹配。
        """
        # 构建搜索模式
        clean_name = re.escape(att_name)
        clean_id = re.escape(att_id)

        patterns = [
            # 精确匹配：附件X\n附件名\n正文
            rf"{clean_id}\s*\n\s*{clean_name}[\s\S]*?(?=\n{re.escape(self._next_attachment_id(att_id))}\s*\n|\n附件1[0-9]|\Z)",
            # 宽松匹配
            rf"{clean_id}[^\n]*\n[\s\S]*?(?=\n附件\d|\Z)",
            # 仅匹配附件名
            rf"{clean_name}[\s\S]*?(?=\n附件\d|\Z)",
        ]

        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                body = m.group(0).strip()
                return body, m.start(), m.end()

        return "", -1, -1

    @staticmethod
    def _next_attachment_id(current_id: str) -> str:
        """获取下一个附件编号。"""
        mapping = {
            "封面": "目录", "目录": "评分索引", "评分索引": "附件1",
            "附件1": "附件2", "附件2": "附件2-1", "附件2-1": "附件3",
            "附件3": "附件4", "附件4": "附件5", "附件5": "附件6",
            "附件6": "附件7", "附件7": "附件8", "附件8": "附件9-1",
            "附件9-1": "附件9-2", "附件9-2": "附件10",
            "附件10": "附件11", "附件11": "附件12", "附件12": "",
        }
        return mapping.get(current_id, "")

    @staticmethod
    def _extract_fields(body_text: str) -> Dict[str, str]:
        """
        从附件正文中提取待填字段。

        识别以下模式：
        - ______（下划线占位）
        - [待填]、[请填写]、[XXX]
        - ____年____月____日
        - 空白行/空格占位
        """
        fields = {}

        # 下划线占位
        underline_patterns = re.findall(r'_{3,}', body_text)
        if underline_patterns:
            fields["_has_underlines"] = str(len(underline_patterns))

        # 方括号占位
        bracket_fields = re.findall(r'[\[【]([^\]】]*?(?:填写|待填|XXX|请|选填)[^\]】]*?)[\]】]', body_text)
        for bf in bracket_fields:
            fields[bf] = ""

        # 日期占位
        date_patterns = re.findall(r'(?:____|[\d]{4})\s*年\s*(?:____|[\d]{1,2})\s*月\s*(?:____|[\d]{1,2})\s*日', body_text)
        if date_patterns:
            fields["_date_placeholder"] = "true"

        # □ 选项
        checkbox_count = len(re.findall(r'□', body_text))
        if checkbox_count > 0:
            fields["_checkbox_count"] = str(checkbox_count)

        return fields

    # ── 参考 DOCX 样式捕获 ──────────────────────────────────

    def capture_reference_styles(self, docx_path: Path) -> DocumentStyles:
        """
        返回固定的中文投标文档排版样式（不再从参考DOCX自动检测）。

        使用硬编码的规范样式：
        - 正文：宋体 + Times New Roman, 11pt, 首行缩进2字符, 1.5倍行距
        - 标题（所有级别）：黑体 + Times New Roman
        - 大标题段前段后各1行(12pt)，小标题各0.5行(6pt)
        - 表格：三线表

        Returns:
            完整的 DocumentStyles 对象
        """
        return self._get_default_styles()

    @staticmethod
    def _iter_block_items(parent):
        """按文档顺序迭代段落和表格（与 BidDocumentParser 模式相同）。"""
        from docx.document import Document as _Doc
        parent_elm = parent.element.body if isinstance(parent, _Doc) else parent._element
        for child in parent_elm.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, parent)
            elif isinstance(child, CT_Tbl):
                yield DocxTable(child, parent)

    @staticmethod
    def _capture_run_style(para: Paragraph) -> TextStyle:
        """从段落的第一个有效 run 中提取文字样式。"""
        ts = TextStyle()
        if not para.runs:
            return ts

        # 取第一个有字体设置的 run
        for run in para.runs:
            if run.text.strip():
                # 中文字体
                rpr = run._element.rPr
                if rpr is not None:
                    rFonts = rpr.find(qn("w:rFonts"))
                    if rFonts is not None:
                        ts.font_name_cjk = rFonts.get(qn("w:eastAsia"))
                        ts.font_name_latin = rFonts.get(qn("w:ascii")) or rFonts.get(qn("w:hAnsi"))

                if not ts.font_name_latin:
                    ts.font_name_latin = run.font.name

                ts.font_size_pt = run.font.size.pt if run.font.size else None
                ts.bold = run.bold if run.bold is not None else False
                ts.italic = run.italic if run.italic is not None else False

                # 颜色
                if run.font.color and run.font.color.rgb:
                    ts.color_rgb = str(run.font.color.rgb)

                # 对齐
                if para.alignment is not None:
                    alignment_map = {
                        0: "LEFT", 1: "CENTER", 2: "RIGHT", 3: "JUSTIFY",
                    }
                    ts.alignment = alignment_map.get(para.alignment, "LEFT")
                break

        return ts

    @staticmethod
    def _capture_paragraph_style(para: Paragraph) -> ParagraphStyle:
        """从段落中提取段落格式属性。"""
        ps = ParagraphStyle()
        pf = para.paragraph_format

        # 首行缩进
        if pf.first_line_indent:
            ps.first_line_indent_cm = round(pf.first_line_indent.cm, 2)

        # 行距（带合理性校验和自动修正）
        if pf.line_spacing is not None:
            try:
                val = float(pf.line_spacing)
                # EMU 固定值通常 >= 100（如 190500 = 15pt），小数值视为倍数
                if val >= 100:
                    # EMU 值 → 转换为磅
                    converted_pt = round(val / 12700, 1)
                    if LINE_SPACING_EXACT_PT_MIN <= converted_pt <= LINE_SPACING_EXACT_PT_MAX:
                        ps.line_spacing_exact_pt = converted_pt
                    else:
                        print(f"    [WARN] _capture_paragraph_style: 固定行距异常 "
                              f"({converted_pt}pt，原始值={val})，已重置为默认倍数 {LINE_SPACING_DEFAULT}")
                        ps.line_spacing = LINE_SPACING_DEFAULT
                elif LINE_SPACING_MIN <= val <= LINE_SPACING_MAX:
                    # 正常的行距倍数
                    ps.line_spacing = round(val, 2)
                else:
                    # 不在合理范围的小数值（如 0.13）：异常，修正为默认值
                    print(f"    [WARN] _capture_paragraph_style: 行距倍数异常 "
                          f"({val}，超出范围 [{LINE_SPACING_MIN}, {LINE_SPACING_MAX}])，已重置为默认值 {LINE_SPACING_DEFAULT}")
                    ps.line_spacing = LINE_SPACING_DEFAULT
            except (TypeError, ValueError):
                # 可能是 Length 对象（固定行距）
                try:
                    converted_pt = round(pf.line_spacing.pt, 2)
                    if LINE_SPACING_EXACT_PT_MIN <= converted_pt <= LINE_SPACING_EXACT_PT_MAX:
                        ps.line_spacing_exact_pt = converted_pt
                    else:
                        print(f"    [WARN] _capture_paragraph_style: Length 行距异常 "
                              f"({converted_pt}pt)，已重置为默认倍数 {LINE_SPACING_DEFAULT}")
                        ps.line_spacing = LINE_SPACING_DEFAULT
                except Exception:
                    pass

        # 段前段后
        if pf.space_before:
            ps.space_before_pt = round(pf.space_before.pt, 2)
        if pf.space_after:
            ps.space_after_pt = round(pf.space_after.pt, 2)

        # 大纲级别
        ppr = para._element.pPr
        if ppr is not None:
            outline_lvl = ppr.find(qn("w:outlineLvl"))
            if outline_lvl is not None:
                ps.outline_level = int(outline_lvl.get(qn("w:val"), "0"))

        # 对齐
        if para.alignment is not None:
            alignment_map = {0: "LEFT", 1: "CENTER", 2: "RIGHT", 3: "JUSTIFY"}
            ps.alignment = alignment_map.get(para.alignment)

        return ps

    @staticmethod
    def _detect_real_heading_level(para: Paragraph) -> Optional[int]:
        """
        检测段落的实际标题级别（非仅依赖样式名）。

        策略：
        1. 大纲级别 (outlineLvl) — 最可靠
        2. 样式名中的 heading/标题 标记
        3. 字体大小推断（≥16pt → 1级, ≥14pt → 2级）
        """
        # 1. 大纲级别
        ppr = para._element.pPr
        if ppr is not None:
            outline_lvl = ppr.find(qn("w:outlineLvl"))
            if outline_lvl is not None:
                level = int(outline_lvl.get(qn("w:val"), "0")) + 1
                return min(level, 6)

        # 2. 样式名
        style_name = para.style.name if para.style else ""
        heading_patterns = [
            (r"^heading\s*(\d+)$", 1),
            (r"^标题\s*(\d+)$", 1),
            (r"^Heading\s*(\d+)$", 1),
        ]
        import re as _re
        for pattern, group_idx in heading_patterns:
            m = _re.match(pattern, style_name, _re.IGNORECASE)
            if m:
                return min(int(m.group(group_idx)), 6)

        # 3. 字体大小推断（仅对短文本有效）
        text = para.text.strip()
        if len(text) > 60 or not text:
            return None

        if para.runs:
            run = para.runs[0]
            if run.font.size:
                size_pt = run.font.size.pt
                if size_pt >= 16 and run.bold:
                    return 1
                elif size_pt >= 14 and run.bold:
                    return 2
                elif size_pt >= 12 and run.bold:
                    return 3

        return None

    @staticmethod
    def _capture_table_style(table: DocxTable) -> Optional[TableStyle]:
        """从表格 XML 属性中提取边框样式。"""
        ts = TableStyle()
        tbl_pr = table._element.tblPr
        if tbl_pr is None:
            return None

        borders = tbl_pr.find(qn("w:tblBorders"))
        if borders is None:
            return None

        border_map = {
            "top": ("top_border_sz",),
            "bottom": ("bottom_border_sz",),
            "insideH": ("inside_h_border_sz",),
            "insideV": ("inside_v_border_sz",),
            "left": ("left_border_sz",),
            "right": ("right_border_sz",),
        }

        for border_tag, (attr_name,) in border_map.items():
            el = borders.find(qn(f"w:{border_tag}"))
            if el is not None:
                sz = el.get(qn("w:sz"))
                if sz:
                    setattr(ts, attr_name, int(sz))

        return ts

    @staticmethod
    def _average_text_style(styles: List[TextStyle]) -> TextStyle:
        """从多样本中计算平均/多数 TextStyle。"""
        if not styles:
            return TextStyle()
        # 取最常见的字体名
        from collections import Counter
        cjk_names = Counter(s.font_name_cjk for s in styles if s.font_name_cjk)
        latin_names = Counter(s.font_name_latin for s in styles if s.font_name_latin)
        sizes = [s.font_size_pt for s in styles if s.font_size_pt]
        bold_count = sum(1 for s in styles if s.bold)

        return TextStyle(
            font_name_cjk=cjk_names.most_common(1)[0][0] if cjk_names else "宋体",
            font_name_latin=latin_names.most_common(1)[0][0] if latin_names else "Times New Roman",
            font_size_pt=round(sum(sizes) / len(sizes), 1) if sizes else 11.0,
            bold=bold_count > len(styles) / 2,
            color_rgb=Counter(s.color_rgb for s in styles if s.color_rgb).most_common(1)[0][0]
            if any(s.color_rgb for s in styles) else None,
        )

    @staticmethod
    def _average_paragraph_style(styles: List[ParagraphStyle]) -> ParagraphStyle:
        """从多样本中计算平均 ParagraphStyle。"""
        if not styles:
            return ParagraphStyle()
        indent_vals = [s.first_line_indent_cm for s in styles if s.first_line_indent_cm is not None]
        spacing_vals = [s.line_spacing for s in styles if s.line_spacing is not None]

        return ParagraphStyle(
            first_line_indent_cm=round(sum(indent_vals) / len(indent_vals), 2) if indent_vals else 0.74,
            line_spacing=round(sum(spacing_vals) / len(spacing_vals), 2) if spacing_vals else 1.5,
            space_before_pt=round(
                sum(s.space_before_pt for s in styles if s.space_before_pt is not None) /
                max(1, sum(1 for s in styles if s.space_before_pt is not None)), 2
            ) if any(s.space_before_pt is not None for s in styles) else None,
            space_after_pt=round(
                sum(s.space_after_pt for s in styles if s.space_after_pt is not None) /
                max(1, sum(1 for s in styles if s.space_after_pt is not None)), 2
            ) if any(s.space_after_pt is not None for s in styles) else None,
        )

    # ── 参考 TXT 叙述模式提取 ───────────────────────────────

    def extract_narrative_patterns(self, txt_path: Path) -> Dict[str, Any]:
        """
        读取参考 TXT 文件，提取叙述模式和写作惯例。

        提取以下信息：
        - 典型段落长度分布
        - 句子开头模式（如 "我方充分理解...", "完全满足..."）
        - 章节编号风格
        - 技术响应措辞惯例
        - 常用过渡词和连接词

        Returns:
            patterns 字典，供 Stage 7-8 参考
        """
        if not txt_path or not txt_path.exists():
            return self._get_default_narrative_patterns()

        try:
            text = txt_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"    [FormatAdapter] 无法读取参考 TXT: {e}，使用默认模式")
            return self._get_default_narrative_patterns()

        patterns = {}

        # ── 段落统计 ──
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        para_lengths = [len(p) for p in paragraphs]
        if para_lengths:
            patterns["paragraph_count"] = len(paragraphs)
            patterns["avg_paragraph_length"] = round(sum(para_lengths) / len(para_lengths))
            patterns["min_paragraph_length"] = min(para_lengths)
            patterns["max_paragraph_length"] = max(para_lengths)

        # ── 句子开头模式 ──
        sentence_openers = self._extract_sentence_openers(text)
        patterns["common_openers"] = sentence_openers

        # ── 章节编号风格 ──
        chapter_patterns = self._detect_chapter_patterns(text)
        patterns["chapter_numbering"] = chapter_patterns

        # ── 响应措辞模式 ──
        response_phrases = self._extract_response_phrases(text)
        patterns["response_phrases"] = response_phrases

        # ── 标题检测 ──
        heading_lines = self._extract_heading_patterns(text)
        patterns["heading_patterns"] = heading_lines

        # ── 表格标记 ──
        patterns["has_tables"] = "|" in text and text.count("|") > 10

        return patterns

    @staticmethod
    def _extract_sentence_openers(text: str) -> List[Dict[str, Any]]:
        """提取常见句子开头模式。"""
        openers = []
        common_prefixes = [
            "我方", "完全满足", "满足", "本系统", "系统支持",
            "基于", "通过", "采用", "提供", "支持",
            "具备", "实现", "确保", "可",
        ]

        for prefix in common_prefixes:
            pattern = re.escape(prefix)
            matches = re.findall(rf"(?:^|[。；])\s*({pattern}[^。；]{{15,80}})", text)
            if matches:
                openers.append({
                    "prefix": prefix,
                    "frequency": len(matches),
                    "examples": matches[:3],
                })

        # 按频率排序
        openers.sort(key=lambda x: x["frequency"], reverse=True)
        return openers[:15]

    @staticmethod
    def _detect_chapter_patterns(text: str) -> Dict[str, Any]:
        """检测章节编号风格。"""
        patterns = {}

        # 中文数字编号
        cn_numbered = re.findall(r'^[一二三四五六七八九十]+[、，]\s*.+$', text, re.MULTILINE)
        patterns["chinese_numbered"] = len(cn_numbered) > 0

        # 阿拉伯数字编号
        arabic_numbered = re.findall(r'^\d+[.)]\s*.+$', text, re.MULTILINE)
        patterns["arabic_numbered"] = len(arabic_numbered) > 0

        # 多级编号
        multi_level = re.findall(r'^\d+\.\d+(?:\.\d+)?\s+.+$', text, re.MULTILINE)
        patterns["multi_level"] = len(multi_level) > 0

        # 括号编号
        bracket_numbered = re.findall(r'^[（(][一二三四五六七八九十\d]+[）)]\s*.+$', text, re.MULTILINE)
        patterns["bracket_numbered"] = len(bracket_numbered) > 0

        return patterns

    @staticmethod
    def _extract_response_phrases(text: str) -> List[Dict[str, Any]]:
        """提取技术响应中的常用措辞。"""
        phrases = []

        response_patterns = [
            ("完全满足", r"完全满足[^。；]{10,80}"),
            ("基本满足", r"基本满足[^。；]{10,80}"),
            ("支持", r".{0,10}支持[^。；]{10,80}"),
            ("提供", r".{0,10}提供[^。；]{10,80}"),
            ("基于AI", r"基于(?:AI|大模型|人工智能)[^。；]{15,100}"),
            ("数据安全", r"数据(?:安全|隔离|加密|保护)[^。；]{15,100}"),
        ]

        for label, pattern in response_patterns:
            matches = re.findall(pattern, text)
            if matches:
                phrases.append({
                    "label": label,
                    "frequency": len(matches),
                    "examples": matches[:2],
                })

        phrases.sort(key=lambda x: x["frequency"], reverse=True)
        return phrases

    @staticmethod
    def _extract_heading_patterns(text: str) -> List[Dict[str, Any]]:
        """提取标题行模式。"""
        headings = []
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 检测可能的标题行
            if re.match(r'^\d+\.\d+(?:\.\d+)?[\s.]+', line):
                headings.append({"text": line[:80], "type": "numbered"})
            elif re.match(r'^[一二三四五六七八九十]+、', line):
                headings.append({"text": line[:80], "type": "chinese_numbered"})

        return headings[:30]

    @staticmethod
    def _get_default_narrative_patterns() -> Dict[str, Any]:
        """返回默认叙述模式（当无参考 TXT 时使用）。"""
        return {
            "paragraph_count": 0,
            "avg_paragraph_length": 200,
            "common_openers": [
                {"prefix": "我方", "frequency": 10, "examples": []},
                {"prefix": "完全满足", "frequency": 8, "examples": []},
                {"prefix": "基于", "frequency": 5, "examples": []},
                {"prefix": "提供", "frequency": 5, "examples": []},
            ],
            "chapter_numbering": {
                "chinese_numbered": True,
                "arabic_numbered": True,
                "multi_level": True,
            },
            "response_phrases": [],
            "heading_patterns": [],
            "has_tables": False,
        }

    # ── 默认样式 ────────────────────────────────────────────

    @staticmethod
    def _get_default_styles() -> DocumentStyles:
        """返回默认的中文投标文档排版样式（与 DocxExporter 硬编码常量一致）。"""
        ds = DocumentStyles()

        # 一级标题：黑体 16pt 加粗居中，段前段后各1行(≈12pt)
        ds.heading_styles[1] = (
            TextStyle(font_name_cjk="黑体", font_name_latin="Times New Roman",
                       font_size_pt=16.0, bold=True, alignment="CENTER"),
            ParagraphStyle(first_line_indent_cm=0, line_spacing=1.5,
                           space_before_pt=12, space_after_pt=12),
        )

        # 二级标题：黑体 14pt 加粗左对齐，段前段后各1行(≈12pt)
        ds.heading_styles[2] = (
            TextStyle(font_name_cjk="黑体", font_name_latin="Times New Roman",
                       font_size_pt=14.0, bold=True, alignment="LEFT"),
            ParagraphStyle(first_line_indent_cm=0, line_spacing=1.5,
                           space_before_pt=12, space_after_pt=12),
        )

        # 三级标题：黑体 12pt 加粗左对齐，段前段后各0.5行(≈6pt)
        ds.heading_styles[3] = (
            TextStyle(font_name_cjk="黑体", font_name_latin="Times New Roman",
                       font_size_pt=12.0, bold=True, alignment="LEFT"),
            ParagraphStyle(first_line_indent_cm=0, line_spacing=1.5,
                           space_before_pt=6, space_after_pt=6),
        )

        # 正文：宋体 11pt
        ds.body_style = TextStyle(
            font_name_cjk="宋体", font_name_latin="Times New Roman",
            font_size_pt=11.0, bold=False, alignment="JUSTIFY",
        )
        ds.body_para_style = ParagraphStyle(
            first_line_indent_cm=0.74, line_spacing=1.5,
        )

        # 三线表
        ds.table_style = TableStyle(
            top_border_sz=12,           # 1.5pt
            bottom_border_sz=12,        # 1.5pt
            inside_h_border_sz=4,       # 0.5pt
            inside_v_border_sz=0,
        )
        ds.table_cell_style = TextStyle(
            font_name_cjk="宋体", font_name_latin="Times New Roman",
            font_size_pt=10.0, bold=False,
        )
        ds.table_header_style = TextStyle(
            font_name_cjk="宋体", font_name_latin="Times New Roman",
            font_size_pt=10.0, bold=True, alignment="CENTER",
        )

        return ds

    # ── 组合构建 ────────────────────────────────────────────

    def build_format_spec(
        self,
        full_text: str,
        ref_docx: Optional[Path] = None,
        ref_txt: Optional[Path] = None,
        extra_info: Optional[Dict[str, Any]] = None,
    ) -> FormatSpec:
        """
        编排所有三个提取步骤，构建完整的 FormatSpec。

        Args:
            full_text: 解析后的标书全文（full_text.md 内容）
            ref_docx: 参考 DOCX 路径（用于样式捕获）
            ref_txt: 参考 TXT 路径（用于叙述模式提取）
            extra_info: 额外信息（如公司信息覆盖）

        Returns:
            完整的 FormatSpec 对象
        """
        spec = FormatSpec(
            spec_version="1.0",
            generated_at=datetime.datetime.now().isoformat(),
        )

        # ── 步骤1：提取格式规格 ──
        format_data = self.extract_format_spec_from_text(full_text)
        spec.source_found = format_data["source_found"]
        spec.source_section = format_data["source_section"]
        spec.attachments = format_data["attachments"]
        spec.technical_section_map = format_data["technical_section_map"]

        if not spec.source_found and self.config:
            # 尝试从配置加载默认格式模板
            default_template = None
            try:
                default_template = self.config.get_default_format_template()
            except AttributeError:
                pass
            if default_template and default_template.exists():
                print(f"    使用配置的默认格式模板: {default_template}")
                spec.attachments = [dict(a) for a in self.DEFAULT_ATTACHMENTS]

        # ── 步骤2：捕获参考样式 ──
        if ref_docx is None and self.config:
            try:
                ref_docx = self.config.get_reference_docx_path()
            except AttributeError:
                pass

        if ref_docx and ref_docx.exists():
            spec.document_styles = self.capture_reference_styles(ref_docx)
            print(f"    已捕获参考 DOCX 样式: {ref_docx}")
        else:
            spec.document_styles = self._get_default_styles()
            if ref_docx:
                print(f"    [WARN] 参考 DOCX 不存在: {ref_docx}，使用默认样式")

        # ── 步骤3：提取叙述模式 ──
        if ref_txt is None and self.config:
            try:
                ref_txt = self.config.get_reference_txt_path()
            except AttributeError:
                pass

        spec.narrative_patterns = self.extract_narrative_patterns(ref_txt)

        # ── 步骤4：TOC 配置 ──
        spec.toc_config = {
            "generate_toc": True,
            "toc_title": "目  录",
            "max_level": 3,
            "include_attachments": True,
        }
        if self.config:
            try:
                spec.toc_config["generate_toc"] = self.config.is_toc_enabled()
            except AttributeError:
                pass

        # ── 补充附件（若无从文本提取到） ──
        if not spec.attachments:
            spec.attachments = [dict(a) for a in self.DEFAULT_ATTACHMENTS]

        return spec

    def get_default_format_spec(self) -> FormatSpec:
        """
        返回可配置的默认格式规格（当招标文件中没有"投标文件格式"章节时使用）。

        可通过配置中的 format.default_format_template 加载自定义默认格式。
        """
        spec = FormatSpec(
            spec_version="1.0",
            generated_at=datetime.datetime.now().isoformat(),
            source_found=False,
            source_section="(默认格式)",
            attachments=[dict(a) for a in self.DEFAULT_ATTACHMENTS],
            technical_section_map=dict(self.DEFAULT_TECH_SECTION_MAP),
            document_styles=self._get_default_styles(),
            narrative_patterns=self._get_default_narrative_patterns(),
            toc_config={"generate_toc": True, "toc_title": "目  录", "max_level": 3},
        )

        # 尝试从配置加载自定义默认模板
        if self.config:
            try:
                default_template = self.config.get_default_format_template()
                if default_template and default_template.exists():
                    # 加载自定义模板的样式
                    spec.document_styles = self.capture_reference_styles(default_template)
                    print(f"    使用自定义默认格式模板: {default_template}")
            except AttributeError:
                pass

        return spec

    def build_format_spec_from_docx(self, templates_docx_path: Path) -> FormatSpec:
        """
        从预提取的 templates.docx 直接构建 FormatSpec。

        此方法用于 Stage 6 优先读取 extract_format_section.py 生成的模板文件。
        相比文本搜索方式，此方法直接从 DOCX 结构读取章节和样式，更准确。

        Args:
            templates_docx_path: templates/templates.docx 路径

        Returns:
            完整的 FormatSpec 对象
        """
        from docx import Document as DocxDoc
        from docx.oxml.ns import qn as _qn

        spec = FormatSpec(
            spec_version="1.0",
            generated_at=datetime.datetime.now().isoformat(),
            source_section="第五部分 投标文件格式",
            source_found=True,
            attachments=[],
            technical_section_map=dict(self.DEFAULT_TECH_SECTION_MAP),
            narrative_patterns=self._get_default_narrative_patterns(),
            toc_config={"generate_toc": True, "toc_title": "目  录", "max_level": 3},
        )

        try:
            doc = DocxDoc(str(templates_docx_path))
        except Exception as e:
            print(f"    [WARN] 无法打开模板文件 {templates_docx_path}: {e}")
            return self.get_default_format_spec()

        # ── 捕获样式 ──
        spec.document_styles = self.capture_reference_styles(templates_docx_path)

        # ── 遍历段落，按附件编号分段 ──
        current_attachment = None
        current_body_lines: List[str] = []
        all_attachments: List[Dict[str, Any]] = []

        # 先添加封面和目录
        all_attachments.append({
            "attachment_id": "封面", "name": "投标文件封面",
            "section_type": "cover", "body_text": "", "fields": {},
        })
        all_attachments.append({
            "attachment_id": "目录", "name": "投标文件总目录",
            "section_type": "toc", "body_text": "", "fields": {},
        })

        import re as _re

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # 检测附件标题：附件N 或 附件N-N
            att_match = _re.match(r'^(附件\d+(?:-\d+)?)\s*\n?(.*)', text)
            if att_match:
                # 保存上一个附件
                if current_attachment:
                    current_attachment["body_text"] = "\n".join(current_body_lines)
                    current_attachment["fields"] = self._extract_fields(
                        current_attachment["body_text"]
                    )
                    all_attachments.append(current_attachment)

                att_id = att_match.group(1)
                att_name = att_match.group(2).strip() if att_match.group(2) else att_id

                # 判断类型
                if att_id == "附件6":
                    att_type = "technical"
                elif att_id == "附件11":
                    att_type = "technical"
                else:
                    att_type = "business"

                current_attachment = {
                    "attachment_id": att_id,
                    "name": att_name,
                    "section_type": att_type,
                    "body_text": "",
                    "fields": {},
                }
                current_body_lines = []
            else:
                if current_attachment:
                    current_body_lines.append(text)

        # 保存最后一个附件
        if current_attachment:
            current_attachment["body_text"] = "\n".join(current_body_lines)
            current_attachment["fields"] = self._extract_fields(
                current_attachment["body_text"]
            )
            all_attachments.append(current_attachment)

        # 添加附件12（如果缺失）
        if not any(a["attachment_id"] == "附件12" for a in all_attachments):
            all_attachments.append({
                "attachment_id": "附件12", "name": "投标人认为需要提供的其他资料",
                "section_type": "business", "body_text": "", "fields": {},
            })

        spec.attachments = all_attachments
        print(f"    从模板 DOCX 提取: {len(all_attachments)} 个附件")
        return spec


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

def build_format_spec(
    full_text: str,
    ref_docx: Optional[Path] = None,
    ref_txt: Optional[Path] = None,
    config: Any = None,
) -> FormatSpec:
    """快速构建 FormatSpec。"""
    adapter = FormatAdapter(config)
    return adapter.build_format_spec(full_text, ref_docx, ref_txt)


def load_format_spec(json_path: Path) -> FormatSpec:
    """从 JSON 文件加载 FormatSpec。"""
    data = json.loads(json_path.read_text(encoding="utf-8"))

    # 恢复 DocumentStyles
    doc_styles = None
    if data.get("document_styles"):
        doc_styles = DocumentStyles.from_dict(data["document_styles"])

    return FormatSpec(
        spec_version=data.get("spec_version", "1.0"),
        generated_at=data.get("generated_at", ""),
        source_section=data.get("source_section", ""),
        source_found=data.get("source_found", False),
        attachments=data.get("attachments", []),
        technical_section_map=data.get("technical_section_map", {}),
        document_styles=doc_styles,
        narrative_patterns=data.get("narrative_patterns", {}),
        toc_config=data.get("toc_config", {}),
    )


def save_format_spec(spec: FormatSpec, output_path: Path) -> Path:
    """将 FormatSpec 保存为 JSON 文件。"""
    data = {
        "spec_version": spec.spec_version,
        "generated_at": spec.generated_at,
        "source_section": spec.source_section,
        "source_found": spec.source_found,
        "attachments": spec.attachments,
        "technical_section_map": spec.technical_section_map,
        "document_styles": spec.document_styles.to_dict() if spec.document_styles else None,
        "narrative_patterns": spec.narrative_patterns,
        "toc_config": spec.toc_config,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path
