"""文档读取模块。

使用 python-docx / PyPDF2 / python-pptx 读取各类参考文档，
提取纯文本内容供 LLM 上下文使用。
"""

import os
from typing import List, Tuple
from docx import Document


def read_docx_text(file_path: str, max_chars: int = 15000) -> str:
    """读取 DOCX 文件并提取纯文本内容。

    对超大文件（如 69MB source/file.docx），仅提取前 max_chars 字符。

    Args:
        file_path: DOCX 文件的绝对路径
        max_chars: 最大返回字符数（对大文件进行裁剪）

    Returns:
        提取的纯文本字符串
    """
    if not os.path.exists(file_path):
        return ""

    try:
        doc = Document(file_path)
        paragraphs = []
        total_chars = 0

        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                paragraphs.append(text)
                total_chars += len(text)
                if total_chars >= max_chars:
                    paragraphs.append(f"\n...(内容已截断，文件共 {os.path.getsize(file_path)} 字节)...")
                    break

        # 也提取表格内容
        if total_chars < max_chars:
            for table in doc.tables:
                for row in table.rows:
                    row_texts = []
                    for cell in row.cells:
                        ct = cell.text.strip()
                        if ct:
                            row_texts.append(ct)
                    if row_texts:
                        line = " | ".join(row_texts)
                        paragraphs.append(line)
                        total_chars += len(line)
                        if total_chars >= max_chars:
                            break
                    if total_chars >= max_chars:
                        break
                if total_chars >= max_chars:
                    break

        return "\n".join(paragraphs)

    except Exception as e:
        return f"[读取文件失败: {e}]"


def read_pdf_text(file_path: str, max_chars: int = 15000) -> str:
    """读取 PDF 文件并提取纯文本内容。

    Args:
        file_path: PDF 文件的绝对路径
        max_chars: 最大返回字符数

    Returns:
        提取的纯文本字符串
    """
    if not os.path.exists(file_path):
        return ""

    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(file_path)
        paragraphs = []
        total_chars = 0
        total_pages = len(reader.pages)

        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                cleaned = text.strip()
                if cleaned:
                    if total_chars + len(cleaned) > max_chars:
                        remaining = max_chars - total_chars
                        paragraphs.append(cleaned[:remaining])
                        paragraphs.append(f"\n...(内容已截断，共 {total_pages} 页，文件 {os.path.getsize(file_path)} 字节)...")
                        break
                    paragraphs.append(cleaned)
                    total_chars += len(cleaned)

        return "\n".join(paragraphs)

    except ImportError:
        return "[PDF解析需要安装 PyPDF2，请运行: pip install PyPDF2]"
    except Exception as e:
        return f"[读取PDF文件失败: {e}]"


def read_pptx_text(file_path: str, max_chars: int = 15000) -> str:
    """读取 PPTX 文件并提取纯文本内容。

    Args:
        file_path: PPTX 文件的绝对路径
        max_chars: 最大返回字符数

    Returns:
        提取的纯文本字符串
    """
    if not os.path.exists(file_path):
        return ""

    try:
        from pptx import Presentation

        prs = Presentation(file_path)
        paragraphs = []
        total_chars = 0
        slide_count = len(prs.slides)

        for slide_num, slide in enumerate(prs.slides, 1):
            slide_texts = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        t = para.text.strip()
                        if t:
                            slide_texts.append(t)
                if shape.has_table:
                    table = shape.table
                    for row in table.rows:
                        row_texts = []
                        for cell in row.cells:
                            ct = cell.text.strip()
                            if ct:
                                row_texts.append(ct)
                        if row_texts:
                            slide_texts.append(" | ".join(row_texts))

            if slide_texts:
                slide_content = f"--- 幻灯片 {slide_num} ---\n" + "\n".join(slide_texts)
                if total_chars + len(slide_content) > max_chars:
                    remaining = max_chars - total_chars
                    paragraphs.append(slide_content[:remaining])
                    paragraphs.append(f"\n...(内容已截断，共 {slide_count} 页，文件 {os.path.getsize(file_path)} 字节)...")
                    break
                paragraphs.append(slide_content)
                total_chars += len(slide_content)

        return "\n\n".join(paragraphs)

    except ImportError:
        return "[PPTX解析需要安装 python-pptx，请运行: pip install python-pptx]"
    except Exception as e:
        return f"[读取PPTX文件失败: {e}]"


def read_file_auto(file_path: str, max_chars: int = 15000) -> str:
    """根据文件扩展名自动选择合适的读取器。

    支持: .docx, .pdf, .pptx, .ppt, .txt, .md

    Args:
        file_path: 文件的绝对路径
        max_chars: 最大返回字符数

    Returns:
        提取的纯文本字符串
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext in ('.txt', '.md'):
        try:
            text = open(file_path, encoding='utf-8').read()
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n...(内容已截断)..."
            return text
        except Exception as e:
            return f"[读取文本文件失败: {e}]"
    elif ext in ('.docx', '.doc'):
        return read_docx_text(file_path, max_chars=max_chars)
    elif ext == '.pdf':
        return read_pdf_text(file_path, max_chars=max_chars)
    elif ext in ('.pptx', '.ppt'):
        return read_pptx_text(file_path, max_chars=max_chars)
    else:
        return f"[不支持的文件格式: {ext}]"


def load_contract_examples(examples_dir: str, max_chars_per_file: int = 10000) -> List[Tuple[str, str]]:
    """加载合同案例文件夹中的所有参考文档（.docx 和 .pdf）。

    Args:
        examples_dir: 合同案例目录的绝对路径
        max_chars_per_file: 每个文件最大提取字符数

    Returns:
        (文件名, 文本内容) 元组列表
    """
    examples = []
    if not os.path.isdir(examples_dir):
        return examples

    for fname in sorted(os.listdir(examples_dir)):
        if fname.startswith("~$") or fname.startswith("."):
            continue
        ext = os.path.splitext(fname)[1].lower()
        if ext in ('.docx', '.doc', '.pdf'):
            file_path = os.path.join(examples_dir, fname)
            text = read_file_auto(file_path, max_chars=max_chars_per_file)
            if text and not text.startswith("["):
                examples.append((fname, text))

    return examples


def load_source_context(source_path: str, max_chars: int = 20000) -> str:
    """加载 source/ 参考文档作为上下文。

    该文件可能为大型招投标书（如 69MB DOCX），仅提取前 max_chars 字符。

    Args:
        source_path: source 文件的绝对路径
        max_chars: 最大返回字符数

    Returns:
        提取的文本内容
    """
    if not os.path.exists(source_path):
        return ""
    return read_file_auto(source_path, max_chars=max_chars)


def format_examples_for_prompt(examples: List[Tuple[str, str]]) -> str:
    """将合同案例格式化为可注入 Prompt 的文本块。

    Args:
        examples: (文件名, 文本内容) 列表

    Returns:
        格式化的参考文本
    """
    if not examples:
        return "（无参考案例）"

    parts = []
    for i, (fname, text) in enumerate(examples, 1):
        parts.append(f"【参考案例 {i}：{fname}】\n{text}\n")
    return "\n".join(parts)
