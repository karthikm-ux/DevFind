"""
Generate DevFind_Professional_Case_Study.pptx
Run: python docs/gen_pptx.py
"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt
import copy
from lxml import etree

# ── Palette ──
TEAL      = RGBColor(0x0F, 0x76, 0x6E)
GRAPHITE  = RGBColor(0x17, 0x21, 0x2B)
BG        = RGBColor(0xF5, 0xF7, 0xFA)
WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
SLATE     = RGBColor(0x64, 0x74, 0x8B)
SLATE_LT  = RGBColor(0xF1, 0xF5, 0xF9)
AMBER     = RGBColor(0xB4, 0x53, 0x09)
AMBER_LT  = RGBColor(0xFE, 0xF3, 0xC7)
RED       = RGBColor(0xB9, 0x1C, 0x1C)
GREEN     = RGBColor(0x15, 0x80, 0x3D)
BORDER    = RGBColor(0xE2, 0xE8, 0xF0)
DARK_TEXT = RGBColor(0x1E, 0x29, 0x3B)

SW = Inches(13.333)
SH = Inches(7.5)
FONT = "Calibri"

prs = Presentation()
prs.slide_width  = SW
prs.slide_height = SH


def blank_slide(prs):
    blank = prs.slide_layouts[6]
    return prs.slides.add_slide(blank)


def set_bg(slide, color=BG):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_rect(slide, left, top, width, height, fill_color=None, line_color=None, line_width_pt=0.5):
    shape = slide.shapes.add_shape(1, left, top, width, height)  # MSO_SHAPE_TYPE.RECTANGLE = 1
    shape.fill.solid()
    if fill_color:
        shape.fill.fore_color.rgb = fill_color
    else:
        shape.fill.background()
    if line_color:
        shape.line.color.rgb = line_color
        shape.line.width = Pt(line_width_pt)
    else:
        shape.line.fill.background()
    return shape


def add_text_box(slide, text, left, top, width, height,
                 font_size=12, bold=False, color=DARK_TEXT,
                 align=PP_ALIGN.LEFT, italic=False, font=FONT, wrap=True):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.name = font
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    return txBox


def add_title_bar(slide, title_text, bar_height=Inches(0.65)):
    bar = add_rect(slide, 0, 0, SW, bar_height, fill_color=TEAL)
    tb  = slide.shapes.add_textbox(Inches(0.4), Inches(0.08), SW - Inches(0.8), bar_height - Inches(0.1))
    tf  = tb.text_frame
    tf.word_wrap = False
    p   = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    run = p.add_run()
    run.text = title_text
    run.font.name = FONT
    run.font.size = Pt(20)
    run.font.bold = True
    run.font.color.rgb = WHITE
    return bar


def add_bullet_list(slide, items, left, top, width, height,
                    font_size=12, color=DARK_TEXT, indent=False):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf    = txBox.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = item
        p.alignment = PP_ALIGN.LEFT
        pf = p._pPr if p._pPr is not None else p._p.get_or_add_pPr()
        for run in p.runs:
            run.font.name = FONT
            run.font.size = Pt(font_size)
            run.font.color.rgb = color
        if not p.runs:
            run = p.add_run()
            run.text = item
            p.text = ""
            run.font.name = FONT
            run.font.size = Pt(font_size)
            run.font.color.rgb = color


def styled_bullet(slide, items, left, top, width, height, font_size=12, color=DARK_TEXT, title=None):
    """Add a text box with a title and bullet list items."""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    start = 0
    if title:
        p = tf.paragraphs[0]
        r = p.add_run()
        r.text = title
        r.font.name = FONT
        r.font.size = Pt(font_size + 1)
        r.font.bold = True
        r.font.color.rgb = GRAPHITE
        start = 1
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if (i == 0 and not title) else tf.add_paragraph()
        r = p.add_run()
        r.text = item
        r.font.name = FONT
        r.font.size = Pt(font_size)
        r.font.color.rgb = color
        p.space_before = Pt(2)


def add_table(slide, headers, rows, left, top, width, col_widths=None):
    cols = len(headers)
    row_count = len(rows) + 1
    tbl = slide.shapes.add_table(row_count, cols, left, top, width, Inches(0.3 * row_count + 0.1)).table

    # Header row
    for j, h in enumerate(headers):
        cell = tbl.cell(0, j)
        cell.fill.solid()
        cell.fill.fore_color.rgb = TEAL
        p = cell.text_frame.paragraphs[0]
        r = p.add_run()
        r.text = h
        r.font.name = FONT
        r.font.size = Pt(10)
        r.font.bold = True
        r.font.color.rgb = WHITE

    # Data rows
    for i, row in enumerate(rows):
        fill_c = SLATE_LT if i % 2 == 0 else WHITE
        for j, cell_text in enumerate(row):
            cell = tbl.cell(i + 1, j)
            cell.fill.solid()
            cell.fill.fore_color.rgb = fill_c
            p = cell.text_frame.paragraphs[0]
            r = p.add_run()
            r.text = str(cell_text)
            r.font.name = FONT
            r.font.size = Pt(9)
            r.font.color.rgb = DARK_TEXT

    # Column widths
    if col_widths:
        for j, w in enumerate(col_widths):
            for i in range(row_count):
                tbl.cell(i, j).width = w

    return tbl


def add_code_box(slide, code_text, left, top, width, height):
    box = add_rect(slide, left, top, width, height, fill_color=RGBColor(0xF8, 0xFA, 0xFC), line_color=BORDER)
    tb = slide.shapes.add_textbox(left + Inches(0.1), top + Inches(0.05), width - Inches(0.2), height - Inches(0.1))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = code_text
    r.font.name = "Courier New"
    r.font.size = Pt(9)
    r.font.color.rgb = GRAPHITE


def note_box(slide, text, left, top, width, height, bg=AMBER_LT, border=AMBER, text_color=None):
    add_rect(slide, left, top, width, height, fill_color=bg, line_color=border, line_width_pt=1.2)
    tc = text_color or RGBColor(0x92, 0x40, 0x0E)
    tb = slide.shapes.add_textbox(left + Inches(0.1), top + Inches(0.05), width - Inches(0.2), height - Inches(0.1))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = text
    r.font.name = FONT
    r.font.size = Pt(10)
    r.font.color.rgb = tc


# ════════════════════════════════════════════════════════════
# SLIDE 1 — Title
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_rect(s, 0, 0, SW, Inches(2.0), fill_color=TEAL)
add_text_box(s, "DevFind", Inches(0.6), Inches(0.3), Inches(10), Inches(0.9),
             font_size=44, bold=True, color=WHITE)
add_text_box(s, "Semantic Bug & Issue Intelligence Platform",
             Inches(0.6), Inches(1.1), Inches(10), Inches(0.55),
             font_size=19, color=RGBColor(0xCC, 0xFB, 0xF1))
add_text_box(s, "A Weaviate Vector Database Case Study",
             Inches(0.6), Inches(2.2), Inches(9), Inches(0.4),
             font_size=14, color=SLATE)
add_text_box(s, "Database Management Systems  ·  Computer Science Project  ·  October 2024",
             Inches(0.6), Inches(2.7), Inches(10), Inches(0.4),
             font_size=12, color=SLATE)
add_rect(s, 0, SH - Inches(0.05), SW, Inches(0.05), fill_color=TEAL)


# ════════════════════════════════════════════════════════════
# SLIDE 2 — Problem Statement
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "Problem Statement")
bullets = [
    "  ·  Software teams repeatedly investigate bugs already reported elsewhere",
    "  ·  Different developers use different terminology for identical failures",
    "  ·  Manual triage of large backlogs is slow and error-prone",
    "  ·  Duplicate reports waste engineering time and obscure incident frequency",
]
styled_bullet(s, bullets, Inches(0.4), Inches(0.85), Inches(7.5), Inches(3.5), font_size=13)
add_rect(s, Inches(8.2), Inches(0.9), Inches(4.7), Inches(3.0),
         fill_color=WHITE, line_color=BORDER)
add_text_box(s, "Example", Inches(8.4), Inches(0.95), Inches(4.2), Inches(0.4),
             font_size=10, bold=True, color=SLATE)
add_text_box(s,
    "AUTH-101\n\"Session expires on page reload\"\n\nAUTH-104\n\"Application logs out after browser refresh\"\n\nSame root cause — filed separately",
    Inches(8.4), Inches(1.35), Inches(4.3), Inches(2.3),
    font_size=10.5, color=DARK_TEXT)
add_text_box(s,
    "DevFind addresses this by indexing bug semantics, not just keywords.",
    Inches(0.4), Inches(6.85), Inches(12), Inches(0.45),
    font_size=11, italic=True, color=SLATE)


# ════════════════════════════════════════════════════════════
# SLIDE 3 — Objectives & Scope
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "Objectives & Scope")
obj_items = [
    "1.  Store structured issue data in Weaviate with full CRUD",
    "2.  Enable semantic, keyword, and hybrid search over issue text",
    "3.  Surface duplicate candidates using vector distance",
    "4.  Support human review and decision recording",
    "5.  Integrate GitHub Issues as a live data source",
    "6.  Provide optional RAG-assisted debugging",
]
styled_bullet(s, obj_items, Inches(0.4), Inches(0.85), Inches(6.2), Inches(4.5),
              font_size=12.5, title="Objectives")

scope_items = [
    "In scope:",
    "  Weaviate Cloud  ·  Semantic duplicate detection",
    "  GitHub Issues import  ·  Streamlit UI",
    "  Evaluation framework  ·  151 passing tests",
    "",
    "Out of scope:",
    "  Automated duplicate merging",
    "  CI pipeline integration",
    "  Production deployment",
    "  User authentication",
]
styled_bullet(s, scope_items, Inches(7.0), Inches(0.85), Inches(5.9), Inches(4.5),
              font_size=12, title="Scope")


# ════════════════════════════════════════════════════════════
# SLIDE 4 — Existing Approach & Limitations
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "Starting Point: devfind_demo.py")
add_code_box(s,
    "import weaviate\nclient = weaviate.connect_to_local()\n\n# Hard-coded 10 sample issues\n# No search functionality\n# No user interface\n# No CRUD operations\n# No test coverage\n# Single file, 61 lines total",
    Inches(0.4), Inches(0.85), Inches(5.8), Inches(3.6))
limits = [
    "  ·  Hard-coded localhost — no cloud support",
    "  ·  10 static records — not a real dataset",
    "  ·  No search functionality",
    "  ·  No user-facing interface",
    "  ·  No CRUD beyond a single insert",
    "  ·  Zero test coverage",
    "  ·  Single-file — no modularity or reuse",
]
styled_bullet(s, limits, Inches(6.6), Inches(0.85), Inches(6.4), Inches(4.0),
              font_size=12.5, title="Limitations", color=DARK_TEXT)
add_text_box(s, "DevFind builds on this foundation without removing or modifying the original file.",
             Inches(0.4), Inches(6.85), Inches(12), Inches(0.4),
             font_size=11, italic=True, color=SLATE)


# ════════════════════════════════════════════════════════════
# SLIDE 5 — Proposed Solution
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "DevFind: Full-Stack Weaviate Application")
cards = [
    ("Weaviate Cloud", "Primary vector + keyword store\nDevFindIssue + DevFindKnowledge"),
    ("Semantic Search", "near_text, hybrid BM25+vector\nConfigurable distance threshold"),
    ("Duplicate Detection", "Candidate flagging + human review\nDecision recorded to Weaviate"),
    ("GitHub Import", "Idempotent sync via UUIDv5\nDry-run preview mode"),
    ("Streamlit UI", "5-page professional interface\nNo emojis, enterprise layout"),
    ("Evaluation", "Precision@k, Recall@k, MRR\n30-query synthetic dataset"),
]
cols_c = 3
for idx, (title, desc) in enumerate(cards):
    row = idx // cols_c
    col = idx % cols_c
    lft = Inches(0.4) + col * Inches(4.25)
    tp  = Inches(1.05) + row * Inches(2.3)
    add_rect(s, lft, tp, Inches(4.0), Inches(2.0), fill_color=WHITE, line_color=TEAL, line_width_pt=1.5)
    add_text_box(s, title, lft + Inches(0.15), tp + Inches(0.12), Inches(3.7), Inches(0.45),
                 font_size=13, bold=True, color=TEAL)
    add_text_box(s, desc, lft + Inches(0.15), tp + Inches(0.55), Inches(3.7), Inches(1.3),
                 font_size=11, color=DARK_TEXT)


# ════════════════════════════════════════════════════════════
# SLIDE 6 — System Architecture
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "System Architecture")

layers = [
    (TEAL, WHITE, "Presentation Layer",
     "Streamlit app.py  ·  5 pages: Dashboard, Issue Management, Duplicate Finder, GitHub Import, Knowledge Assistant"),
    (RGBColor(0xCC, 0xFB, 0xF1), GRAPHITE, "Business Logic Layer",
     "src/  package  ·  db/ (client, schema, issues, knowledge, search)  ·  github_integration  ·  rag  ·  evaluation  ·  utils"),
    (RGBColor(0x0D, 0x94, 0x88), WHITE, "Database Layer",
     "Weaviate Cloud  ·  DevFindIssue collection  ·  DevFindKnowledge collection  ·  text2vec_weaviate vectorizer"),
    (GRAPHITE, RGBColor(0xCB, 0xD5, 0xE1), "External APIs (optional)",
     "GitHub Issues REST API v3  ·  Ollama (local LLM)  ·  OpenAI API"),
]
layer_h = Inches(1.2)
for i, (bg, fg, lbl, desc) in enumerate(layers):
    top_i = Inches(0.85) + i * (layer_h + Inches(0.15))
    add_rect(s, Inches(0.5), top_i, Inches(12.3), layer_h, fill_color=bg, line_color=None)
    add_text_box(s, lbl, Inches(0.7), top_i + Inches(0.1), Inches(12), Inches(0.42),
                 font_size=12, bold=True, color=fg)
    add_text_box(s, desc, Inches(0.7), top_i + Inches(0.5), Inches(12), Inches(0.55),
                 font_size=10.5, color=fg)
    if i < len(layers) - 1:
        add_text_box(s, "▼", Inches(6.4), top_i + layer_h + Inches(0.02), Inches(0.5), Inches(0.14),
                     font_size=10, color=SLATE, align=PP_ALIGN.CENTER)


# ════════════════════════════════════════════════════════════
# SLIDE 7 — Data Flow
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "End-to-End Data Flow")

flow_boxes = [
    "New Issue\nDescription",
    "Weaviate\ntext2vec",
    "DevFindIssue\nCollection",
    "near_text /\nhybrid query",
    "Ranked\nCandidates",
    "Human\nReview",
]
bw = Inches(1.8)
bh = Inches(1.1)
gap = Inches(0.22)
total_w = len(flow_boxes) * bw + (len(flow_boxes) - 1) * gap
start_x = (SW - total_w) / 2
top_y   = Inches(1.7)

for i, label in enumerate(flow_boxes):
    lft = start_x + i * (bw + gap)
    add_rect(s, lft, top_y, bw, bh, fill_color=WHITE, line_color=TEAL, line_width_pt=1.2)
    add_text_box(s, label, lft + Inches(0.05), top_y + Inches(0.18), bw - Inches(0.1), Inches(0.7),
                 font_size=11, bold=False, color=GRAPHITE, align=PP_ALIGN.CENTER)
    if i < len(flow_boxes) - 1:
        arx = lft + bw + Inches(0.04)
        add_text_box(s, "→", arx, top_y + Inches(0.3), gap - Inches(0.05), Inches(0.45),
                     font_size=14, color=TEAL, align=PP_ALIGN.CENTER)

note_box(s,
    "Vector embeddings are computed by the Weaviate-hosted text2vec_weaviate model at write time and at query time. "
    "No local embedding model is required.",
    Inches(1.0), Inches(5.5), Inches(11.3), Inches(0.75),
    bg=RGBColor(0xF0, 0xFD, 0xFA), border=TEAL, text_color=RGBColor(0x0F, 0x76, 0x6E))


# ════════════════════════════════════════════════════════════
# SLIDE 8 — Schema
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "Weaviate Collection Schema")

add_text_box(s, "DevFindIssue (primary collection)", Inches(0.4), Inches(0.75), Inches(7.0), Inches(0.35),
             font_size=12, bold=True, color=TEAL)
add_table(s,
    ["Property", "Type", "Description"],
    [
        ["issue_key",     "TEXT",       "Unique key, e.g. AUTH-101"],
        ["title",         "TEXT",       "Short issue title (vectorised)"],
        ["description",   "TEXT",       "Full detail (vectorised)"],
        ["severity",      "TEXT",       "Critical / High / Medium / Low"],
        ["status",        "TEXT",       "Open / In Progress / Resolved / Closed"],
        ["component",     "TEXT",       "Affected subsystem"],
        ["duplicate_of",  "TEXT",       "Confirmed parent issue key"],
        ["review_status", "TEXT",       "pending / confirmed_dup / distinct"],
        ["tags",          "TEXT_ARRAY", "Free-form tags"],
    ],
    Inches(0.4), Inches(1.1), Inches(7.0),
    col_widths=[Inches(1.6), Inches(1.3), Inches(4.1)],
)

add_text_box(s, "DevFindKnowledge (optional — RAG)", Inches(7.7), Inches(0.75), Inches(5.2), Inches(0.35),
             font_size=12, bold=True, color=TEAL)
add_table(s,
    ["Property", "Type"],
    [
        ["doc_id",      "TEXT"],
        ["title",       "TEXT"],
        ["content",     "TEXT"],
        ["source_name", "TEXT"],
        ["chunk_index", "INT"],
        ["doc_type",    "TEXT"],
        ["created_at",  "TEXT"],
    ],
    Inches(7.7), Inches(1.1), Inches(5.2),
    col_widths=[Inches(1.7), Inches(1.3)],
)

add_text_box(s,
    "Vectorizer: text2vec_weaviate  ·  Distance: cosine  ·  UUID strategy: UUIDv5 (deterministic, idempotent upsert)",
    Inches(0.4), Inches(6.8), Inches(12.5), Inches(0.4),
    font_size=10, italic=True, color=SLATE)


# ════════════════════════════════════════════════════════════
# SLIDE 9 — CRUD
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "CRUD Operations")

crud_ops = [
    ("CREATE", "upsert_issue()", "UUIDv5 ensures idempotent insert.\nSecond write updates, not duplicates.\nValidation enforced before write."),
    ("READ",   "get_issue_by_key()\nlist_issues()", "Filter by status, severity,\ncomponent, project.\nFetch single by UUID."),
    ("UPDATE", "update_issue()", "Partial property update.\nUnchanged fields preserved.\nReturns True on success."),
    ("DELETE", "delete_issue()", "Permanent removal.\nUUID-based lookup.\nReturns True if found."),
]
cw = Inches(3.1)
for i, (op, fn, desc) in enumerate(crud_ops):
    lft = Inches(0.35) + i * (cw + Inches(0.1))
    add_rect(s, lft, Inches(0.85), cw, Inches(5.5), fill_color=WHITE, line_color=BORDER)
    add_text_box(s, op, lft + Inches(0.15), Inches(0.95), cw - Inches(0.2), Inches(0.55),
                 font_size=15, bold=True, color=TEAL)
    add_code_box(s, fn, lft + Inches(0.1), Inches(1.55), cw - Inches(0.15), Inches(0.55))
    add_text_box(s, desc, lft + Inches(0.15), Inches(2.2), cw - Inches(0.2), Inches(3.5),
                 font_size=11.5, color=DARK_TEXT)

add_text_box(s, "All CRUD operations use the DevFindIssue collection as the primary store.",
             Inches(0.4), Inches(6.8), Inches(12), Inches(0.4),
             font_size=10, italic=True, color=SLATE)


# ════════════════════════════════════════════════════════════
# SLIDE 10 — Search Modes
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "Search: Keyword vs Semantic vs Hybrid")

add_table(s,
    ["", "Keyword (BM25)", "Semantic (near_text)", "Hybrid (default)"],
    [
        ["Technique",    "Term frequency / BM25",  "Cosine vector distance",   "BM25 + vector fusion"],
        ["Finds",        "Exact matches only",      "Paraphrases & synonyms",   "Exact + semantic"],
        ["Misses",       "Different terminology",   "May overreach",            "Fewer misses overall"],
        ["Weaviate API", "query.bm25()",            "query.near_text()",        "query.hybrid()"],
        ["Best for",     "Known error codes",       "Natural language queries", "General production use"],
    ],
    Inches(0.4), Inches(0.85), Inches(12.5),
    col_widths=[Inches(1.5), Inches(3.2), Inches(3.8), Inches(4.0)],
)

add_text_box(s,
    "Hybrid search is the default mode in DevFind, fusing BM25 relevance with vector similarity via reciprocal rank fusion.",
    Inches(0.4), Inches(6.8), Inches(12), Inches(0.4),
    font_size=10.5, italic=True, color=SLATE)


# ════════════════════════════════════════════════════════════
# SLIDE 11 — Semantic Search Workflow
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "Embedding & Semantic Search Workflow")

steps = [
    ("1", "Issue description text is ingested into Weaviate via insert_issue() or upsert_issue()"),
    ("2", "text2vec_weaviate model converts text to a high-dimensional vector on write"),
    ("3", "At search time, query text is embedded using the same Weaviate-hosted model"),
    ("4", "Cosine distance computed between query vector and all stored vectors"),
    ("5", "Top-k results returned, ordered by ascending distance"),
    ("6", "Results below the threshold are flagged is_candidate=True for human review"),
]
for i, (num, text) in enumerate(steps):
    top_i = Inches(0.95) + i * Inches(0.88)
    add_rect(s, Inches(0.4), top_i, Inches(0.5), Inches(0.55), fill_color=TEAL)
    add_text_box(s, num, Inches(0.4), top_i + Inches(0.07), Inches(0.5), Inches(0.4),
                 font_size=13, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text_box(s, text, Inches(1.05), top_i + Inches(0.08), Inches(8.5), Inches(0.45),
                 font_size=12, color=DARK_TEXT)

note_box(s,
    'Example: Semantic search finds AUTH-104 ("logs out after browser refresh") '
    'when queried with AUTH-101 language ("session expires on page reload") — '
    'keyword search returns zero results for this pair.',
    Inches(0.4), Inches(6.3), Inches(12.5), Inches(0.85),
    bg=RGBColor(0xF0, 0xFD, 0xFA), border=TEAL, text_color=RGBColor(0x0F, 0x76, 0x6E))


# ════════════════════════════════════════════════════════════
# SLIDE 12 — Duplicate Finder Workflow
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "Duplicate Finder Workflow")

flow_steps = [
    ("Developer submits issue description", TEAL, WHITE),
    ("Hybrid search over DevFindIssue", RGBColor(0xCC, 0xFB, 0xF1), GRAPHITE),
    ("Rank results by distance score", RGBColor(0xCC, 0xFB, 0xF1), GRAPHITE),
    ("distance < threshold?  →  Flag as Candidate", RGBColor(0xFE, 0xF3, 0xC7), RGBColor(0x92, 0x40, 0x0E)),
    ("Display results with distance metrics in UI", WHITE, GRAPHITE),
    ("Developer reviews each candidate", WHITE, GRAPHITE),
    ("Confirm  →  record_review(confirmed_dup)       Reject  →  record_review(distinct)", RGBColor(0xDC, 0xFC, 0xE7), RGBColor(0x15, 0x80, 0x3D)),
]
step_h = Inches(0.72)
for i, (txt, bg, fg) in enumerate(flow_steps):
    top_i = Inches(0.85) + i * (step_h + Inches(0.05))
    add_rect(s, Inches(1.5), top_i, Inches(10.3), step_h, fill_color=bg, line_color=BORDER)
    add_text_box(s, txt, Inches(1.7), top_i + Inches(0.15), Inches(9.9), step_h - Inches(0.1),
                 font_size=11.5, color=fg)
    if i < len(flow_steps) - 1:
        add_text_box(s, "▼", Inches(6.5), top_i + step_h + Inches(0.01), Inches(0.5), Inches(0.08),
                     font_size=9, color=SLATE, align=PP_ALIGN.CENTER)

add_text_box(s,
    "Semantic similarity is a candidate signal, not proof of shared root cause. Human review is always required.",
    Inches(0.4), Inches(6.85), Inches(12), Inches(0.4),
    font_size=10, italic=True, color=SLATE)


# ════════════════════════════════════════════════════════════
# SLIDE 13 — Metadata Filtering
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "Metadata Filtering")
add_text_box(s,
    "Filters are applied as pre-search constraints, reducing the candidate pool before vector ranking.",
    Inches(0.4), Inches(0.75), Inches(12), Inches(0.4),
    font_size=12, color=DARK_TEXT)

add_table(s,
    ["Filter Field", "Accepted Values", "Use Case"],
    [
        ["status",    "Open · In Progress · Resolved · Closed",  "Focus on unresolved issues only"],
        ["severity",  "Critical · High · Medium · Low",           "Prioritise high-impact bugs"],
        ["component", "Any text (e.g. Authentication)",           "Scope search to a subsystem"],
        ["project",   "Any text (e.g. ProjectAlpha)",             "Isolate a project or team"],
    ],
    Inches(0.4), Inches(1.25), Inches(12.5),
    col_widths=[Inches(2.0), Inches(5.0), Inches(5.5)],
)

add_code_box(s,
    "# Weaviate filter example (src/db/search.py)\n"
    "from weaviate.classes.query import Filter\n\n"
    "collection.query.hybrid(\n"
    "    query=query_text,\n"
    "    filters=Filter.by_property(\"status\").equal(\"Open\"),\n"
    "    limit=10\n"
    ")",
    Inches(0.4), Inches(4.2), Inches(12.5), Inches(2.1))


# ════════════════════════════════════════════════════════════
# SLIDE 14 — GitHub Import
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "GitHub Issues Integration")

steps_gh = [
    "1.  Authenticate via GitHub Personal Access Token",
    "2.  Paginate through issues (100 per page, pull requests excluded)",
    "3.  Normalise: map labels → severity, state → status",
    "4.  Compute UUIDv5(source='github', issue_number) for stable identity",
    "5.  Upsert into DevFindIssue — existing records updated, not duplicated",
    "6.  Optional dry-run: preview without writing to Weaviate",
]
styled_bullet(s, steps_gh, Inches(0.4), Inches(0.85), Inches(7.2), Inches(4.5),
              font_size=12.5, title="Import Workflow")

add_table(s,
    ["Environment Variable", "Purpose"],
    [
        ["GITHUB_TOKEN",       "API authentication (Personal Access Token)"],
        ["GITHUB_REPO_OWNER",  "Repository owner or organisation name"],
        ["GITHUB_REPO_NAME",   "Repository name"],
    ],
    Inches(7.5), Inches(1.1), Inches(5.4),
    col_widths=[Inches(2.3), Inches(3.1)],
)

add_text_box(s, "Incremental sync: only changed issues are re-written. Repeated imports are safe.",
             Inches(0.4), Inches(6.85), Inches(12), Inches(0.4),
             font_size=10, italic=True, color=SLATE)


# ════════════════════════════════════════════════════════════
# SLIDE 15 — Knowledge Assistant / RAG
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "Knowledge Assistant (RAG Pipeline)")

rag_steps = [
    "1.  Developer asks a debugging question in the UI",
    "2.  hybrid_search retrieves top-k similar issues from DevFindIssue",
    "3.  search_knowledge retrieves matching knowledge chunks from DevFindKnowledge",
    "4.  Evidence compiled: issues + knowledge chunks as grounding context",
    "5.  LLM (Ollama / OpenAI) generates a cited answer",
    "6.  Citations reference only actually retrieved records",
]
styled_bullet(s, rag_steps, Inches(0.4), Inches(0.85), Inches(7.0), Inches(4.5),
              font_size=12.5, title="RAG Pipeline")

note_box(s,
    "Current status: DevFindKnowledge collection is subject to Weaviate Cloud "
    "rate limits on first creation. When the collection is unavailable, Knowledge Assistant "
    "displays a clear notice and halts gracefully. Issue search and duplicate detection "
    "remain fully operational.\n\n"
    "LLM provider is optional. When LLM_PROVIDER is not configured, an evidence summary "
    "is returned without AI generation.",
    Inches(7.5), Inches(1.1), Inches(5.5), Inches(3.8),
    bg=AMBER_LT, border=AMBER, text_color=RGBColor(0x92, 0x40, 0x0E))


# ════════════════════════════════════════════════════════════
# SLIDE 16 — Testing
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "Testing Methodology & Results")

add_table(s,
    ["Test Category", "Test Count", "Result"],
    [
        ["CRUD operations (mocked Weaviate)",          "13",  "Passed"],
        ["Schema operations incl. 429 safety tests",   "8",   "Passed"],
        ["Search metrics (Precision, Recall, MRR)",    "14",  "Passed"],
        ["RAG pipeline & citation fields",             "6",   "Passed"],
        ["GitHub integration (mocked API)",            "12",  "Passed"],
        ["Utils, validation, normalisation",           "38",  "Passed"],
        ["Misc search, filter, dataclass tests",       "60",  "Passed"],
        ["Live Weaviate (skipped — no credentials)",   "7",   "Skipped"],
        ["TOTAL",                                      "158", "151 passed · 7 skipped · 0 failed"],
    ],
    Inches(0.4), Inches(0.85), Inches(12.5),
    col_widths=[Inches(5.8), Inches(2.2), Inches(4.5)],
)

styled_bullet(s, [
    "  ·  Framework: pytest with unittest.mock",
    "  ·  Weaviate client fully mocked — tests run without credentials",
    "  ·  Live tests decorated @skip_live, skipped without WEAVIATE_URL/WEAVIATE_API_KEY",
    "  ·  Results from actual pytest run — not fabricated",
], Inches(0.4), Inches(5.55), Inches(12), Inches(1.5), font_size=11.5)


# ════════════════════════════════════════════════════════════
# SLIDE 17 — Evaluation
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "Evaluation Methodology")

styled_bullet(s, [
    "  ·  Synthetic evaluation dataset: 30 labeled query/candidate pairs",
    "  ·  Categories: duplicate (10), related (8), unrelated (4), ambiguous (4), exact error code (4)",
    "  ·  Metrics: Precision@k, Recall@k, Mean Reciprocal Rank (MRR), search latency",
    "  ·  Modes compared: keyword BM25, semantic near_text, hybrid (same queries and labels)",
    "  ·  Results saved to: results/eval_results.json and results/eval_results.csv",
], Inches(0.4), Inches(0.85), Inches(7.5), Inches(3.5), font_size=12.5, title="Methodology")

note_box(s,
    "IMPORTANT — Scope Limitation\n\n"
    "Results derive from a 30-query synthetic dataset with author-assigned relevance labels. "
    "The dataset is intentionally small and was constructed for demonstration purposes. "
    "Results are illustrative and not representative of production performance "
    "on real bug repositories. No fabricated benchmarks are included in this report.",
    Inches(7.8), Inches(0.85), Inches(5.2), Inches(3.8),
    bg=AMBER_LT, border=AMBER, text_color=RGBColor(0x78, 0x35, 0x0F))


# ════════════════════════════════════════════════════════════
# SLIDE 18 — Limitations & Future Work
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "Limitations & Future Work")

limits_l = [
    "  ·  DevFindKnowledge subject to Weaviate Cloud rate limits on creation",
    "  ·  Evaluation dataset is synthetic (30 queries, author-assigned labels)",
    "  ·  No automated duplicate merging",
    "  ·  LLM integration optional and unverified end-to-end in cloud environment",
    "  ·  No user authentication in the Streamlit UI",
    "  ·  App runs on localhost — no production deployment",
]
styled_bullet(s, limits_l, Inches(0.4), Inches(0.85), Inches(6.2), Inches(5.0),
              font_size=12.5, title="Current Limitations", color=DARK_TEXT)

future_l = [
    "  ·  Incremental GitHub sync on webhook trigger",
    "  ·  Fine-tuned re-ranker on confirmed duplicate pairs",
    "  ·  Larger real-world evaluation dataset (open-source bug trackers)",
    "  ·  Role-based access control",
    "  ·  Export confirmed duplicates to JIRA / Linear",
    "  ·  Automated nightly evaluation pipeline",
]
styled_bullet(s, future_l, Inches(7.0), Inches(0.85), Inches(6.0), Inches(5.0),
              font_size=12.5, title="Future Improvements", color=DARK_TEXT)


# ════════════════════════════════════════════════════════════
# SLIDE 19 — Conclusion
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "Conclusion")

add_text_box(s,
    "DevFind demonstrates a practical application of Weaviate as the primary data store for a "
    "semantically-aware issue intelligence platform. The project covers:\n\n"
    "  ·  Full CRUD operations with idempotent UUIDv5 upserts\n"
    "  ·  Three search modalities: keyword BM25, semantic near_text, hybrid\n"
    "  ·  Human-reviewed duplicate detection workflow with recorded decisions\n"
    "  ·  Idempotent GitHub Issues import with dry-run support\n"
    "  ·  Optional RAG-assisted debugging assistant with honest availability reporting\n"
    "  ·  151 passing unit tests, 7 skipped live tests, 0 failures\n"
    "  ·  Production-ready HTTP 429 rate-limit tolerance on startup",
    Inches(0.5), Inches(0.9), Inches(12), Inches(3.8),
    font_size=13, color=DARK_TEXT)

add_rect(s, Inches(0.5), Inches(4.9), Inches(12), Inches(1.5), fill_color=RGBColor(0xCC, 0xFB, 0xF1), line_color=TEAL)
add_text_box(s,
    "Weaviate is the primary database — not a secondary index. All issue records, "
    "knowledge chunks, and review decisions persist in and are retrieved from Weaviate.",
    Inches(0.7), Inches(5.05), Inches(11.5), Inches(1.1),
    font_size=13, bold=True, color=TEAL)


# ════════════════════════════════════════════════════════════
# SLIDE 20 — References
# ════════════════════════════════════════════════════════════
s = blank_slide(prs)
set_bg(s)
add_title_bar(s, "References")

refs = [
    "1.  Weaviate B.V. (2024). Weaviate Documentation. https://weaviate.io/developers/weaviate",
    "2.  Robertson, S., & Zaragoza, H. (2009). The Probabilistic Relevance Framework: BM25 and Beyond. "
        "Foundations and Trends in Information Retrieval, 3(4), 333–389.",
    "3.  Lewis, P., et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. "
        "Advances in Neural Information Processing Systems, 33.",
    "4.  GitHub. (2024). REST API documentation — Issues. https://docs.github.com/en/rest/issues",
    "5.  Python Software Foundation. (2024). uuid — UUID objects. https://docs.python.org/3/library/uuid.html",
    "6.  Streamlit Inc. (2024). Streamlit documentation. https://docs.streamlit.io",
    "7.  python-pptx contributors. (2024). python-pptx documentation. https://python-pptx.readthedocs.io",
    "8.  python-docx contributors. (2024). python-docx documentation. https://python-docx.readthedocs.io",
]
styled_bullet(s, refs, Inches(0.5), Inches(0.85), Inches(12.3), Inches(5.8), font_size=11)

# ════════════════════════════════════════════════════════════
# SAVE
# ════════════════════════════════════════════════════════════
import os
out_path = r"c:\Users\aadiu\Downloads\DevFind_Project_Package\docs\DevFind_Professional_Case_Study.pptx"
prs.save(out_path)
print(f"Saved: {out_path}")
print(f"Size:  {os.path.getsize(out_path):,} bytes")
print(f"Slides: {len(prs.slides)}")
