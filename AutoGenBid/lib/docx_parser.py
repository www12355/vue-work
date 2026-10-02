"""
标书文档解析器 — 使用 python-docx 解析 .docx 标书文件，
提取段落、标题、表格、图片，输出结构化 JSON/Markdown 到 .cache/01_parsed/。

用法:
    from lib.docx_parser import BidDocumentParser
    parser = BidDocumentParser(Path("标书文件.docx"), Path(".cache/01_parsed"))
    parsed = parser.parse()
"""

from __future__ import annotations

import sys
import io
import json
import os
import re
import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ═══════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════

@dataclass
class ParagraphData:
    """段落实体。"""
    index: int
    text: str
    style: str
    heading_level: Optional[int] = None
    is_list: bool = False
    has_bold: bool = False
    font_name: Optional[str] = None


@dataclass
class TableData:
    """表格实体。"""
    index: int
    rows: List[List[str]]
    caption: str = ""


@dataclass
class ImageData:
    """图片实体。"""
    index: int
    name: str
    width_cm: Optional[float] = None
    height_cm: Optional[float] = None
    data: Optional[bytes] = None


@dataclass
class Section:
    """章节实体（递归树结构）。"""
    level: int
    title: str
    start_index: int
    end_index: int = -1
    children: List[Section] = field(default_factory=list)
    paragraph_indices: List[int] = field(default_factory=list)


@dataclass
class ParsedDocument:
    """完整解析后的文档。"""
    source_path: str
    parsed_at: str
    sections: List[Section] = field(default_factory=list)
    paragraphs: List[ParagraphData] = field(default_factory=list)
    tables: List[TableData] = field(default_factory=list)
    images: List[ImageData] = field(default_factory=list)
    total_paragraphs: int = 0
    total_tables: int = 0
    total_images: int = 0


# ═══════════════════════════════════════════════════════════════
# 解析器
# ═══════════════════════════════════════════════════════════════

