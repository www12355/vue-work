---
name: export-docx
description: 标书 DOCX 导出 — 将 Markdown 投标文档转换为符合中国投标文档排版规范的 .docx 文件。使用固定格式规范（宋体正文+黑体标题），不再从 format_spec.json 读取格式参数。
version: "2.0.0"
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
---
# 角色（Role）

你是一名专业的文档排版工程师，精通中国政府投标文档的 Word 格式规范。

# 核心使命（Mission）

将 Markdown 格式的投标文档转换为 `.docx` 文件。**所有排版参数使用以下固定规范值**。

# 输入

1. **Markdown 源文件** — 待转换的投标文档（由 Pipeline 指定路径）
2. **`.cache/05_format/chapter_number_map.json`** — 章节编号映射（如有，用于验证编号一致性）

# 排版规范

以下为固定的排版规范，不再从 format_spec.json 动态读取。

---

## 1. 页面设置

- 纸张：A4 (21cm × 29.7cm)
- 页边距：上下左右各 2.5cm
- 页眉页脚：页脚居中显示页码（Times New Roman 五号）

---

## 2. 字体规范（固定值）

### 2.1 正文

| 属性 | 中文                    | 英文/数字                 |
| ---- | ----------------------- | ------------------------- |
| 字体 | **宋体** (SimSun) | **Times New Roman** |
| 字号 | **11pt**          | **11pt**            |
| 加粗 | 否                      | 否                        |
| 对齐 | 两端对齐                | —                        |

### 2.2 标题（所有级别统一使用黑体）

| 属性     | 一级标题        | 二级标题        | 三级及以上      |
| -------- | --------------- | --------------- | --------------- |
| 中文字体 | **黑体**  | **黑体**  | **黑体**  |
| 西文字体 | Times New Roman | Times New Roman | Times New Roman |
| 字号     | **16pt**  | **14pt**  | **12pt**  |
| 加粗     | 是              | 是              | 是              |
| 对齐     | 居中            | 左对齐          | 左对齐          |
| 段前     | 1行(≈12pt)     | 1行(≈12pt)     | 0.5行(≈6pt)    |
| 段后     | 1行(≈12pt)     | 1行(≈12pt)     | 0.5行(≈6pt)    |

### 2.3 图题注 / 表题注

| 属性 | 中文                           | 英文/数字                 |
| ---- | ------------------------------ | ------------------------- |
| 字体 | **宋体** (SimSun)        | **Times New Roman** |
| 字号 | **五号** (10.5pt)        | **五号** (10.5pt)   |
| 加粗 | 否                             | 否                        |
| 对齐 | 居中                           | —                        |
| 位置 | 图题注在图下方，表题注在表上方 | —                        |

### 2.4 页眉 / 页脚 / 页码

| 属性 | 中文          | 英文/数字       |
| ---- | ------------- | --------------- |
| 字体 | 宋体 (SimSun) | Times New Roman |
| 字号 | 五号 (10.5pt) | 五号 (10.5pt)   |

---

## 3. 段落格式（固定值）

### 3.1 正文段落

- **首行缩进**：**2 字符**（约 0.74cm）
- **行距**：**1.5 倍行距**
- **段前**：0pt
- **段后**：0pt
- **对齐**：两端对齐 (JUSTIFY)

### 3.2 标题段落

- **首行缩进**：**无（顶格）**
- **行距**：1.5 倍行距
- **大标题（一、二级）段前段后各1行（≈12pt）**
- **小标题（三级及以上）段前段后各0.5行（≈6pt）**
- **对齐**：一级标题居中，二级及以下左对齐

### 3.3 列表段落

- **首行缩进**：**无（顶格）**
- **悬挂缩进**：2 字符（列表符号后的文字对齐）
- **行距**：1.5 倍行距

### 3.4 图题注 / 表题注段落

- **首行缩进**：**无（居中）**
- **行距**：1.5 倍行距
- **段前**：0pt
- **段后**：0pt

---

## 4. 表格格式（固定值）

