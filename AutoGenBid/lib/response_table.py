"""
应答表生成器 — 从招标文件中提取"平台功能要求"表格，生成一对一应答表。

用途：
    Stage 9 使用此模块：
    1. 从 .cache/01_parsed/ 中提取 "平台功能要求" 表格
    2. 将每条要求与生成的投标内容进行匹配
    3. 生成 附件6 风格的 "技术一对一应答表" DOCX

用法:
    from lib.response_table import ResponseTableGenerator
    gen = ResponseTableGenerator(format_spec)
    table = gen.generate_response_docx(requirements, output_path, metadata)
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
from docx.shared import Cm, Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from lib.format_adapter import FormatSpec, DocumentStyles
from lib.docx_exporter import DocxExporter


# ═══════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════

@dataclass
class RequirementItem:
    """平台功能要求表格中的单条要求。"""
    seq: int                                # 序号
    module: str                             # 模块名（如 "智能分类", "智能解析"）
    parameter_requirement: str              # 功能参数要求全文
    source_section: str = ""                # 来源章节（如 "13.2.1.1"）
    matched_response: str = ""              # 匹配到的投标应答文本
    deviation: str = ""                     # 不再使用偏离说明
    confidence: float = 0.0                 # 匹配置信度


@dataclass
class ResponseTable:
    """单个策略的完整应答表。"""
    strategy_id: str
    strategy_name: str
    project_name: str = ""
    project_id: str = ""
    package_id: str = ""
    requirements: List[RequirementItem] = field(default_factory=list)
    table_title: str = "技术一对一应答表"
    declaration_text: str = "我单位郑重承诺：所提供的服务、人员及设备符合相关强制性规定。"
    generated_at: str = ""


# ═══════════════════════════════════════════════════════════════
# 应答表生成器
# ═══════════════════════════════════════════════════════════════

class ResponseTableGenerator:
    """从招标文件和生成内容中构建一对一应答表。"""

    # 应答措辞模板
    RESPONSE_TEMPLATES = {
        "full": "完全满足。{detail}",
        "partial": "基本满足。{detail}",
        "exceed": "完全满足并超越要求。{detail}",
        "reference": "详见技术方案{section}章节。{detail}",
    }

    def __init__(self, format_spec: Optional[FormatSpec] = None, config: Any = None):
        self.format_spec = format_spec
        self.config = config

    # ── 需求提取 ────────────────────────────────────────────

    def extract_platform_requirements(
        self,
        tables_json_path: Path,
        full_text_path: Path,
    ) -> List[RequirementItem]:
        """
        从 tables.json 和 full_text.md 中提取"平台功能要求"表格。

        识别策略：
        1. 在 full_text 中搜索 "平台功能要求" 或 "13.2.1"
        2. 找到附近的表格（tables.json 中位置靠近的表格）
        3. 解析表格行（处理合并单元格）
        4. 返回 RequirementItem 列表

        Args:
            tables_json_path: .cache/01_parsed/tables.json 路径
            full_text_path: .cache/01_parsed/full_text.md 路径

        Returns:
            解析后的 RequirementItem 列表
        """
        tables = []
        if tables_json_path.exists():
            tables = json.loads(tables_json_path.read_text(encoding="utf-8"))

        full_text = ""
        if full_text_path.exists():
            full_text = full_text_path.read_text(encoding="utf-8")

        requirements = []

        # ── 方法1：从 full_text 中找到的表格 markdown 直接解析 ──
        # 查找 "13.2.1 平台功能要求" 区域
        section_patterns = [
            r"13\.2\.1\s+平台功能要求.*?\n(.*?)(?=\n\d+\.\d+\.\d|\n13\.2\.2|\n\d+\.\d+[^\d])",
            r"平台功能要求\s*\n(.*?)(?=\n\d+\.\d+\.\d|\n13\.2\.2)",
        ]

        for pattern in section_patterns:
            m = re.search(pattern, full_text, re.DOTALL)
            if m:
                section_content = m.group(0)
                # 尝试提取表格
                table_start = section_content.find("|")
                if table_start >= 0:
                    table_text = section_content[table_start:]
                    parsed_reqs = self._parse_embedded_table(table_text)
                    if parsed_reqs:
                        requirements = parsed_reqs
                        break

        # ── 方法2：从 tables.json 中寻找 ──
        if not requirements:
            requirements = self._find_requirements_in_tables(tables, full_text)

        # ── 方法3：从 full_text 中按模式解析 ──
        if not requirements:
            requirements = self._parse_requirements_from_text(full_text)

        return requirements

    def _parse_embedded_table(self, table_text: str) -> List[RequirementItem]:
        """解析内嵌在 Markdown 中的平台功能要求表格。"""
        lines = [l.strip() for l in table_text.split("\n") if l.strip().startswith("|")]

        if len(lines) < 2:
            return []

        requirements = []
        current_module = ""
        current_section = ""
        seq = 0

        for line in lines:
            # 跳过分隔线
            if re.match(r"^\|[\s\-:|]+\|$", line):
                continue

            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) < 3:
                continue

            # 尝试解析：序号 | 模块 | 功能参数要求 | 应答名称章节
            try:
                seq_str = cells[0].strip()
                module_str = cells[1].strip() if len(cells) > 1 else ""
                requirement_str = cells[2].strip() if len(cells) > 2 else ""
                section_str = cells[3].strip() if len(cells) > 3 else ""
            except IndexError:
                continue

            # 序号可能是数字
            if seq_str.isdigit():
                seq = int(seq_str)
                if module_str:
                    current_module = module_str
                if section_str:
                    current_section = section_str

                # 合并需求文本（可能跨多个单元格）
                full_req = requirement_str
                if len(cells) > 4:
                    full_req += " " + " ".join(cells[4:])

                if full_req:
                    requirements.append(RequirementItem(
                        seq=seq,
                        module=current_module,
                        parameter_requirement=full_req[:500],
                        source_section=current_section,
                    ))
            elif seq_str and not seq_str.isdigit():
                # 可能是合并单元格的延续 — 追加到上一行
                if requirements and seq == requirements[-1].seq:
                    requirements[-1].parameter_requirement += " " + " ".join(cells)

        return requirements

    def _find_requirements_in_tables(
        self, tables: List[Dict], full_text: str
    ) -> List[RequirementItem]:
        """在 tables.json 中寻找平台功能要求表格。"""
        # 首先尝试匹配包含"功能要求"表的表头关键词
        header_keywords = [
            ["序号", "模块", "功能"],
            ["序号", "模块名称", "功能要求"],
            ["序号", "模块", "参数"],
            ["序号", "名称", "要求"],
        ]

        for table in tables:
            rows = table.get("rows", [])
            if not rows or len(rows) < 2:
                continue

            # 检查表头行
            header_row = rows[0]
            header_text = " ".join(str(c) for c in header_row if c)

            for hk in header_keywords:
                if all(kw in header_text for kw in hk):
                    reqs = self._parse_table_rows(rows)
                    if reqs:
                        return reqs

        # 后备：通过内容关键词搜索
        content_keywords = [
            "智能分类", "智能解析", "平台功能", "数据导出",
            "数据合并", "数据清洗", "数据异常", "数据统计",
            "功能要求", "参数要求",
        ]

        for table in tables:
            rows = table.get("rows", [])
            if not rows:
                continue

            flat_text = " ".join(" ".join(str(c) for c in row) for row in rows if row)
            if any(kw in flat_text for kw in content_keywords):
                reqs = self._parse_table_rows(rows)
                if reqs:
                    return reqs

        return []

    def _parse_table_rows(self, rows: List[List[str]]) -> List[RequirementItem]:
        """解析表格行数据为 RequirementItem 列表。"""
        requirements = []
        current_module = ""
        current_section = ""
        seq = 0

        for row in rows:
            if len(row) < 2:
                continue

            first_cell = row[0].strip()
            second_cell = row[1].strip() if len(row) > 1 else ""
            third_cell = row[2].strip() if len(row) > 2 else ""
            fourth_cell = row[3].strip() if len(row) > 3 else ""

            # 检查是否为表头行
            if first_cell in ("序号", "模块", "") and second_cell in ("模块", "功能参数要求", ""):
                continue

            # 序号
            if first_cell.isdigit():
                seq = int(first_cell)
            elif not first_cell:
                # 合并单元格延续 — 追加到上一行
                if requirements:
                    requirements[-1].parameter_requirement += " " + second_cell + " " + third_cell
                continue

            if second_cell.strip():
                current_module = second_cell.strip()
            if fourth_cell.strip():
                current_section = fourth_cell.strip()

            if third_cell.strip():
                requirements.append(RequirementItem(
                    seq=seq,
                    module=current_module,
                    parameter_requirement=third_cell[:500],
                    source_section=current_section,
                ))

        return requirements

    def _parse_requirements_from_text(self, full_text: str) -> List[RequirementItem]:
        """
        从 full_text.md 中按文本模式解析平台功能要求。

        识别 "13.2.1.X" 编号的子章节作为独立要求。
        """
        requirements = []
        seq = 0

        # 匹配 13.2.1.1 到 13.2.1.7 的子章节
        section_pattern = re.compile(
            r'13\.2\.1\.(\d+)\s+([^\n]+)\s*\n(.*?)(?=\n13\.2\.1\.\d+|\n13\.2\.2|\Z)',
            re.DOTALL,
        )

        for m in section_pattern.finditer(full_text):
            section_num = m.group(1)
            section_title = m.group(2).strip()
            section_content = m.group(3).strip()

            # 提取 "完全满足" 语句作为响应参考
            full_satisfy = re.findall(r'完全满足[^。；]*[。；]', section_content)
            response_hint = full_satisfy[0] if full_satisfy else section_content[:200]

            seq += 1
            requirements.append(RequirementItem(
                seq=seq,
                module=section_title,
                parameter_requirement=section_content[:500],
                source_section=f"13.2.1.{section_num}",
                matched_response=response_hint,
                confidence=0.9,
            ))

        return requirements

    # ── 响应匹配 ────────────────────────────────────────────

    def match_responses(
        self,
        requirements: List[RequirementItem],
        bid_draft_path: Path,
    ) -> List[RequirementItem]:
        """
        将提取的需求与生成的投标内容进行匹配。

        三层匹配策略：
        1. 直接章节引用匹配（13.2.1.1 → 查找对应章节）
        2. 关键词重叠评分
        3. 降级到全文本搜索

        Args:
            requirements: RequirementItem 列表
            bid_draft_path: 生成的 bid_draft.md 路径

        Returns:
            填充了 matched_response 的 RequirementItem 列表
        """
        if not bid_draft_path.exists():
            return requirements

        md_text = bid_draft_path.read_text(encoding="utf-8")

        for req in requirements:
            # 层级1：章节引用匹配
            response = self._find_section_in_markdown(md_text, req.source_section)
            if response and len(response) > 50:
                req.matched_response = response[:500]
                req.confidence = 0.85
                continue

            # 层级2：关键词重叠匹配
            response = self._keyword_match(md_text, req)
            if response and len(response) > 30:
                req.matched_response = response[:500]
                req.confidence = 0.6
                continue

            # 层级3：全文本搜索
            keywords = self._extract_keywords(req.parameter_requirement)
            best_match = ""
            best_score = 0
            paragraphs = md_text.split("\n\n")
            for para in paragraphs:
                if len(para) < 20:
                    continue
                score = sum(1 for kw in keywords if kw in para)
                if score > best_score:
                    best_score = score
                    best_match = para

            if best_match and best_score >= 2:
                req.matched_response = best_match[:500]
                req.confidence = 0.4
            else:
                req.matched_response = "详见技术方案相关章节。"
                req.confidence = 0.2

        return requirements

    def _find_section_in_markdown(self, md_text: str, section_ref: str) -> Optional[str]:
        """在 Markdown 中定位特定章节引用。"""
        if not section_ref:
            return None

        # 将 "13.2.1.1" 转换为可能的标题模式
        patterns = [
            rf'#+\s*{re.escape(section_ref)}[\s.]+[^\n]+\n(.*?)(?=\n#+\s|\Z)',
            rf'{re.escape(section_ref)}[\s\S]*?(?=\n\d+\.\d+\.\d+|\Z)',
        ]

        for pattern in patterns:
            m = re.search(pattern, md_text, re.DOTALL)
            if m:
                content = m.group(0)
                # 提取实质性内容（跳过标题行）
                lines = content.split("\n")
                body_lines = [l for l in lines if not l.startswith("#") and l.strip()]
                if body_lines:
                    return " ".join(body_lines[:10])

        return None

    def _keyword_match(self, md_text: str, req: RequirementItem) -> Optional[str]:
        """基于关键词重叠在 Markdown 中搜索最佳匹配段落。"""
        keywords = self._extract_keywords(req.parameter_requirement)
        if not keywords:
            return None

        paragraphs = md_text.split("\n\n")
        scored_paras = []

        for para in paragraphs:
            if len(para) < 30:
                continue
            score = 0
            for kw in keywords:
                if kw in para:
                    score += 1
                # 部分匹配
                for i in range(len(kw) - 1, 1, -1):
                    if kw[:i] in para:
                        score += 0.3
                        break
            if score > 0:
                scored_paras.append((score, para))

        scored_paras.sort(key=lambda x: x[0], reverse=True)
        if scored_paras and scored_paras[0][0] >= 1.5:
            return scored_paras[0][1]

        return None

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        """从需求文本中提取关键词。"""
        # 移除常见停用词和标点
        stop_words = {"的", "和", "与", "及", "或", "对", "在", "为", "是",
                      "了", "使用", "进行", "具有", "包括", "一个", "一种",
                      "等", "等。", "：", "。", "，", "、"}
        # 提取有意义的短语
        words = []
        # 按逗号和句号分割
        segments = re.split(r'[，。,\.\s]+', text)
        for seg in segments:
            seg = seg.strip()
            if len(seg) >= 2 and seg not in stop_words:
                words.append(seg)

        # 也提取连续的中文词组（2-4字符）
        import re as _re
        phrases = _re.findall(r'[一-鿿]{2,4}', text)
        for p in phrases:
            if p not in stop_words and p not in words:
                words.append(p)

        return words[:15]

    # ── 应答表 DOCX 生成 ────────────────────────────────────

    def generate_response_docx(
        self,
        requirements: List[RequirementItem],
        output_path: Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """
        生成"技术一对一应答表" DOCX（A4竖排，4列，1:2:7:2列宽比）。

        表格结构：
        序号 | 模块 | 功能参数要求 | 应答章节

        Args:
            requirements: 匹配后的 RequirementItem 列表
            output_path: 输出 DOCX 路径
            metadata: 文档元数据（项目名、编号、包号等）

        Returns:
            输出文件路径
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        meta = metadata or {}

        # 获取样式
        styles = self.format_spec.document_styles if self.format_spec else DocumentStyles()

        doc = DocxExporter.create_template_from_spec(styles)

        # ── 标题：技术一对一应答表（黑体 16pt 加粗居中）──
        title_para = doc.add_paragraph()
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_run = title_para.add_run(meta.get('response_table_title', '技术一对一应答表'))
        title_run.font.size = Pt(16)
        title_run.bold = True
        title_run.font.name = "Times New Roman"
        title_run._element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")

        doc.add_paragraph()

        # ── 项目信息 ──
        info_lines = [
            f"项目名称：{meta.get('project_name', '')}",
            f"项目编号：{meta.get('project_id', '')}",
            f"包    号：{meta.get('package_id', '')}",
        ]
        for line in info_lines:
            info_para = doc.add_paragraph()
            run = info_para.add_run(line)
            run.font.size = Pt(11)
            if styles.body_style:
                DocxExporter._apply_text_style_to_run(run, styles.body_style)

        doc.add_paragraph()

        # ── 声明文本 ──
        declaration = meta.get(
            'declaration_text',
            '我单位郑重承诺：以下应答表中描述的全部技术方案内容均真实、准确，'
            '并已在投标技术方案中详细阐述。'
        )
        decl_para = doc.add_paragraph()
        decl_run = decl_para.add_run(declaration)
        decl_run.font.size = Pt(10)
        decl_para.paragraph_format.first_line_indent = Cm(0.74)

        doc.add_paragraph()

        # ── 4列响应表：序号 | 模块 | 功能参数要求 | 应答章节 ──
        headers = ["序号", "模块", "功能参数要求", "应答章节"]
        table = doc.add_table(rows=len(requirements) + 1, cols=len(headers))
        table.autofit = False
        table.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # 列宽按 1:2:7:2 比例分配（可用宽度 16.0cm = A4竖排 21cm - 2.5cm*2边距）
        usable_width_cm = 16.0
        total_ratio = 12
        col_widths = [
            Cm(usable_width_cm * r / total_ratio)
            for r in (1, 2, 7, 2)
        ]
        for j, width in enumerate(col_widths):
            for row in table.rows:
                try:
                    row.cells[j].width = width
                except Exception:
                    pass

        # 表头（黑体加粗居中）
        for j, header in enumerate(headers):
            cell = table.rows[0].cells[j]
            cell.text = ""
            run = cell.paragraphs[0].add_run(header)
            run.bold = True
            run.font.size = Pt(10)
            run.font.name = "Times New Roman"
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

        # 数据行
        for i, req in enumerate(requirements):
            row = table.rows[i + 1]
            # 应答章节格式：对应技术方案章节：XX.XX.XX 章节名称
            section_ref = req.matched_response if req.matched_response else (
                f"对应技术方案章节：{req.source_section}" if req.source_section else ""
            )
            row_data = [
                str(req.seq),
                req.module,
                req.parameter_requirement[:300],
                section_ref,
            ]
            for j, cell_text in enumerate(row_data):
                cell = row.cells[j]
                cell.text = ""
                run = cell.paragraphs[0].add_run(cell_text)
                run.font.size = Pt(9)
                run.font.name = "Times New Roman"
                run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

                # 序号列居中，其余左对齐
                if j == 0:
                    cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                else:
                    cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT

        # 应用三线表边框
        if styles.table_style:
            DocxExporter._apply_three_line_borders_styled(table, styles.table_style)

        doc.add_paragraph()

        # ── 注释 ──
        notes = [
            "注：",
            "1. 本应答表建立了招标文件功能参数要求与投标技术方案章节之间的一对一映射关系。",
            "2. 功能参数要求列描述的是我方技术方案对该需求的具体实现方式。",
            "3. 应答章节列标注了技术方案中对应的章节位置，方便评标专家查阅。",
        ]
        for note in notes:
            note_para = doc.add_paragraph()
            note_run = note_para.add_run(note)
            note_run.font.size = Pt(9)
            note_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

        # ── 投标人信息 ──
        doc.add_paragraph()
        company_name = meta.get('company_name', '')
        company_info_para = doc.add_paragraph()
        company_info_para.add_run(f"投标人名称：{company_name}").font.size = Pt(11)
        doc.add_paragraph()
        date_para = doc.add_paragraph()
        date_para.add_run(f"日期：    年    月    日").font.size = Pt(11)

        # ── 保存 ──
        doc.save(str(output_path))
        print(f"    [应答表] 生成 {len(requirements)} 条需求 → {output_path}")
        return output_path

    def _format_response(self, req: RequirementItem) -> str:
        """格式化单条应答文本。"""
        if req.matched_response:
            return req.matched_response[:300]

        # 生成默认应答
        if req.confidence >= 0.8:
            return self.RESPONSE_TEMPLATES["full"].format(
                detail=f"我方方案已全面覆盖{req.module}功能的全部技术要求。"
            )
        elif req.confidence >= 0.4:
            return self.RESPONSE_TEMPLATES["reference"].format(
                section=req.source_section,
                detail=f"我方方案已覆盖{req.module}功能的核心技术要求。"
            )
        else:
            return f"满足{req.module}功能要求。详见技术方案对应章节。"

    # ── 生成摘要报告 ────────────────────────────────────────

    def generate_summary(self, requirements: List[RequirementItem]) -> Dict[str, Any]:
        """生成应答表的统计摘要。"""
        total = len(requirements)
        matched_high = sum(1 for r in requirements if r.confidence >= 0.8)
        matched_medium = sum(1 for r in requirements if 0.4 <= r.confidence < 0.8)
        matched_low = sum(1 for r in requirements if r.confidence < 0.4)

        modules = {}
        for r in requirements:
            modules[r.module] = modules.get(r.module, 0) + 1

        return {
            "total_requirements": total,
            "matched_high_confidence": matched_high,
            "matched_medium_confidence": matched_medium,
            "matched_low_confidence": matched_low,
            "coverage_rate": round((matched_high + matched_medium) / max(1, total), 2),
            "modules": modules,
        }


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

def generate_response_table(
    requirements: List[RequirementItem],
    output_path: Path,
    metadata: Optional[Dict[str, Any]] = None,
    format_spec: Optional[FormatSpec] = None,
) -> Path:
    """快速生成应答表 DOCX。"""
    gen = ResponseTableGenerator(format_spec)
    return gen.generate_response_docx(requirements, output_path, metadata)
