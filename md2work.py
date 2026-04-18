#!/usr/bin/env python3
"""
md2work — Convert a markdown case study to a portfolio work page.

Usage:
    python md2work.py path/to/case-study.md
    python md2work.py path/to/case-study.md --output-dir ./work

The input file should have YAML-style frontmatter:

    ---
    title: Your Project Title
    subtitle: One or two sentences summarizing impact.
    ---

    ## Context

    Background prose...

    ## Key Challenges

    ### Challenge Title

    Problem: ...
    Solution: ...

    ## Results & Impact

    - **~2000 RPS** sustained throughput

    ## Observability

    ![Caption text for image](/images/grafana.png)

    ## System Architecture

    ```diagram
    <!-- D2 or Mermaid render here -->
    ```

Automatic mappings:
  - frontmatter title          → <h1 class="work-title">
  - frontmatter subtitle       → <p class="work-subtitle">
  - ## Section                 → <section class="work-section">
  - ### Challenge (in section) → <div class="challenge">
  - ```diagram blocks          → <div class="diagram">
  - ![caption](src) images     → <div class="image-block">
  - <ul> in results/metrics    → <ul class="metrics">

Dependencies: markdown, beautifulsoup4
    pip install markdown beautifulsoup4

D2 diagrams:
    ```diagram blocks are rendered to SVG using the d2 CLI if it is installed.
    Install d2: https://d2lang.com/tour/install
    If d2 is not found, a placeholder div is emitted instead.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

try:
    from markdown import Markdown
except ImportError:
    sys.exit("Missing dependency: pip install markdown")

try:
    from bs4 import BeautifulSoup, NavigableString, Tag, XMLParsedAsHTMLWarning
    import warnings
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
except ImportError:
    sys.exit("Missing dependency: pip install beautifulsoup4")


# ── Frontmatter ───────────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> "tuple[dict, str]":
    """
    Split YAML-style frontmatter from the markdown body.

    Returns (meta_dict, body_text). If no frontmatter is present,
    meta_dict will be empty and body_text is the full input.
    """
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return {}, text

    # Find the closing ---
    rest = stripped[3:]
    end = rest.find("\n---")
    if end == -1:
        return {}, text

    fm_block = rest[:end]
    body = rest[end + 4:].lstrip("\n")

    meta = {}
    for line in fm_block.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()
            # Strip surrounding quotes
            if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            meta[key] = value

    return meta, body


# ── HTML post-processing ──────────────────────────────────────────────────────

def wrap_sections(soup: BeautifulSoup) -> None:
    """
    Group content between <h2> headings into <section class="work-section">.
    Operates on the top-level children of the soup.
    """
    # Collect top-level nodes
    top = list(soup.children)

    # Find h2 positions
    h2_indices = [i for i, el in enumerate(top) if isinstance(el, Tag) and el.name == "h2"]
    if not h2_indices:
        return

    # Build groups: everything before first h2 stays, then each h2 + its following siblings
    sections = []
    boundaries = h2_indices + [len(top)]
    for j, start in enumerate(h2_indices):
        end = boundaries[j + 1]
        group = top[start:end]
        sections.append(group)

    pre_section = top[: h2_indices[0]]

    # Remove all top-level nodes from soup
    for el in top:
        el.extract()

    # Re-add pre-section nodes
    for el in pre_section:
        soup.append(el)

    # Re-add each group wrapped in a section
    for group in sections:
        section_tag = soup.new_tag("section", attrs={"class": "work-section"})
        for el in group:
            section_tag.append(el)
        soup.append(section_tag)


def wrap_challenges(soup: BeautifulSoup) -> None:
    """
    Within each <section class="work-section">, wrap content between <h3>
    headings into <div class="challenge">.
    """
    for section in soup.find_all("section", class_="work-section"):
        children = list(section.children)
        h3_indices = [
            i for i, el in enumerate(children)
            if isinstance(el, Tag) and el.name == "h3"
        ]
        if not h3_indices:
            continue

        challenges = []
        boundaries = h3_indices + [len(children)]
        for j, start in enumerate(h3_indices):
            end = boundaries[j + 1]
            challenges.append(children[start:end])

        pre_challenge = children[: h3_indices[0]]

        # Remove all children from section
        for el in children:
            el.extract()

        for el in pre_challenge:
            section.append(el)

        for group in challenges:
            div = soup.new_tag("div", attrs={"class": "challenge"})
            for el in group:
                div.append(el)
            section.append(div)


def render_d2(source: str, theme: int = 200) -> Optional[str]:
    """
    Render a D2 diagram source string to an SVG string using the d2 CLI.

    Uses a temp file pair so d2 can write a proper .svg output.
    Returns the SVG string on success, or None if d2 is unavailable or fails.

    Theme 200 is "Dark Mauve" — a good match for this site's dark palette.
    """
    if not shutil.which("d2"):
        return None

    tmp_in = tmp_out = None
    try:
        fd, tmp_in = tempfile.mkstemp(suffix=".d2")
        with os.fdopen(fd, "w") as f:
            f.write(source)
        tmp_out = tmp_in.replace(".d2", ".svg")

        result = subprocess.run(
            ["d2", f"--theme={theme}", tmp_in, tmp_out],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"Warning: d2 failed: {result.stderr.strip()}", file=sys.stderr)
            return None

        return Path(tmp_out).read_text(encoding="utf-8")

    except subprocess.TimeoutExpired:
        print("Warning: d2 rendering timed out", file=sys.stderr)
        return None
    finally:
        if tmp_in and os.path.exists(tmp_in):
            os.unlink(tmp_in)
        if tmp_out and os.path.exists(tmp_out):
            os.unlink(tmp_out)


def process_diagrams(soup: BeautifulSoup, d2_theme: int = 200) -> None:
    """
    Convert ```diagram fenced blocks to <div class="diagram">.

    Python-Markdown renders them as:
        <pre><code class="language-diagram">content</code></pre>

    If the d2 CLI is available and the block contains non-empty, non-comment
    content, the diagram is rendered to an inline SVG. Otherwise a placeholder
    div is emitted with the raw source preserved as an HTML comment.
    """
    for pre in soup.find_all("pre"):
        code = pre.find("code", class_="language-diagram")
        if not code:
            continue

        source = code.get_text()
        div = soup.new_tag("div", attrs={"class": "diagram"})

        # Only attempt rendering if there's actual D2 source (not just a comment)
        stripped = source.strip()
        is_placeholder = not stripped or stripped.startswith("<!--")

        if not is_placeholder:
            svg = render_d2(stripped, theme=d2_theme)
            if svg:
                div.append(BeautifulSoup(svg, "html.parser"))
                pre.replace_with(div)
                continue
            # d2 failed — fall through to placeholder

        # Emit placeholder with source preserved as a comment for later use
        comment_source = source.replace("--", "- -")  # HTML comments can't contain --
        div.append(BeautifulSoup(f"<!-- d2 diagram source:\n{comment_source}\n-->", "html.parser"))
        pre.replace_with(div)


def process_images(soup: BeautifulSoup) -> None:
    """
    Convert inline images to image-block wrappers.

    Markdown `![caption](src)` renders as `<p><img alt="caption" src="..."></p>`.
    We transform that into:
        <div class="image-block">
            <img src="...">
            <p class="caption">caption</p>
        </div>
    """
    for p in soup.find_all("p"):
        img = p.find("img")
        if not img:
            continue
        # Only convert if the <p> is essentially just the image
        text_content = p.get_text(strip=True).replace(img.get("alt", ""), "").strip()
        if text_content:
            continue

        src = img.get("src", "")
        alt = img.get("alt", "")

        div = soup.new_tag("div", attrs={"class": "image-block"})

        new_img = soup.new_tag("img", attrs={"src": src})
        div.append(new_img)

        if alt:
            cap = soup.new_tag("p", attrs={"class": "caption"})
            cap.string = alt
            div.append(cap)

        p.replace_with(div)


def add_metrics_class(soup: BeautifulSoup) -> None:
    """
    Add class="metrics" to <ul> elements inside sections whose <h2>
    contains "result", "impact", or "metric" (case-insensitive).
    """
    keywords = ("result", "impact", "metric")
    for section in soup.find_all("section", class_="work-section"):
        h2 = section.find("h2")
        if not h2:
            continue
        heading_text = h2.get_text().lower()
        if any(kw in heading_text for kw in keywords):
            for ul in section.find_all("ul"):
                existing = ul.get("class") or []
                if "metrics" not in existing:
                    ul["class"] = existing + ["metrics"]


# ── Template ──────────────────────────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">

<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title} — Julian Miller</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link
    href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,300;1,9..40,400&display=swap"
    rel="stylesheet">
  <link rel="stylesheet" href="/style.css">
</head>

<body>

  <nav>
    <a class="nav-logo" href="/"><span>//</span> julian miller</a>
    <ul class="nav-links">
      <li><a href="/">Home</a></li>
      <li><a href="/about">About</a></li>
    </ul>
  </nav>

  <div class="work-page">
    <div class="work-inner">

      <h1 class="work-title">{title}</h1>
{subtitle_html}
{body}
    </div>
  </div>

  <footer>
    <img id="noface" src="/images/noface.gif" alt="">
    <p>
      <a href="https://github.com/jrm780" target="_blank" rel="noopener">github</a> &nbsp;·&nbsp;
      <a href="https://www.linkedin.com/in/miller-julian" target="_blank" rel="noopener">linkedin</a> &nbsp;·&nbsp;
      <a href="https://open.spotify.com/user/22axdljviev6cd5idcjkf7rpi?si=bd9efb269df6481bg" target="_blank" rel="noopener">what i listen to</a> &nbsp;·&nbsp;
      <a href="&#109;&#97;&#105;&#108;&#116;&#111;&#58;&#106;&#117;&#108;&#105;&#97;&#110;&#64;&#106;&#117;&#108;&#105;&#97;&#110;&#109;&#105;&#108;&#108;&#101;&#114;&#46;&#99;&#97;">&#106;&#117;&#108;&#105;&#97;&#110;&#64;&#106;&#117;&#108;&#105;&#97;&#110;&#109;&#105;&#108;&#108;&#101;&#114;&#46;&#99;&#97;</a>
    </p>
    <p>&copy; <span id="copyright-year"></span> Julian Miller</p>
  </footer>

  <script>
    document.getElementById('copyright-year').textContent = new Date().getFullYear();

    const nav = document.querySelector('nav');
    window.addEventListener('scroll', () => {{
      nav.classList.toggle('scrolled', window.scrollY > 10);
    }}, {{ passive: true }});
  </script>
  <script src="/js/noface.js"></script>

</body>

</html>
"""


# ── Main ──────────────────────────────────────────────────────────────────────

def convert(input_path: Path, output_dir: Path, d2_theme: int = 200) -> Path:
    text = input_path.read_text(encoding="utf-8")

    meta, body_text = parse_frontmatter(text)

    title = meta.get("title", input_path.stem.replace("-", " ").title())
    subtitle = meta.get("subtitle", "")

    # Convert markdown body to HTML
    md = Markdown(extensions=["fenced_code", "tables", "extra"])
    body_html = md.convert(body_text)

    # Post-process
    soup = BeautifulSoup(body_html, "html.parser")
    process_diagrams(soup, d2_theme=d2_theme)
    wrap_sections(soup)
    wrap_challenges(soup)
    process_images(soup)
    add_metrics_class(soup)

    body_formatted = soup.prettify(formatter="html5")

    subtitle_html = (
        f'      <p class="work-subtitle">\n        {subtitle}\n      </p>\n'
        if subtitle else ""
    )

    html = HTML_TEMPLATE.format(
        title=title,
        subtitle_html=subtitle_html,
        body=body_formatted,
    )

    slug = input_path.stem
    out_dir = output_dir / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "index.html"
    out_file.write_text(html, encoding="utf-8")

    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a markdown case study to a work page HTML file."
    )
    parser.add_argument("input", help="Path to the .md file")
    parser.add_argument(
        "--output-dir",
        default="./work",
        help="Directory to write work/<slug>/index.html into (default: ./work)",
    )
    parser.add_argument(
        "--d2-theme",
        type=int,
        default=200,
        metavar="N",
        help="D2 theme ID to use when rendering diagrams (default: 200 = Dark Mauve)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        sys.exit(f"Error: file not found: {input_path}")
    if input_path.suffix != ".md":
        sys.exit(f"Error: expected a .md file, got: {input_path}")

    output_dir = Path(args.output_dir)
    out_file = convert(input_path, output_dir, d2_theme=args.d2_theme)
    print(f"Written: {out_file}")


if __name__ == "__main__":
    main()
