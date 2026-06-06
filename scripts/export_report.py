#!/usr/bin/env python3
"""Export an analysis report as Markdown, standalone HTML, or both."""

from __future__ import annotations

import argparse
import base64
import html
import mimetypes
import re
import shutil
from datetime import datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Source Markdown report")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--basename", default="analysis-report")
    parser.add_argument(
        "--format",
        choices=["Markdown", "HTML", "Markdown + HTML"],
        default="Markdown + HTML",
    )
    parser.add_argument("--title", help="HTML document title")
    parser.add_argument("--no-embed-assets", action="store_true")
    return parser.parse_args()


def inline_markup(text: str, source_dir: Path, embed_assets: bool) -> str:
    placeholders: list[str] = []

    def stash(value: str) -> str:
        placeholders.append(value)
        return f"\x00{len(placeholders) - 1}\x00"

    def image_repl(match: re.Match[str]) -> str:
        alt = html.escape(match.group(1), quote=True)
        raw_src = match.group(2).strip()
        src_path = Path(raw_src)
        if not src_path.is_absolute():
            src_path = (source_dir / src_path).resolve()
        src = raw_src
        if embed_assets and src_path.exists() and src_path.is_file():
            mime = mimetypes.guess_type(src_path.name)[0] or "application/octet-stream"
            encoded = base64.b64encode(src_path.read_bytes()).decode("ascii")
            src = f"data:{mime};base64,{encoded}"
        return stash(f'<figure><img src="{html.escape(src, quote=True)}" alt="{alt}"><figcaption>{alt}</figcaption></figure>')

    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", image_repl, text)
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", lambda m: stash(f"<code>{html.escape(m.group(1))}</code>"), text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    for index, value in enumerate(placeholders):
        text = text.replace(f"\x00{index}\x00", value)
    return text


def split_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def is_table_separator(line: str) -> bool:
    cells = split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def markdown_to_html(markdown: str, source_dir: Path, embed_assets: bool) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None
    in_code = False
    code_lines: list[str] = []
    index = 0

    def close_paragraph() -> None:
        if paragraph:
            output.append(f"<p>{inline_markup(' '.join(paragraph), source_dir, embed_assets)}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_type
        if list_type:
            output.append(f"</{list_type}>")
            list_type = None

    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            close_paragraph()
            close_list()
            if in_code:
                output.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines.clear()
                in_code = False
            else:
                in_code = True
            index += 1
            continue
        if in_code:
            code_lines.append(line)
            index += 1
            continue
        if not line.strip():
            close_paragraph()
            close_list()
            index += 1
            continue
        if line.strip() == "---":
            close_paragraph()
            close_list()
            output.append("<hr>")
            index += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            close_paragraph()
            close_list()
            level = len(heading.group(1))
            output.append(f"<h{level}>{inline_markup(heading.group(2), source_dir, embed_assets)}</h{level}>")
            index += 1
            continue
        if line.startswith("> "):
            close_paragraph()
            close_list()
            output.append(f"<blockquote>{inline_markup(line[2:], source_dir, embed_assets)}</blockquote>")
            index += 1
            continue
        if "|" in line and index + 1 < len(lines) and is_table_separator(lines[index + 1]):
            close_paragraph()
            close_list()
            headers = split_table_row(line)
            output.append("<div class=\"table-wrap\"><table><thead><tr>")
            output.extend(f"<th>{inline_markup(cell, source_dir, embed_assets)}</th>" for cell in headers)
            output.append("</tr></thead><tbody>")
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                cells = split_table_row(lines[index])
                output.append("<tr>")
                output.extend(f"<td>{inline_markup(cell, source_dir, embed_assets)}</td>" for cell in cells)
                output.append("</tr>")
                index += 1
            output.append("</tbody></table></div>")
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", line)
        numbered = re.match(r"^\d+\.\s+(.+)$", line)
        if bullet or numbered:
            close_paragraph()
            wanted = "ul" if bullet else "ol"
            if list_type != wanted:
                close_list()
                list_type = wanted
                output.append(f"<{wanted}>")
            content = (bullet or numbered).group(1)
            output.append(f"<li>{inline_markup(content, source_dir, embed_assets)}</li>")
            index += 1
            continue
        close_list()
        paragraph.append(line.strip())
        index += 1

    close_paragraph()
    close_list()
    if in_code:
        output.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(output)


def html_document(body: str, title: str) -> str:
    generated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light; --ink:#17202a; --muted:#667085; --line:#d0d5dd; --accent:#175cd3; --panel:#f8fafc; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:#fff; font:15px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    main {{ width:min(1080px,calc(100% - 40px)); margin:40px auto 80px; }}
    h1 {{ font-size:30px; margin:0 0 24px; border-bottom:2px solid var(--ink); padding-bottom:12px; }}
    h2 {{ font-size:22px; margin:38px 0 14px; border-bottom:1px solid var(--line); padding-bottom:7px; }}
    h3 {{ font-size:17px; margin:26px 0 10px; }}
    p,li {{ max-width:88ch; }}
    a {{ color:var(--accent); }}
    blockquote {{ margin:16px 0; padding:12px 16px; border-left:4px solid var(--accent); background:var(--panel); }}
    code {{ padding:2px 5px; background:#f2f4f7; border-radius:3px; }}
    pre {{ overflow:auto; padding:16px; background:#101828; color:#f9fafb; border-radius:6px; }}
    pre code {{ padding:0; background:none; }}
    .table-wrap {{ overflow-x:auto; margin:14px 0 24px; }}
    table {{ border-collapse:collapse; width:100%; min-width:560px; }}
    th,td {{ border:1px solid var(--line); padding:8px 10px; text-align:left; vertical-align:top; }}
    th {{ background:#f2f4f7; }}
    figure {{ margin:24px 0; }}
    img {{ display:block; max-width:100%; height:auto; border:1px solid var(--line); }}
    figcaption {{ margin-top:6px; color:var(--muted); font-size:13px; }}
    footer {{ margin-top:56px; padding-top:12px; border-top:1px solid var(--line); color:var(--muted); font-size:12px; }}
    @media print {{ main {{ width:100%; margin:0; }} a {{ color:inherit; text-decoration:none; }} }}
  </style>
</head>
<body>
<main>
{body}
<footer>生成时间：{generated}</footer>
</main>
</body>
</html>
"""


def main() -> None:
    args = parse_args()
    source = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown = source.read_text(encoding="utf-8")
    outputs = []

    if args.format in {"Markdown", "Markdown + HTML"}:
        markdown_output = output_dir / f"{args.basename}.md"
        if source != markdown_output:
            shutil.copyfile(source, markdown_output)
        outputs.append(str(markdown_output))

    if args.format in {"HTML", "Markdown + HTML"}:
        title = args.title or next(
            (line.lstrip("# ").strip() for line in markdown.splitlines() if line.startswith("# ")),
            "业务分析报告",
        )
        body = markdown_to_html(markdown, source.parent, not args.no_embed_assets)
        html_output = output_dir / f"{args.basename}.html"
        html_output.write_text(html_document(body, title), encoding="utf-8")
        outputs.append(str(html_output))

    print(
        __import__("json").dumps(
            {"format": args.format, "outputs": outputs, "assets_embedded": not args.no_embed_assets},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