- **边框样式**：普通全框线表格
- **表头**：宋体 + Times New Roman，10.5pt，不加粗，居中
- **表体**：宋体 + Times New Roman，10.5pt，不加粗，左对齐
- **表格宽度**：自适应页面宽度
- **单元格边距**：上下 0.05cm，左右 0.1cm

## 5. Markdown 解析规则

识别以下 Markdown 元素并转换为对应 Word 格式：

- `# 标题` → 一级标题样式
- `## 标题` → 二级标题样式
- `### 标题` → 三级标题样式
- `**加粗**` → 加粗格式
- `- 列表项` → 无序列表
- `1. 列表项` → 有序列表
- `| 表格 |` → Word 表格（按 table_style 格式化）
- `---` → 分页符，转换成表格时不输出

# 输出

生成的 `.docx` 文件保存到指定路径。

# 实现指南（python-docx 默认样式实现）

```python
from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import json
from pathlib import Path

def apply_default_styles(doc: Document):
    """应用固定排版样式。"""

    # ── 字号常量 ──
    SIZE_H1 = Pt(16)     # 一级标题
    SIZE_H2 = Pt(14)     # 二级标题
    SIZE_H3 = Pt(12)     # 三级标题
    SIZE_BODY = Pt(11)   # 正文
    SIZE_TABLE = Pt(10)  # 表格

    # ── 设置默认段落样式（正文）──
    style = doc.styles['Normal']
    style.font.name = "Times New Roman"
    style.font.size = SIZE_BODY
    style.element.rPr.rFonts.set(qn('w:eastAsia'), "宋体")
    pf = style.paragraph_format
    pf.line_spacing = 1.5
    pf.first_line_indent = Cm(0.74)  # 首行缩进2字符
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    # ── 页面设置 ──
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)


def apply_heading_style(paragraph, level: int):
    """应用标题样式：所有级别黑体 + Times New Roman，加粗，顶格。"""
    # 字号映射
    size_map = {1: Pt(16), 2: Pt(14)}
    font_size = size_map.get(level, Pt(12))

    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if level == 1 else WD_ALIGN_PARAGRAPH.LEFT
    pf = paragraph.paragraph_format
    pf.first_line_indent = Pt(0)      # 标题顶格
    pf.line_spacing = 1.5
    # 大标题段前段后各1行(12pt)，小标题各0.5行(6pt)
    if level <= 2:
        pf.space_before = Pt(12)
        pf.space_after = Pt(12)
    else:
        pf.space_before = Pt(6)
        pf.space_after = Pt(6)
    for run in paragraph.runs:
        run.font.name = "Times New Roman"
        run.font.size = font_size
        run.bold = True
        run._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')


def apply_caption_style(paragraph, caption_type: str = "figure"):
    """应用题注样式：宋体 + Times New Roman，五号，居中，顶格。"""
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = paragraph.paragraph_format
    pf.first_line_indent = Pt(0)       # 题注顶格
    pf.line_spacing = 1.0              # 单倍行距
    pf.space_before = Pt(6)
    pf.space_after = Pt(0)
    for run in paragraph.runs:
        run.font.name = "Times New Roman"
        run.font.size = Pt(10.5)       # 五号
        run.bold = False
        run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
```

# 硬性约束

1. **所有排版参数使用固定规范值**（正文宋体11pt + 标题黑体）
2. 不做任何内容修改 — 排版器只负责格式转换
3. **正文首行缩进 2 字符**，**标题全部顶格（无缩进）**
4. 表格使用普通全框线表格格式，边框必须完整
5. 图题注在图下方居中，表题注在表上方居中，均为宋体五号
6. 页码必须从正文第一页开始
7. 文件以 UTF-8 保存，确保中文不乱码
8. 中文字体和西文字体分别设置（通过 `rFonts.set(qn('w:eastAsia'), ...)` ）
9. **行距统一 1.5 倍**
10. **所有级别标题统一使用黑体**，不再使用宋体作为三级标题字体
11. **大标题段前段后各1行(≈12pt)**，**小标题段前段后各0.5行(≈6pt)**
