#!/usr/bin/env python3
"""Install cache-busted COT Intelligence assets into the lightweight dashboard shell."""
from __future__ import annotations
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
HTML=ROOT/"worldclass_dashboard.html"; JS=ROOT/"worldclass"/"cot-intelligence.js"; CSS=ROOT/"worldclass"/"cot-intelligence.css"
def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
def main()->None:
    for path in (HTML,JS,CSS):
        if not path.exists() or path.stat().st_size<=0: raise FileNotFoundError(path)
    text=HTML.read_text(encoding="utf-8")
    lines=[line for line in text.splitlines() if 'data-cot-intelligence-asset=' not in line]
    text="\n".join(lines)+("\n" if text.endswith("\n") else "")
    css_tag=f'<link rel="stylesheet" href="worldclass/cot-intelligence.css?v={digest(CSS)}" data-cot-intelligence-asset="css">'
    js_tag=f'<script defer src="worldclass/cot-intelligence.js?v={digest(JS)}" data-cot-intelligence-asset="js"></script>'
    if "</head>" not in text or "</body>" not in text: raise RuntimeError("worldclass_dashboard.html is missing closing head/body")
    text=text.replace("</head>",f"  {css_tag}\n</head>",1).replace("</body>",f"  {js_tag}\n</body>",1)
    HTML.write_text(text,encoding="utf-8")
    print(f"Installed COT Intelligence shell assets · css={digest(CSS)} js={digest(JS)}")
if __name__=="__main__":main()
