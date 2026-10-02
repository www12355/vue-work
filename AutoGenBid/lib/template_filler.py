"""
模板构建与商务填充器 — 根据 FormatSpec 构建 DOCX 模板，填充商务附件。

用途：
    Stage 7 使用此模块：
    1. 创建与"投标文件格式"结构完全匹配的 DOCX 模板
    2. 填充所有商务附件（逐字从原始招标文件复制，不修改）
    3. 为技术章节插入结构化占位符

用法:
    from lib.template_filler import TemplateFiller
    filler = TemplateFiller(format_spec)
    templates = filler.build_templates(strategies, output_dir)
"""

from __future__ import annotations

import sys
import json
import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from docx import Document
from docx.shared import Cm, Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from lib.format_adapter import FormatSpec, DocumentStyles, TextStyle, ParagraphStyle
from lib.docx_exporter import DocxExporter


# ═══════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════

@dataclass
class TemplateSection:
    """模板文档中的一个章节。"""
    section_id: str
    attachment_id: str                     # "附件1", "附件6", 等
    title: str
    section_type: str                      # "business", "technical", "toc", "cover"
    page_number: int = 0
    content: str = ""                      # 已填充的内容（Markdown 或占位符标记）
    is_filled: bool = False
    placeholder_marker: str = ""           # 《TECH:13.1:项目服务方案》


@dataclass
class TemplateDocument:
    """代表一个完整的投标模板文档。"""
    strategy_id: str
    strategy_name: str
    template_path: Path = field(default_factory=Path)
    sections_path: Path = field(default_factory=Path)
    sections: List[Dict[str, Any]] = field(default_factory=list)
    total_pages_estimate: int = 0


# ═══════════════════════════════════════════════════════════════
# 模板填充器
# ═══════════════════════════════════════════════════════════════

