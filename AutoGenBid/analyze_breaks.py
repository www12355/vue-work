"""Analyze section breaks and page breaks in the bid document."""
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn
import os
import sys

# 确保项目根目录在 Python 路径中
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

DOC_PATH = ROOT / "标书文件.docx"

doc = Document(DOC_PATH)

print('=' * 70)
print('BASIC COUNTS')
print('=' * 70)
print(f'Total paragraphs: {len(doc.paragraphs)}')
print(f'Total sections:   {len(doc.sections)}')
print()

# ---------------------------------------------------------------------------
# 1. Find all page breaks
# ---------------------------------------------------------------------------
print('=' * 70)
print('PAGE BREAKS (w:br w:type="page")')
print('=' * 70)

page_break_count = 0
page_break_paragraphs = []

for i, para in enumerate(doc.paragraphs):
    for run in para.runs:
        for br in run._element.findall(qn('w:br')):
            if br.get(qn('w:type')) == 'page':
                page_break_count += 1
                page_break_paragraphs.append(i)
                print(f'PAGE BREAK #{page_break_count} at paragraph {i}:')
                if i > 0:
                    print(f'  <- Prev [{i-1}]: {doc.paragraphs[i-1].text[:100]}')
                print(f'  -> This [{i}]: {para.text[:100]}')
                for j in range(i + 1, min(i + 5, len(doc.paragraphs))):
                    txt = doc.paragraphs[j].text[:100]
                    if txt.strip():
                        print(f'  -> Next [{j}]: {txt}')
                print('---')

print(f'TOTAL PAGE BREAKS: {page_break_count}')
print()

# ---------------------------------------------------------------------------
# 2. Find section breaks at XML level
# ---------------------------------------------------------------------------
print('=' * 70)
print('SECTION PROPERTIES (w:sectPr in body)')
print('=' * 70)

body = doc.element.body
# Find all w:sectPr elements directly under body
sect_prs_in_body = body.findall(qn('w:sectPr'))
print(f'Number of w:sectPr elements in body: {len(sect_prs_in_body)}')

# Find w:sectPr inside paragraphs (section breaks at paragraph level)
sect_prs_in_paras = []
for i, para in enumerate(doc.paragraphs):
    pPr = para._element.find(qn('w:pPr'))
    if pPr is not None:
        sect_pr = pPr.find(qn('w:sectPr'))
        if sect_pr is not None:
            sect_prs_in_paras.append((i, para, sect_pr))

print(f'Number of w:sectPr inside paragraph pPr: {len(sect_prs_in_paras)}')
for idx, (i, para, sect_pr) in enumerate(sect_prs_in_paras):
    print(f'\nSection-break paragraph #{idx}: index {i}')
    print(f'  Params text: {para.text[:100]}')
    if i > 0:
        print(f'  Prev para [{i-1}]: {doc.paragraphs[i-1].text[:100]}')
    for j in range(i + 1, min(i + 5, len(doc.paragraphs))):
        txt = doc.paragraphs[j].text[:100]
        if txt.strip():
            print(f'  Next para [{j}]: {txt}')

# ---------------------------------------------------------------------------
# 3. High-level section information (python-docx sections)
# ---------------------------------------------------------------------------
print()
print('=' * 70)
print('SECTIONS (via doc.sections)')
print('=' * 70)

for idx, section in enumerate(doc.sections):
    print(f'\nSection {idx}:')
    print(f'  start_type: {section.start_type}')
    print(f'  page_width / page_height: {section.page_width} / {section.page_height}')
    print(f'  orientation: {section.orientation}')
    print(f'  left_margin: {section.left_margin}, right_margin: {section.right_margin}')
    print(f'  top_margin: {section.top_margin}, bottom_margin: {section.bottom_margin}')
    print(f'  header_distance: {section.header_distance}, footer_distance: {section.footer_distance}')
    print(f'  different_first_page_header_footer: {section.different_first_page_header_footer}')

    # Show section XML snippet
    sect_pr_xml = section._sectPr.xml
    # Print first 300 chars of XML
    if len(sect_pr_xml) > 300:
        print(f'  XML snippet: {sect_pr_xml[:300]}...')
    else:
        print(f'  XML full: {sect_pr_xml}')

# ---------------------------------------------------------------------------
# 4. Map paragraphs to sections (rough heuristic)
# ---------------------------------------------------------------------------
print()
print('=' * 70)
print('PARAGRAPH -> SECTION MAPPING (heuristic by w:sectPr position)')
print('=' * 70)

# w:sectPr is the last child of w:body; each new w:sectPr in a pPr
# marks the start of a new section for subsequent paragraphs.
# The first section covers paragraphs from 0 to the first in-para sectPr (exclusive).
# The last section is defined by the body-level w:sectPr.

break_indices = [-1] + [p[0] for p in sect_prs_in_paras]
for bi in range(len(break_indices)):
    start = break_indices[bi] + 1
    end = break_indices[bi + 1] if bi + 1 < len(break_indices) else len(doc.paragraphs)
    print(f'Segment {bi}: paragraphs {start} to {end - 1} ({end - start} paragraphs)')
    # Show first 3 paragraphs with content
    shown = 0
    for pi in range(start, end):
        if shown < 3 and doc.paragraphs[pi].text.strip():
            print(f'  [{pi}]: {doc.paragraphs[pi].text[:100]}')
            shown += 1

print()
print('DONE.')
