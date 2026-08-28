"""Build docs/user-guide.html from docs/user-guide.src.html, embedding docs/images/*.png as data URIs.

Usage: python3 tools/build_docs_html.py
"""
import base64, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMG = ROOT / "docs" / "images"
SRC = ROOT / "docs" / "user-guide.src.html"
OUT = ROOT / "docs" / "user-guide.html"


def main() -> None:
    html = SRC.read_text()
    out = re.sub(r"\{\{img:([^}]+)\}\}", lambda m: "data:image/png;base64," + base64.b64encode((IMG / m.group(1)).read_bytes()).decode(), html)
    OUT.write_text(out)
    print(f"{OUT.name}: {len(out) // 1024} KB")


if __name__ == "__main__":
    main()