class TemplateFiller:
    """根据格式规格构建 DOCX 模板并填充商务附件。"""

    # 技术章节到模板占位符的映射
    TECH_CHAPTER_MAP = {
        "项目背景与需求分析": "13.1",
        "总体技术架构设计": "13.2",
        "核心功能模块技术方案": "13.2.1",
        "AI模型与智能化能力": "13.2.1.7",
        "项目重点难点与应对": "13.2.2",
        "人员配置方案": "13.3",
        "项目进度安排": "13.4",
        "服务质量保证与验收": "13.5",
    }

    # 商务附件 ID 列表（不应由 AI 修改）
    BUSINESS_ATTACHMENT_IDS = {
        "封面", "目录", "评分索引",
        "附件1", "附件2", "附件2-1", "附件3", "附件4", "附件5",
        "附件7", "附件8", "附件9-1", "附件9-2", "附件10", "附件12",
    }

    # 技术附件 ID 列表（将由 AI 生成的内容填充）
    TECHNICAL_ATTACHMENT_IDS = {
        "附件6", "附件11",
    }

    def __init__(self, format_spec: FormatSpec, config: Any = None):
        """
        Args:
            format_spec: 从 Stage 6 构建的 FormatSpec
            config: BidPipelineConfig 实例
        """
        self.format_spec = format_spec
        self.config = config
        self.exporter = DocxExporter()

    # ── 主入口 ──────────────────────────────────────────────

    def build_templates(
        self,
        strategies: List[Any],
        output_dir: Path,
    ) -> List[TemplateDocument]:
        """
        为每个策略（中标+参考文件）构建一个 DOCX 模板。

        Args:
            strategies: DegradeStrategy 列表
            output_dir: 模板输出目录 (.cache/07_template/)

        Returns:
            TemplateDocument 列表
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        templates = []

        for s in strategies:
            idx = s.bid_index
            is_winning = getattr(s, 'is_winning', False)
            strategy_name = getattr(s, 'strategy_name', f'方案{idx}')

            bid_id = "bid_00_winning" if is_winning else f"bid_{idx:02d}"

            print(f"    构建模板: {strategy_name} ({bid_id})")

            template_docx = output_dir / f"{bid_id}_template.docx"
            sections_json = output_dir / f"{bid_id}_sections.json"

            # 构建模板
            doc, sections = self._build_single_template(strategy_name, is_winning)

            # 保存
            doc.save(str(template_docx))
            sections_json.write_text(
                json.dumps(sections, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            td = TemplateDocument(
                strategy_id=bid_id,
                strategy_name=strategy_name,
                template_path=template_docx,
                sections_path=sections_json,
                sections=sections,
            )
            templates.append(td)

        print(f"    共构建 {len(templates)} 个模板")
        return templates

    def _build_single_template(
        self,
        strategy_name: str,
        is_winning: bool,
    ) -> Tuple[Document, List[Dict[str, Any]]]:
        """
        构建单个投标文件的完整 DOCX 模板。

        结构顺序：
        1. 封面
        2. 投标文件总目录
        3. 评分因素及评标标准页码检索
        4. 附件1-12（按编号顺序）
        5. 技术方案章节（含占位符）

        Returns:
            (doc, sections_metadata)
        """
        styles = self.format_spec.document_styles or DocumentStyles()
        doc = DocxExporter.create_template_from_spec(styles)

        sections_meta: List[Dict[str, Any]] = []
        page_counter = [1]  # 用列表以便在嵌套函数中修改

        def add_section(section_id: str, title: str, section_type: str,
                        content: str = "", filled: bool = False,
                        placeholder: str = "") -> Dict[str, Any]:
            meta = {
                "section_id": section_id,
                "title": title,
                "section_type": section_type,
                "page_number": page_counter[0],
                "content": content[:200] if content else "",
                "is_filled": filled,
                "placeholder_marker": placeholder,
            }
            sections_meta.append(meta)
            return meta

        # ── 1. 封面 ──
        self._create_cover_page(doc, styles)
        add_section("cover", "投标文件封面", "cover", filled=True)
        page_counter[0] += 1

        # ── 2. 目录 ──
        self._create_toc(doc, styles)
        add_section("toc", "投标文件总目录", "toc", filled=True)
        page_counter[0] += 1

        # ── 3. 评分索引 ──
        add_section("score_index", "评分因素及评标标准页码检索", "toc", filled=True)
        page_counter[0] += 1

        # ── 4. 附件1-12 ──
        for att in self.format_spec.attachments:
            att_id = att.get("attachment_id", "")
            att_name = att.get("name", "")
            att_type = att.get("section_type", "business")
            body_text = att.get("body_text", "")

            # 分页（新附件从新页开始）
            if att_id.startswith("附件"):
                doc.add_page_break()
                page_counter[0] += 1

            if att_type == "business" or att_id in self.BUSINESS_ATTACHMENT_IDS:
                # 商务附件：逐字填充
                self._fill_business_attachment(doc, att, styles)
                add_section(att_id, att_name, "business", body_text, filled=True)
            elif att_type == "technical" or att_id in self.TECHNICAL_ATTACHMENT_IDS:
                # 技术附件：插入占位符
                if att_id == "附件6":
                    placeholder = "《TABLE:附件6:技术一对一应答表》"
                    title = "技术一对一应答表"
                else:
                    placeholder = "《TECH:附件11:技术方案证明材料》"
                    title = "证明材料及方案"

                self._insert_technical_placeholder_section(doc, att_id, title, placeholder, styles)
                add_section(att_id, att_name, "technical", placeholder=placeholder)
            else:
                # TOC/cover 类型
                add_section(att_id, att_name, att_type, filled=True)

        # ── 5. 技术方案章节占位符 ──
        doc.add_page_break()
        page_counter[0] += 1

        # 项目服务方案章节
        self._add_heading(doc, "13. 项目服务方案", 1, styles)
        self._add_heading(doc, "13.1 项目背景、需求分析方案评价", 2, styles)
        placeholder = "《TECH:13.1:项目服务方案》"
        self.exporter.insert_placeholder(doc, "TECH", "13.1", "项目服务方案")
        add_section("tech_13.1", "项目服务方案", "technical", placeholder=placeholder)

        self._add_heading(doc, "13.2 系统性能设计方案评价", 2, styles)
        self._add_heading(doc, "13.2.1 平台功能要求", 3, styles)
        placeholder = "《TECH:13.2.1:平台功能要求》"
        self.exporter.insert_placeholder(doc, "TECH", "13.2.1", "平台功能要求")
        add_section("tech_13.2.1", "平台功能要求", "technical", placeholder=placeholder)

        self._add_heading(doc, "13.2.2 项目重点难点与应对", 3, styles)
        placeholder = "《TECH:13.2.2:项目重点难点》"
        self.exporter.insert_placeholder(doc, "TECH", "13.2.2", "项目重点难点")
        add_section("tech_13.2.2", "项目重点难点与应对", "technical", placeholder=placeholder)

        self._add_heading(doc, "13.3 人员配置方案", 2, styles)
        placeholder = "《TECH:13.3:人员配置方案》"
        self.exporter.insert_placeholder(doc, "TECH", "13.3", "人员配置方案")
        add_section("tech_13.3", "人员配置方案", "technical", placeholder=placeholder)

        self._add_heading(doc, "13.4 项目进度安排", 2, styles)
        placeholder = "《TECH:13.4:项目进度安排》"
        self.exporter.insert_placeholder(doc, "TECH", "13.4", "项目进度安排")
        add_section("tech_13.4", "项目进度安排", "technical", placeholder=placeholder)

        self._add_heading(doc, "13.5 服务质量保证与验收", 2, styles)
        placeholder = "《TECH:13.5:服务质量保证》"
        self.exporter.insert_placeholder(doc, "TECH", "13.5", "服务质量保证")
        add_section("tech_13.5", "服务质量保证与验收", "technical", placeholder=placeholder)

        return doc, sections_meta

    # ── 封面 ────────────────────────────────────────────────

    def _create_cover_page(self, doc: Document, styles: DocumentStyles) -> None:
        """创建投标文件封面。"""
        # 空行让标题居中偏上
        for _ in range(6):
            doc.add_paragraph()

        # 标题
        title_para = doc.add_paragraph()
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = title_para.add_run("投 标 文 件")
        run.font.size = Pt(22)
        run.bold = True
        if styles.heading_styles.get(1) and styles.heading_styles[1][0]:
            DocxExporter._apply_text_style_to_run(run, styles.heading_styles[1][0])
            run.font.size = Pt(22)

        # 副标题
        sub_para = doc.add_paragraph()
        sub_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sub_run = sub_para.add_run("（加盖电子签章）")
        sub_run.font.size = Pt(12)

        doc.add_paragraph()

        # 信息行
        info_fields = [
            "项目编号：________________",
            "项目名称：________________",
            "所投包号：________________",
            "投标单位名称：________________",
            "投标代表人姓名：________________",
            "投标日期：    年    月    日",
        ]
        for field in info_fields:
            info_para = doc.add_paragraph()
            info_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = info_para.add_run(field)
            run.font.size = Pt(12)

    # ── 目录 ────────────────────────────────────────────────

    def _create_toc(self, doc: Document, styles: DocumentStyles) -> None:
        """插入 Word TOC 域代码（由 Word 打开时自动更新）。"""
        # TOC 标题
        toc_title = doc.add_paragraph()
        toc_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = toc_title.add_run("目  录")
        run.font.size = Pt(16)
        run.bold = True

        doc.add_paragraph()  # 空行

        # TOC 域代码
        para = doc.add_paragraph()

        # 开始域
        run_begin = para.add_run()
        fld_begin = OxmlElement("w:fldChar")
        fld_begin.set(qn("w:fldCharType"), "begin")
        run_begin._element.append(fld_begin)

        # 域指令
        run_instr = para.add_run()
        instr = OxmlElement("w:instrText")
        instr.set(qn("xml:space"), "preserve")
        instr.text = ' TOC \\o "1-3" \\h \\z \\u '
        run_instr._element.append(instr)

        # 分隔
        run_sep = para.add_run()
        fld_sep = OxmlElement("w:fldChar")
        fld_sep.set(qn("w:fldCharType"), "separate")
        run_sep._element.append(fld_sep)

        # 提示文本
        run_hint = para.add_run('（请在 Word 中右键点击此处，选择“更新域”以生成目录）')
        run_hint.font.size = Pt(10)
        run_hint.font.color.rgb = RGBColor(0x80, 0x80, 0x80)

        # 结束域
        run_end = para.add_run()
        fld_end = OxmlElement("w:fldChar")
        fld_end.set(qn("w:fldCharType"), "end")
        run_end._element.append(fld_end)

    # ── 商务附件填充 ────────────────────────────────────────

    def _fill_business_attachment(
        self,
        doc: Document,
        attachment: Dict[str, Any],
        styles: DocumentStyles,
    ) -> None:
        """
        逐字填充单个商务附件。

        从 FormatSpec 中的 attachment body_text 获取原始文本，
        进行最小化处理（保留结构，替换占位字段），写入 DOCX。

        商务附件绝不经过 AI 修改。
        """
        att_id = attachment.get("attachment_id", "")
        att_name = attachment.get("name", "")
        body_text = attachment.get("body_text", "")

        # 附件标题
        self._add_heading(doc, f"{att_id}  {att_name}", 1, styles)

        if not body_text:
            self._add_body(doc, f"（{att_name} — 按招标文件要求填写）", styles)
            # 对于没有 body_text 但有 fields 的附件，生成字段表格
            fields = attachment.get("fields", {})
            if fields and att_id in ("附件3", "附件4", "附件5", "附件7", "附件10"):
                self._add_field_table(doc, att_id, fields, styles)
            return

        # 逐段处理文本
        paragraphs = body_text.split("\n")
        for para_text in paragraphs:
            para_text = para_text.strip()
            if not para_text:
                continue

            # 替换已知的占位字段为下划线
            filled_text = self._substitute_fields(para_text, attachment.get("fields", {}))

            self._add_body(doc, filled_text, styles)

        # 对于表格类附件，补充表格结构
        if att_id in ("附件3", "附件4", "附件5", "附件7", "附件10"):
            self._add_field_table(doc, att_id, attachment.get("fields", {}), styles)

    def _substitute_fields(self, text: str, fields: Dict[str, str]) -> str:
        """
        替换文本中的可配置字段。

        - 公司名称/日期/项目名等从 config.company_info 读取
        - 未配置的保留为下划线占位
        """
        result = text

        # 从配置获取公司信息
        company_info = {}
        if self.config:
            try:
                company_info = self.config.get_company_info()
            except AttributeError:
                pass

        # 已知字段替换
        substitutions = {
            "投标单位名称：": f"投标单位名称：{company_info.get('name', '________________')}",
            "投标代表人姓名：": f"投标代表人姓名：{company_info.get('contact_name', '________________')}",
            "投标单位名称": company_info.get('name', '________________'),
        }

        for old, new in substitutions.items():
            if old in result:
                result = result.replace(old, new)

        return result

    def _add_field_table(
        self,
        doc: Document,
        att_id: str,
        fields: Dict[str, str],
        styles: DocumentStyles,
    ) -> None:
        """为表格类附件添加基础表格结构。"""
        table_configs = {
            "附件3": {
                "title": "开标一览表",
                "headers": ["序号", "名称", "投标总价（元）", "备注"],
                "rows": 3,
            },
            "附件4": {
                "title": "开标分项一览表",
                "headers": ["序号", "分项名称", "分项价格（元）", "备注"],
                "rows": 5,
            },
            "附件5": {
                "title": "商务要求点对点应答表",
                "headers": ["序号", "招标要求", "投标应答", "偏离说明"],
                "rows": 5,
            },
            "附件7": {
                "title": "主要相关项目业绩一览表",
                "headers": ["序号", "项目名称", "合同金额", "签订时间", "业主单位", "备注"],
                "rows": 5,
            },
            "附件10": {
                "title": "政府采购政策情况表",
                "headers": ["序号", "产品名称", "品牌型号", "金额", "制造商企业类型"],
                "rows": 5,
            },
        }

        if att_id not in table_configs:
            return

        config = table_configs[att_id]
        headers = config["headers"]
        num_rows = config["rows"]

        table = doc.add_table(rows=num_rows + 1, cols=len(headers))
        table.autofit = True

        # 表头
        for j, header in enumerate(headers):
            cell = table.rows[0].cells[j]
            cell.text = ""
            run = cell.paragraphs[0].add_run(header)
            run.bold = True
            run.font.size = Pt(10)
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

        # 三线表边框
        if styles.table_style:
            DocxExporter._apply_three_line_borders_styled(table, styles.table_style)

        doc.add_paragraph()

    # ── 技术占位符 ──────────────────────────────────────────

    def _insert_technical_placeholder_section(
        self,
        doc: Document,
        att_id: str,
        title: str,
        placeholder: str,
        styles: DocumentStyles,
    ) -> None:
        """为技术附件插入占位符章节。"""
        self._add_heading(doc, f"{att_id}  {title}", 1, styles)
        self.exporter.insert_placeholder(
            doc,
            "TECH" if "TECH" in placeholder else "TABLE",
            att_id,
            title,
        )

    # ── 辅助方法 ────────────────────────────────────────────

    def _add_heading(self, doc: Document, text: str, level: int, styles: DocumentStyles) -> None:
        """添加带样式的标题。"""
        para = doc.add_paragraph()
        run = para.add_run(text)

        if level in styles.heading_styles:
            ts, ps = styles.heading_styles[level]
            if ts:
                DocxExporter._apply_text_style_to_run(run, ts)
            if ps:
                DocxExporter._apply_para_style_to_paragraph(para, ps)
        else:
            # 回退到默认
            run.font.size = Pt({1: 16, 2: 14, 3: 12}.get(level, 11))
            run.bold = True
            if level == 1:
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def _add_body(self, doc: Document, text: str, styles: DocumentStyles) -> None:
        """添加带样式的正文段落。"""
        para = doc.add_paragraph()
        run = para.add_run(text)

        if styles.body_style:
            DocxExporter._apply_text_style_to_run(run, styles.body_style)
        if styles.body_para_style:
            DocxExporter._apply_para_style_to_paragraph(para, styles.body_para_style)

        if not styles.body_para_style or styles.body_para_style.first_line_indent_cm is None:
            para.paragraph_format.first_line_indent = Cm(0.74)
        if not styles.body_para_style or styles.body_para_style.line_spacing is None:
            para.paragraph_format.line_spacing = 1.5
        if not styles.body_style or not styles.body_style.alignment:
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

def build_template(
    format_spec: FormatSpec,
    strategy: Any,
    output_dir: Path,
) -> TemplateDocument:
    """快速为单个策略构建模板。"""
    filler = TemplateFiller(format_spec)
    templates = filler.build_templates([strategy], output_dir)
    return templates[0] if templates else None


def load_template_sections(json_path: Path) -> List[Dict[str, Any]]:
    """从 JSON 文件加载模板章节元数据。"""
    return json.loads(json_path.read_text(encoding="utf-8"))