class BidDocumentParser:
    """标书 .docx 解析引擎。"""

    # 中文标书中常见的标题样式名
    HEADING_STYLE_PATTERNS = [
        re.compile(r"^heading\s*(\d+)$", re.IGNORECASE),
        re.compile(r"^标题\s*(\d+)$"),
        re.compile(r"^Heading\s*(\d+)$"),
        re.compile(r"^\d+$"),  # 纯数字样式名（如 "1", "2"）
    ]

    # 被认为是正文的样式名
    BODY_STYLE_NAMES = {"Normal", "Body Text", "List Paragraph", "正文", "normal", "body text"}

    MAX_WIDTH_CM = 14.0

    def __init__(self, docx_path: Path, output_dir: Path):
        self.docx_path = Path(docx_path)
        self.output_dir = Path(output_dir)
        self.doc: Optional[DocxDocument] = None
        self.images_dir = self.output_dir / "images"

    # ── 主入口 ──────────────────────────────────────────────

    def parse(self) -> ParsedDocument:
        """解析 .docx 文件，返回结构化 ParsedDocument。"""
        if not self.docx_path.exists():
            raise FileNotFoundError(f"标书文件不存在: {self.docx_path}")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

        self.doc = Document(str(self.docx_path))
        self._images: List[ImageData] = []  # 临时收集图片

        parsed = ParsedDocument(
            source_path=str(self.docx_path.resolve()),
            parsed_at=datetime.datetime.now().isoformat(),
        )

        # 逐块遍历文档
        block_index = 0
        for block in self._iter_block_items(self.doc):
            if isinstance(block, Paragraph):
                pdata = self._extract_paragraph(block, block_index, self._images)
                parsed.paragraphs.append(pdata)
                block_index += 1
            elif isinstance(block, DocxTable):
                tdata = self._extract_table(block, block_index)
                parsed.tables.append(tdata)
                block_index += 1

        parsed.images = self._images

        parsed.total_paragraphs = len(parsed.paragraphs)
        parsed.total_tables = len(parsed.tables)
        parsed.total_images = len(parsed.images)

        # 构建章节树
        parsed.sections = self._build_section_tree(parsed.paragraphs)

        # 保存所有输出
        self._save_outputs(parsed)

        # 写解析日志
        self._write_log(parsed)

        return parsed

    # ── 块迭代器 ────────────────────────────────────────────

    @staticmethod
    def _iter_block_items(parent) -> Iterator[Union[Paragraph, DocxTable]]:
        """
        按文档顺序迭代段落和表格。
        参考 Extract_Word.py 的 iter_block_items()。
        """
        from docx.document import Document as _Doc
        parent_elm = parent.element.body if isinstance(parent, _Doc) else parent._element
        for child in parent_elm.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, parent)
            elif isinstance(child, CT_Tbl):
                yield DocxTable(child, parent)

    # ── 段落提取 ────────────────────────────────────────────

    def _extract_paragraph(self, para: Paragraph, index: int, images: List[ImageData]) -> ParagraphData:
        """提取单个段落的内容和元数据。"""
        style_name = para.style.name if para.style else "Normal"
        text = para.text.strip()
        heading_level = self._detect_heading_level(style_name)
        is_list = self._is_list_paragraph(para)
        has_bold = any(run.bold for run in para.runs if run.bold)

        # 提取图片
        for run in para.runs:
            img = self._extract_image_from_run(run, len(images))
            if img:
                images.append(img)

        # 获取字体名
        font_name = None
        if para.runs:
            first_run = para.runs[0]
            font_name = first_run.font.name if first_run.font.name else None

        return ParagraphData(
            index=index,
            text=text,
            style=style_name,
            heading_level=heading_level,
            is_list=is_list,
            has_bold=has_bold,
            font_name=font_name,
        )

    def _detect_heading_level(self, style_name: str) -> Optional[int]:
        """从 Word 样式名检测标题级别。"""
        for pattern in self.HEADING_STYLE_PATTERNS:
            m = pattern.match(style_name)
            if m:
                level = int(m.group(1))
                return min(level, 6)  # 限制最大 6 级
        return None

    @staticmethod
    def _is_list_paragraph(para: Paragraph) -> bool:
        """判断段落是否为列表段落。"""
        if para.style.name == "List Paragraph":
            return True
        # 检查 XML 中是否有 numPr 元素（有序/无序列表标记）
        if para._element.xpath(".//w:numPr"):
            return True
        return False

    # ── 图片提取 ────────────────────────────────────────────

    def _extract_image_from_run(self, run, index: int) -> Optional[ImageData]:
        """
        从 run 的 XML 中提取内嵌图片。
        参考 Extract_Word.py 的 get_image_from_run()。
        """
        drawing_elements = run._element.xpath(".//a:blip")
        if not drawing_elements:
            return None

        try:
            embed = drawing_elements[0].get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
            )
            image_part = run.part.related_parts[embed]
            image_data = image_part.blob

            # 图片尺寸
            width_cm = None
            height_cm = None
            extent_el = run._element.xpath(".//wp:extent")
            if extent_el:
                cx = int(extent_el[0].get("cx", 0))
                cy = int(extent_el[0].get("cy", 0))
                width_cm = cx / 914400 * 2.54
                height_cm = cy / 914400 * 2.54

            image_name = os.path.basename(image_part.partname) if image_part.partname else f"image_{index:03d}.png"

            # 保存图片到 images_dir
            img_path = self.images_dir / image_name
            img_path.write_bytes(image_data)

            return ImageData(
                index=index,
                name=image_name,
                width_cm=round(width_cm, 2) if width_cm else None,
                height_cm=round(height_cm, 2) if height_cm else None,
                data=None,  # 不保留 bytes，已存入文件
            )
        except Exception as e:
            print(f"    [WARN] 图片提取失败 (index {index}): {e}")
            return None

    # ── 表格提取 ────────────────────────────────────────────

    def _extract_table(self, table: DocxTable, index: int) -> TableData:
        """提取表格为二维数组。"""
        rows_data = []
        for row in table.rows:
            row_data = []
            for cell in row.cells:
                cell_text = ""
                for cell_para in cell.paragraphs:
                    cell_text += cell_para.text.strip()
                row_data.append(cell_text)
            rows_data.append(row_data)
        return TableData(index=index, rows=rows_data)

    # ── 章节树构建 ──────────────────────────────────────────

    def _build_section_tree(self, paragraphs: List[ParagraphData]) -> List[Section]:
        """根据标题层级构建章节树。"""
        sections: List[Section] = []
        stack: List[Section] = []  # 用于跟踪父节点

        current_section = Section(level=0, title="(文档根)", start_index=0)
        current_section.paragraph_indices = []

        for i, para in enumerate(paragraphs):
            if para.heading_level is not None:
                level = para.heading_level

                # 弹出比当前级别更深或同级的节点
                while stack and stack[-1].level >= level:
                    finished = stack.pop()
                    finished.end_index = i - 1
                    parent = stack[-1] if stack else current_section
                    parent.children.append(finished)

                new_sec = Section(
                    level=level,
                    title=para.text,
                    start_index=i,
                )
                stack.append(new_sec)

        # 弹出剩余的
        while stack:
            finished = stack.pop()
            finished.end_index = len(paragraphs) - 1
            parent = stack[-1] if stack else current_section
            parent.children.append(finished)

        # 收集每个 section 内的段落索引
        for sec in self._iter_sections(current_section):
            if sec.start_index >= 0:
                sec.paragraph_indices = self._collect_paragraph_indices(sec, paragraphs)

        return current_section.children

    @staticmethod
    def _iter_sections(root: Section):
        """递归遍历所有 Section 节点。"""
        yield root
        for child in root.children:
            yield from BidDocumentParser._iter_sections(child)

    @staticmethod
    def _collect_paragraph_indices(section: Section, paragraphs: List[ParagraphData]) -> List[int]:
        """收集某章节范围内的所有非标题段落索引。"""
        indices = []
        end = section.end_index if section.end_index >= 0 else len(paragraphs) - 1
        for i in range(section.start_index, end + 1):
            if paragraphs[i].heading_level is None or i == section.start_index:
                indices.append(i)
        return indices

    # ── 启发式需求提取 ──────────────────────────────────────

    def extract_requirements_heuristic(self, parsed: ParsedDocument) -> List[Dict[str, Any]]:
        """
        启发式提取需求：查找 ★、▲、必须、应、要求 等关键词标记。
        返回需求列表，供后续 AI 精确提取参考。
        """
        req_keywords = ["★", "▲", "必须", "应满足", "要求", "需具备", "须"]
        requirements = []
        req_id = 0

        for para in parsed.paragraphs:
            text = para.text
            if not text:
                continue
            for kw in req_keywords:
                if kw in text:
                    req_id += 1
                    requirements.append({
                        "req_id": f"REQ-H{req_id:04d}",
                        "paragraph_index": para.index,
                        "text": text[:500],
                        "matched_keyword": kw,
                        "heading_level": para.heading_level,
                        "style": para.style,
                    })
                    break

        return requirements

    # ── 保存输出 ────────────────────────────────────────────

    def _save_outputs(self, parsed: ParsedDocument) -> None:
        """将所有解析结果写入 .cache/01_parsed/。"""

        # 完整文本 (Markdown)
        md_lines = []
        for para in parsed.paragraphs:
            if para.heading_level:
                prefix = "#" * min(para.heading_level, 6)
                md_lines.append(f"\n{prefix} {para.text}\n")
            elif para.text:
                md_lines.append(f"{para.text}\n")

        full_text_path = self.output_dir / "full_text.md"
        full_text_path.write_text("".join(md_lines), encoding="utf-8")

        # 表格 JSON
        tables_path = self.output_dir / "tables.json"
        tables_path.write_text(
            json.dumps([asdict(t) for t in parsed.tables], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 章节树 JSON
        sections_path = self.output_dir / "sections.json"
        sections_path.write_text(
            json.dumps(self._section_to_dict(parsed.sections), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 段落 JSONL
        paragraphs_path = self.output_dir / "paragraphs.jsonl"
        with open(paragraphs_path, "w", encoding="utf-8") as f:
            for para in parsed.paragraphs:
                f.write(json.dumps(asdict(para), ensure_ascii=False) + "\n")

        # 文档完整结构
        structure_path = self.output_dir / "document_structure.json"
        structure_path.write_text(
            json.dumps(self._parsed_to_dict(parsed), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 启发式需求
        heuristic_reqs = self.extract_requirements_heuristic(parsed)
        reqs_path = self.output_dir / "heuristic_requirements.json"
        reqs_path.write_text(
            json.dumps(heuristic_reqs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_log(self, parsed: ParsedDocument) -> None:
        """写解析日志。"""
        log_path = self.output_dir / "parse_log.txt"
        lines = [
            f"标书解析日志",
            f"================",
            f"源文件: {parsed.source_path}",
            f"解析时间: {parsed.parsed_at}",
            f"总段落数: {parsed.total_paragraphs}",
            f"总表格数: {parsed.total_tables}",
            f"总图片数: {parsed.total_images}",
            f"总章节数(一级): {len(parsed.sections)}",
            f"",
            f"章节结构:",
        ]
        for sec in parsed.sections:
            lines.append(f"  {'  ' * (sec.level - 1)}[{sec.level}] {sec.title} (段落 {sec.start_index}-{sec.end_index})")
            for sub in sec.children:
                lines.append(f"    {'  ' * (sub.level - 1)}[{sub.level}] {sub.title} (段落 {sub.start_index}-{sub.end_index})")

        log_path.write_text("\n".join(lines), encoding="utf-8")

    # ── JSON 序列化辅助 ─────────────────────────────────────

    @staticmethod
    def _section_to_dict(sections: List[Section]) -> List[Dict]:
        result = []
        for sec in sections:
            d = {
                "level": sec.level,
                "title": sec.title,
                "start_index": sec.start_index,
                "end_index": sec.end_index,
                "paragraph_count": len(sec.paragraph_indices),
                "children": BidDocumentParser._section_to_dict(sec.children),
            }
            result.append(d)
        return result

    @staticmethod
    def _parsed_to_dict(parsed: ParsedDocument) -> Dict[str, Any]:
        return {
            "source_path": parsed.source_path,
            "parsed_at": parsed.parsed_at,
            "total_paragraphs": parsed.total_paragraphs,
            "total_tables": parsed.total_tables,
            "total_images": parsed.total_images,
            "sections": BidDocumentParser._section_to_dict(parsed.sections),
            "image_names": [img.name for img in parsed.images],
        }

    # ── 便捷方法 ────────────────────────────────────────────

    def get_full_text(self) -> str:
        """返回解析后的纯文本。"""
        path = self.output_dir / "full_text.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def get_sections_json(self) -> List[Dict]:
        path = self.output_dir / "sections.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return []

    def get_heuristic_requirements(self) -> List[Dict]:
        path = self.output_dir / "heuristic_requirements.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return []

    # ── 文档样式提取（供 Stage 6 格式适配使用） ────────────

    def extract_document_styles(self) -> Dict[str, Any]:
        """
        仅提取 DOCX 的排版格式元数据（不提取内容）。
        供 Stage 6 FormatAdapter 捕获参考文档样式使用。

        返回包含页面尺寸、页边距、各级标题样式、正文样式、
        表格边框样式的字典。

        Returns:
            {
                "page": {width_cm, height_cm, margins},
                "headings": {level: {text_style, paragraph_style}},
                "body": {text_style, paragraph_style},
                "tables": [{borders, cell_styles}],
                "source_path": str,
            }
        """
        if self.doc is None:
            try:
                self.doc = Document(str(self.docx_path))
            except Exception as e:
                return {"error": str(e), "source_path": str(self.docx_path)}

        result = {
            "source_path": str(self.docx_path.resolve()),
            "extracted_at": datetime.datetime.now().isoformat(),
            "page": {},
            "headings": {},
            "body": {},
            "tables": [],
        }

        # ── 页面设置 ──
        for section in self.doc.sections:
            result["page"] = {
                "width_cm": round(section.page_width.cm, 2) if section.page_width else 21.0,
                "height_cm": round(section.page_height.cm, 2) if section.page_height else 29.7,
                "margin_top_cm": round(section.top_margin.cm, 2) if section.top_margin else 2.5,
                "margin_bottom_cm": round(section.bottom_margin.cm, 2) if section.bottom_margin else 2.5,
                "margin_left_cm": round(section.left_margin.cm, 2) if section.left_margin else 2.5,
                "margin_right_cm": round(section.right_margin.cm, 2) if section.right_margin else 2.5,
            }
            break

        # ── 段落样式收集 ──
        heading_samples: Dict[int, List[Dict]] = {}
        body_text_styles: List[Dict] = []
        body_para_styles: List[Dict] = []

        for block in self._iter_block_items(self.doc):
            if isinstance(block, Paragraph):
                para = block
                text_style = self._extract_style_from_paragraph_static(para)
                para_style = self._extract_paragraph_format_static(para)

                heading_level = self._detect_heading_level(para.style.name if para.style else "Normal")
                if heading_level and 1 <= heading_level <= 3 and para.text.strip():
                    if heading_level not in heading_samples:
                        heading_samples[heading_level] = []
                    heading_samples[heading_level].append({
                        "text": text_style,
                        "paragraph": para_style,
                        "sample_text": para.text.strip()[:60],
                    })
                elif para.text.strip() and heading_level is None:
                    body_text_styles.append(text_style)
                    body_para_styles.append(para_style)

            elif isinstance(block, DocxTable):
                table_style = self._extract_style_from_table_static(block)
                if table_style:
                    result["tables"].append(table_style)

        # ── 聚合标题样式 ──
        for level in range(1, 4):
            if level in heading_samples and heading_samples[level]:
                result["headings"][str(level)] = heading_samples[level][:3]  # 最多3个样本

        # ── 聚合正文样式 ──
        if body_text_styles:
            # 取最常见的字体
            from collections import Counter
            cjk_counter = Counter(s.get("font_name_cjk") for s in body_text_styles if s.get("font_name_cjk"))
            latin_counter = Counter(s.get("font_name_latin") for s in body_text_styles if s.get("font_name_latin"))
            sizes = [s.get("font_size_pt") for s in body_text_styles if s.get("font_size_pt")]
            bold_ratio = sum(1 for s in body_text_styles if s.get("bold")) / max(1, len(body_text_styles))

            result["body"]["text_style"] = {
                "font_name_cjk": cjk_counter.most_common(1)[0][0] if cjk_counter else "宋体",
                "font_name_latin": latin_counter.most_common(1)[0][0] if latin_counter else "Times New Roman",
                "font_size_pt": round(sum(sizes) / len(sizes), 1) if sizes else 11.0,
                "bold": bold_ratio > 0.5,
                "sample_count": len(body_text_styles),
            }

        if body_para_styles:
            indent_vals = [s.get("first_line_indent_cm") for s in body_para_styles if s.get("first_line_indent_cm") is not None]
            spacing_vals = [s.get("line_spacing") for s in body_para_styles if s.get("line_spacing") is not None]
            result["body"]["paragraph_style"] = {
                "first_line_indent_cm": round(sum(indent_vals) / len(indent_vals), 2) if indent_vals else 0.74,
                "line_spacing": round(sum(spacing_vals) / len(spacing_vals), 2) if spacing_vals else 1.5,
                "sample_count": len(body_para_styles),
            }

        return result

    @staticmethod
    def _extract_style_from_paragraph_static(para: Paragraph) -> Dict[str, Any]:
        """静态方法：从段落中提取文字样式（供 extract_document_styles 使用）。"""
        style = {
            "font_name_cjk": None,
            "font_name_latin": None,
            "font_size_pt": None,
            "bold": False,
            "italic": False,
            "color_rgb": None,
            "alignment": None,
        }

        if para.runs:
            for run in para.runs:
                if run.text.strip():
                    rpr = run._element.rPr
                    if rpr is not None:
                        rFonts = rpr.find(qn("w:rFonts"))
                        if rFonts is not None:
                            style["font_name_cjk"] = rFonts.get(qn("w:eastAsia"))
                            style["font_name_latin"] = rFonts.get(qn("w:ascii")) or rFonts.get(qn("w:hAnsi"))

                    if not style["font_name_latin"]:
                        style["font_name_latin"] = run.font.name

                    style["font_size_pt"] = run.font.size.pt if run.font.size else None
                    style["bold"] = run.bold if run.bold is not None else False
                    style["italic"] = run.italic if run.italic is not None else False

                    if run.font.color and run.font.color.rgb:
                        style["color_rgb"] = str(run.font.color.rgb)

                    alignment_map = {0: "LEFT", 1: "CENTER", 2: "RIGHT", 3: "JUSTIFY"}
                    style["alignment"] = alignment_map.get(para.alignment) if para.alignment is not None else None
                    break

        return style

    @staticmethod
    def _extract_paragraph_format_static(para: Paragraph) -> Dict[str, Any]:
        """静态方法：从段落中提取段落格式（供 extract_document_styles 使用）。"""
        fmt = {
            "first_line_indent_cm": None,
            "line_spacing": None,
            "line_spacing_exact_pt": None,
            "space_before_pt": None,
            "space_after_pt": None,
            "outline_level": None,
            "alignment": None,
        }
        pf = para.paragraph_format

        if pf.first_line_indent:
            fmt["first_line_indent_cm"] = round(pf.first_line_indent.cm, 2)

        if pf.line_spacing is not None:
            try:
                fmt["line_spacing"] = round(float(pf.line_spacing), 2)
            except TypeError:
                fmt["line_spacing_exact_pt"] = pf.line_spacing.pt if hasattr(pf.line_spacing, 'pt') else None

        if pf.space_before:
            fmt["space_before_pt"] = round(pf.space_before.pt, 2)
        if pf.space_after:
            fmt["space_after_pt"] = round(pf.space_after.pt, 2)

        ppr = para._element.pPr
        if ppr is not None:
            outline_lvl = ppr.find(qn("w:outlineLvl"))
            if outline_lvl is not None:
                fmt["outline_level"] = int(outline_lvl.get(qn("w:val"), "0"))

        alignment_map = {0: "LEFT", 1: "CENTER", 2: "RIGHT", 3: "JUSTIFY"}
        fmt["alignment"] = alignment_map.get(para.alignment) if para.alignment is not None else None

        return fmt

    @staticmethod
    def _extract_style_from_table_static(table: DocxTable) -> Optional[Dict[str, Any]]:
        """静态方法：从表格中提取边框样式（供 extract_document_styles 使用）。"""
        tbl_pr = table._element.tblPr
        if tbl_pr is None:
            return None

        borders = tbl_pr.find(qn("w:tblBorders"))
        if borders is None:
            return None

        result = {
            "rows": len(table.rows),
            "cols": len(table.columns),
            "borders": {},
        }

        border_tags = ["top", "bottom", "left", "right", "insideH", "insideV"]
        for tag in border_tags:
            el = borders.find(qn(f"w:{tag}"))
            if el is not None:
                result["borders"][tag] = {
                    "val": el.get(qn("w:val")),
                    "sz": el.get(qn("w:sz")),
                    "color": el.get(qn("w:color")),
                }

        return result if result["borders"] else None


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

def parse_bid_document(docx_path: Path, cache_dir: Path) -> ParsedDocument:
    """快速解析标书文档。"""
    parser = BidDocumentParser(docx_path, cache_dir / "01_parsed")
    return parser.parse()
