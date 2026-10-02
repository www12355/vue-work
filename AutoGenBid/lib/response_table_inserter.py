"""
应答表插入器 — 使用 python-docx 将应答表 DOCX 插入到技术文档的指定位置。

用途：
    Stage 10 使用此模块：
    1. 打开已填充的技术文档 DOCX
    2. 定位"第二章第一节（概述）"末尾位置
    3. 在该位置插入应答表 DOCX
    4. 保存合并后的文档

插入策略（三级回退）：
    1. 找到包含"概述"或"项目概述"的标题段落（Heading 2 级别）
    2. 在其下一个同级标题之前插入
    3. 如果找不到，回退到文档末尾插入

用法:
    from lib.response_table_inserter import ResponseTableInserter
    inserter = ResponseTableInserter()
    inserter.insert(filled_docx, response_docx, output_path)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, List
from copy import deepcopy

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from docx import Document
from docx.shared import Cm, Pt
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH


class ResponseTableInserter:
    """在技术文档的概述章节末尾插入应答表。"""

    # 概述相关的章节关键词（优先级从高到低）
    OVERVIEW_KEYWORDS = [
        "项目概述", "概述", "项目背景与需求分析",
        "项目背景", "需求分析",
    ]

    # 标题样式名称模式（用于识别标题段落）
    HEADING_STYLE_PATTERNS = [
        "Heading", "heading", "标题",
    ]

    def insert(
        self,
        filled_docx_path: Path,
        response_docx_path: Path,
        output_path: Path,
    ) -> Path:
        """
        将应答表 DOCX 插入到填充文档的概述章节末尾。

        Args:
            filled_docx_path: 已填充的技术文档路径
            response_docx_path: 应答表 DOCX 路径
            output_path: 输出文件路径

        Returns:
            输出文件路径
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        doc = Document(str(filled_docx_path))

        if not response_docx_path or not response_docx_path.exists():
            # 无应答表，直接复制
            doc.save(str(output_path))
            return output_path

        # ── 查找插入位置 ──
        insert_index = self._find_overview_section_end(doc)

        if insert_index is not None:
            print(f"    [应答表插入] 在概述章节末尾（段落索引 {insert_index}）插入应答表")
            self._insert_response_docx_at(doc, response_docx_path, insert_index)
        else:
            # 回退到文档末尾
            print(f"    [应答表插入] 未找到概述章节，在文档末尾插入应答表")
            self._append_response_docx(doc, response_docx_path)

        doc.save(str(output_path))
        print(f"    [应答表插入] 输出 → {output_path.name}")
        return output_path

    def _find_overview_section_end(self, doc: Document) -> Optional[int]:
        """
        查找概述章节末尾的段落索引。

        算法：
        1. 遍历段落，找到包含"概述"关键词且样式为标题的段落
        2. 从该段落向后找下一个同级或更高级标题
        3. 返回下一个标题之前的段落索引

        Returns:
            插入位置的段落索引（在该段落之后插入），或 None
        """
        paras = doc.paragraphs
        overview_idx = None
        overview_level = None

        # Step 1: 找到概述章节
        for i, para in enumerate(paras):
            text = para.text.strip()
            if not text:
                continue

            # 检查是否为标题段落
            if not self._is_heading(para):
                continue

            # 检查是否包含概述关键词
            for kw in self.OVERVIEW_KEYWORDS:
                if kw in text:
                    overview_idx = i
                    overview_level = self._get_heading_level(para)
                    print(f"    [应答表插入] 找到概述章节: '{text[:50]}' (段落 {i}, 级别 {overview_level})")
                    break

            if overview_idx is not None:
                break

        if overview_idx is None:
            return None

        # Step 2: 从概述章节向后找下一个同级或更高级标题
        for j in range(overview_idx + 1, len(paras)):
            para = paras[j]
            if not para.text.strip():
                continue
            if not self._is_heading(para):
                continue

            next_level = self._get_heading_level(para)
            # 同级（级别相同或更高）标题 → 在此之前插入
            if overview_level is not None and next_level is not None and next_level <= overview_level:
                # 返回 j-1（前一个段落的末尾）
                insert_idx = max(overview_idx, j - 1)
                print(f"    [应答表插入] 下一个同级标题: '{para.text[:50]}' (段落 {j})，"
                      f"插入位置: 段落 {insert_idx} 末尾")
                return insert_idx

        # Step 3: 未找到下一个同级标题 → 在概述章节段落之后插入
        # 找到概述章节后的最后一个非空段落
        last_content_idx = overview_idx
        for j in range(overview_idx + 1, len(paras)):
            if paras[j].text.strip():
                last_content_idx = j

        return last_content_idx

    def _is_heading(self, para) -> bool:
        """判断段落是否为标题（基于样式名称）。"""
        style_name = para.style.name if para.style else ""
        for pattern in self.HEADING_STYLE_PATTERNS:
            if pattern in style_name:
                return True
        # 也检查 OutlineLevel（1-9 为标题层级）
        try:
            ol = para.paragraph_format.outline_level
            if ol is not None and 0 <= ol <= 8:
                return True
        except Exception:
            pass
        return False

    def _get_heading_level(self, para) -> Optional[int]:
        """获取标题级别（1-9），越小越高级。"""
        style_name = para.style.name if para.style else ""
        # 从样式名称中提取数字（如 Heading 2 → 2）
        import re
        match = re.search(r'(\d+)', style_name)
        if match:
            return int(match.group(1))
        # 从 OutlineLevel 获取
        try:
            ol = para.paragraph_format.outline_level
            if ol is not None and 0 <= ol <= 8:
                return ol + 1  # OutlineLevel 0 = Heading 1
        except Exception:
            pass
        return None

    def _insert_response_docx_at(
        self,
        doc: Document,
        response_docx_path: Path,
        insert_index: int,
    ) -> None:
        """
        在指定段落索引之后插入应答表内容。

        使用 XML 级别的元素插入，在 insert_index 段落之后
        插入分页符和应答表的所有 body 子元素。
        """
        response_doc = Document(str(response_docx_path))
        body = doc.element.body
        paras = doc.paragraphs

        # 找到插入位置的 XML 元素索引
        if insert_index >= len(paras):
            # 文档末尾
            insert_xml_idx = len(body)
        else:
            # 在该段落的 XML 元素之后插入
            target_para_elem = paras[insert_index]._element
            # 找到该元素在 body 中的位置
            body_children = list(body)
            try:
                insert_xml_idx = body_children.index(target_para_elem) + 1
            except ValueError:
                insert_xml_idx = len(body)

        # ── 插入分页符 ──
        from docx.oxml import OxmlElement
        page_break_para = OxmlElement('w:p')
        page_break_run = OxmlElement('w:r')
        page_break_br = OxmlElement('w:br')
        page_break_br.set(qn('w:type'), 'page')
        page_break_run.append(page_break_br)
        page_break_para.append(page_break_run)

        body.insert(insert_xml_idx, page_break_para)
        insert_xml_idx += 1

        # ── 插入应答表内容（跳过 sectPr）──
        response_body = response_doc.element.body
        for child in list(response_body):
            # 跳过 section properties
            if child.tag == qn('w:sectPr'):
                continue
            # 深拷贝以保留格式
            cloned = deepcopy(child)
            body.insert(insert_xml_idx, cloned)
            insert_xml_idx += 1

    def _append_response_docx(
        self,
        doc: Document,
        response_docx_path: Path,
    ) -> None:
        """回退方案：将应答表追加到文档末尾。"""
        response_doc = Document(str(response_docx_path))
        body = doc.element.body

        # 添加分页符
        from docx.oxml import OxmlElement
        page_break_para = OxmlElement('w:p')
        page_break_run = OxmlElement('w:r')
        page_break_br = OxmlElement('w:br')
        page_break_br.set(qn('w:type'), 'page')
        page_break_run.append(page_break_br)
        page_break_para.append(page_break_run)
        body.append(page_break_para)

        # 追加应答表内容
        response_body = response_doc.element.body
        for child in list(response_body):
            if child.tag == qn('w:sectPr'):
                continue
            body.append(deepcopy(child))
