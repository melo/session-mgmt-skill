#!/usr/bin/env python3
"""Convert a Markdown file to a styled PDF.

Uses python-markdown for Markdown→HTML and WeasyPrint for HTML→PDF.
Requires system-wide installation of weasyprint and markdown:
    sudo uv pip install --system weasyprint markdown

System dependencies (pango, cairo, gdk-pixbuf) must also be present.

Usage:
    python3 ~/.claude/scripts/md2pdf.py <input.md> <output.pdf>
"""

import os
import sys

import markdown
from weasyprint import HTML

CSS = """
@page {
    size: A4;
    margin: 2cm 2.5cm;
    @bottom-center {
        content: counter(page);
        font-size: 10px;
        color: #666;
    }
}

body {
    font-family: sans-serif;
    font-size: 13px;
    line-height: 1.6;
    color: #222;
}

h1 {
    font-size: 24px;
    border-bottom: 2px solid #333;
    padding-bottom: 8px;
    margin-bottom: 16px;
    break-before: page;
}

/* Don't break before the first h1 (document title) */
h1:first-of-type {
    break-before: auto;
}

h2 {
    font-size: 20px;
    border-bottom: 1px solid #ccc;
    padding-bottom: 6px;
    margin-top: 24px;
    break-before: page;
}

/* Don't break before the first h2 when it immediately follows the title */
h1:first-of-type ~ h2:first-of-type {
    break-before: auto;
}

h3 {
    font-size: 16px;
    margin-top: 20px;
}

h4 {
    font-size: 14px;
    margin-top: 16px;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin: 12px 0;
    font-size: 12px;
}

th, td {
    border: 1px solid #ccc;
    padding: 6px 10px;
    text-align: left;
}

th {
    background-color: #f5f5f5;
    font-weight: bold;
}

code {
    background-color: #f4f4f4;
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 12px;
}

pre {
    background-color: #f4f4f4;
    padding: 12px;
    border-radius: 4px;
    overflow-x: auto;
    font-size: 11px;
    line-height: 1.4;
}

pre code {
    background: none;
    padding: 0;
}

blockquote {
    border-left: 3px solid #ccc;
    margin: 12px 0;
    padding: 8px 16px;
    color: #555;
    background-color: #fafafa;
}

hr {
    border: none;
    border-top: 1px solid #ddd;
    margin: 24px 0;
}

strong {
    font-weight: 600;
}

del {
    text-decoration: line-through;
    color: #999;
}

ul, ol {
    padding-left: 24px;
}

li {
    margin-bottom: 4px;
}

img {
    max-width: 100%;
    height: auto;
}

/* Footnotes */
div.footnote {
    margin-top: 32px;
    padding-top: 12px;
    border-top: 1px solid #ccc;
    font-size: 11px;
    line-height: 1.5;
    color: #555;
}

div.footnote ol {
    padding-left: 20px;
}

div.footnote li {
    margin-bottom: 4px;
}

div.footnote hr {
    display: none;
}

sup a.footnote-ref {
    color: #0066cc;
    text-decoration: none;
    font-size: 10px;
}

a.footnote-backref {
    color: #0066cc;
    text-decoration: none;
    font-size: 10px;
}
"""


def convert(md_path: str, pdf_path: str) -> None:
    with open(md_path) as f:
        md_text = f.read()

    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "smarty", "footnotes"],
    )

    html_doc = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{CSS}</style>
</head>
<body>
{html_body}
</body>
</html>"""

    base_url = os.path.dirname(os.path.abspath(md_path))
    HTML(string=html_doc, base_url=base_url).write_pdf(pdf_path)
    print(f"  {pdf_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.md> <output.pdf>")
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
