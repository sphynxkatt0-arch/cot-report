#!/usr/bin/env python3
"""Install cache-busted COT Intelligence assets into the lightweight dashboard shell."""
from __future__ import annotations
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
HTML=ROOT/"worldclass_dashboard.html"
JS=ROOT/"worldclass"/"cot-intelligence.js"
COPY_JS=ROOT/"worldclass"/"cot-intelligence-v2-copy.js"
CSS=ROOT/"worldclass"/"cot-intelligence.css"
LIGHT_CSS=ROOT/"worldclass"/"cot-intelligence-light.css"
CURRENT_EDGE_MODEL=ROOT/"worldclass"/"current-edge-model.js"
CURRENT_EDGE_JS=ROOT/"worldclass"/"current-edge-command.js"
CURRENT_EDGE_CSS=ROOT/"worldclass"/"current-edge-command.css"
MOBILE_UX_CSS=ROOT/"worldclass"/"mobile-ux.css"
def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
def main()->None:
    for path in (HTML,JS,COPY_JS,CSS,LIGHT_CSS,CURRENT_EDGE_MODEL,CURRENT_EDGE_JS,CURRENT_EDGE_CSS,MOBILE_UX_CSS):
        if not path.exists() or path.stat().st_size<=0:raise FileNotFoundError(path)
    text=HTML.read_text(encoding="utf-8")
    lines=[line for line in text.splitlines() if 'data-cot-intelligence-asset=' not in line]
    text="\n".join(lines)+("\n" if text.endswith("\n") else "")
    css_tag=f'<link rel="stylesheet" href="worldclass/cot-intelligence.css?v={digest(CSS)}" data-cot-intelligence-asset="css">'
    light_css_tag=f'<link rel="stylesheet" href="worldclass/cot-intelligence-light.css?v={digest(LIGHT_CSS)}" data-cot-intelligence-asset="light-css">'
    edge_css_tag=f'<link rel="stylesheet" href="worldclass/current-edge-command.css?v={digest(CURRENT_EDGE_CSS)}" data-cot-intelligence-asset="current-edge-css">'
    mobile_css_tag=f'<link rel="stylesheet" href="worldclass/mobile-ux.css?v={digest(MOBILE_UX_CSS)}" data-cot-intelligence-asset="mobile-ux-css">'
    js_tag=f'<script defer src="worldclass/cot-intelligence.js?v={digest(JS)}" data-cot-intelligence-asset="js"></script>'
    copy_js_tag=f'<script defer src="worldclass/cot-intelligence-v2-copy.js?v={digest(COPY_JS)}" data-cot-intelligence-asset="v2-copy-js"></script>'
    edge_model_tag=f'<script defer src="worldclass/current-edge-model.js?v={digest(CURRENT_EDGE_MODEL)}" data-cot-intelligence-asset="current-edge-model"></script>'
    edge_js_tag=f'<script defer src="worldclass/current-edge-command.js?v={digest(CURRENT_EDGE_JS)}" data-cot-intelligence-asset="current-edge-js"></script>'
    if "</head>" not in text or "</body>" not in text:raise RuntimeError("worldclass_dashboard.html is missing closing head/body")
    text=text.replace("</head>",f"  {css_tag}\n  {light_css_tag}\n  {edge_css_tag}\n  {mobile_css_tag}\n</head>",1).replace("</body>",f"  {js_tag}\n  {copy_js_tag}\n  {edge_model_tag}\n  {edge_js_tag}\n</body>",1)
    HTML.write_text(text,encoding="utf-8")
    print(f"Installed COT Intelligence shell assets · css={digest(CSS)} light-css={digest(LIGHT_CSS)} js={digest(JS)} v2-copy={digest(COPY_JS)} current-edge={digest(CURRENT_EDGE_JS)} mobile-ux={digest(MOBILE_UX_CSS)}")
if __name__=="__main__":main()
