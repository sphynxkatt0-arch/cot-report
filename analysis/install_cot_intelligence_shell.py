#!/usr/bin/env python3
"""Install cache-busted COT Intelligence assets into the lightweight dashboard shell."""
from __future__ import annotations
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
HTML=ROOT/"worldclass_dashboard.html"
JS=ROOT/"worldclass"/"cot-intelligence.js"
CSS=ROOT/"worldclass"/"cot-intelligence.css"
LIGHT_CSS=ROOT/"worldclass"/"cot-intelligence-light.css"
CURRENT_EDGE_MODEL=ROOT/"worldclass"/"current-edge-model.js"
CURRENT_EDGE_JS=ROOT/"worldclass"/"current-edge-command.js"
CURRENT_EDGE_CSS=ROOT/"worldclass"/"current-edge-command.css"
MOBILE_UX_CSS=ROOT/"worldclass"/"mobile-ux.css"
MOBILE_UX_RUNTIME=ROOT/"worldclass"/"mobile-ux-runtime.js"
WORLDCLASS_UX_CSS=ROOT/"worldclass"/"cot-intelligence-worldclass-ux.css"
WORLDCLASS_UX_RUNTIME=ROOT/"worldclass"/"cot-intelligence-worldclass-ux.js"
REPORT_TAXONOMY_CSS=ROOT/"worldclass"/"report-taxonomy.css"
REPORT_TAXONOMY_RUNTIME=ROOT/"worldclass"/"report-taxonomy.js"
UX_HARDENING_CSS=ROOT/"worldclass"/"ux-hardening.css"
UX_HARDENING_RUNTIME=ROOT/"worldclass"/"ux-hardening.js"
def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
def main()->None:
    for path in (HTML,JS,CSS,LIGHT_CSS,CURRENT_EDGE_MODEL,CURRENT_EDGE_JS,CURRENT_EDGE_CSS,MOBILE_UX_CSS,MOBILE_UX_RUNTIME,WORLDCLASS_UX_CSS,WORLDCLASS_UX_RUNTIME,REPORT_TAXONOMY_CSS,REPORT_TAXONOMY_RUNTIME,UX_HARDENING_CSS,UX_HARDENING_RUNTIME):
        if not path.exists() or path.stat().st_size<=0: raise FileNotFoundError(path)
    text=HTML.read_text(encoding="utf-8")
    lines=[line for line in text.splitlines() if 'data-cot-intelligence-asset=' not in line]
    text="\n".join(lines)+("\n" if text.endswith("\n") else "")
    css_tag=f'<link rel="stylesheet" href="worldclass/cot-intelligence.css?v={digest(CSS)}" data-cot-intelligence-asset="css">'
    light_css_tag=f'<link rel="stylesheet" href="worldclass/cot-intelligence-light.css?v={digest(LIGHT_CSS)}" data-cot-intelligence-asset="light-css">'
    edge_css_tag=f'<link rel="stylesheet" href="worldclass/current-edge-command.css?v={digest(CURRENT_EDGE_CSS)}" data-cot-intelligence-asset="current-edge-css">'
    mobile_css_tag=f'<link rel="stylesheet" href="worldclass/mobile-ux.css?v={digest(MOBILE_UX_CSS)}" data-cot-intelligence-asset="mobile-ux-css">'
    worldclass_ux_css_tag=f'<link rel="stylesheet" href="worldclass/cot-intelligence-worldclass-ux.css?v={digest(WORLDCLASS_UX_CSS)}" data-cot-intelligence-asset="worldclass-ux-css">'
    report_taxonomy_css_tag=f'<link rel="stylesheet" href="worldclass/report-taxonomy.css?v={digest(REPORT_TAXONOMY_CSS)}" data-cot-intelligence-asset="report-taxonomy-css">'
    ux_hardening_css_tag=f'<link rel="stylesheet" href="worldclass/ux-hardening.css?v={digest(UX_HARDENING_CSS)}" data-cot-intelligence-asset="ux-hardening-css">'
    js_tag=f'<script defer src="worldclass/cot-intelligence.js?v={digest(JS)}" data-cot-intelligence-asset="js"></script>'
    report_taxonomy_runtime_tag=f'<script defer src="worldclass/report-taxonomy.js?v={digest(REPORT_TAXONOMY_RUNTIME)}" data-cot-intelligence-asset="report-taxonomy-js"></script>'
    edge_model_tag=f'<script defer src="worldclass/current-edge-model.js?v={digest(CURRENT_EDGE_MODEL)}" data-cot-intelligence-asset="current-edge-model"></script>'
    edge_js_tag=f'<script defer src="worldclass/current-edge-command.js?v={digest(CURRENT_EDGE_JS)}" data-cot-intelligence-asset="current-edge-js"></script>'
    mobile_runtime_tag=f'<script defer src="worldclass/mobile-ux-runtime.js?v={digest(MOBILE_UX_RUNTIME)}" data-cot-intelligence-asset="mobile-ux-runtime"></script>'
    worldclass_ux_runtime_tag=f'<script defer src="worldclass/cot-intelligence-worldclass-ux.js?v={digest(WORLDCLASS_UX_RUNTIME)}" data-cot-intelligence-asset="worldclass-ux-runtime"></script>'
    ux_hardening_runtime_tag=f'<script defer src="worldclass/ux-hardening.js?v={digest(UX_HARDENING_RUNTIME)}" data-cot-intelligence-asset="ux-hardening-js"></script>'
    if "</head>" not in text or "</body>" not in text: raise RuntimeError("worldclass_dashboard.html is missing closing head/body")
    text=text.replace("</head>",f"  {css_tag}\n  {light_css_tag}\n  {edge_css_tag}\n  {mobile_css_tag}\n  {worldclass_ux_css_tag}\n  {report_taxonomy_css_tag}\n  {ux_hardening_css_tag}\n</head>",1).replace("</body>",f"  {js_tag}\n  {report_taxonomy_runtime_tag}\n  {edge_model_tag}\n  {edge_js_tag}\n  {mobile_runtime_tag}\n  {worldclass_ux_runtime_tag}\n  {ux_hardening_runtime_tag}\n</body>",1)
    HTML.write_text(text,encoding="utf-8")
    print(f"Installed COT Intelligence shell assets · css={digest(CSS)} light-css={digest(LIGHT_CSS)} js={digest(JS)} report-taxonomy={digest(REPORT_TAXONOMY_RUNTIME)} current-edge={digest(CURRENT_EDGE_JS)} mobile-ux={digest(MOBILE_UX_CSS)} worldclass-ux={digest(WORLDCLASS_UX_CSS)} ux-hardening={digest(UX_HARDENING_CSS)}")
if __name__=="__main__":main()
