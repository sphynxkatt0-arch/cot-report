#!/usr/bin/env python3
"""Install the immutable release-corrected v2 research into production runtime.

Historical research is read only from the frozen snapshot. Current actor state is
recomputed from the latest normalized COT inputs, then active thresholds and
cross-market context are resolved against the frozen v2 evidence. The browser's
canonical filenames are replaced atomically; old research snapshots are never
modified.
"""
from __future__ import annotations
import gzip,hashlib,json,shutil,subprocess,sys
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parent;WC=ROOT/'worldclass';RESEARCH=WC/'research'
SNAP=RESEARCH/'snapshots'/'2026-08-11-release-corrected-v2'
CANON_REG=WC/'cot-edge-registry.json';CANON_ACTIVE=WC/'cot-active-edges.json';CANON_CROSS=WC/'cot-cross-market.json';CANON_DETAILS=WC/'cot-edge-details'
COPY_JS=WC/'cot-intelligence-v2-copy.js';HTML=ROOT/'worldclass_dashboard.html'

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def short_sha(path:Path)->str:return sha(path)[:12]
def load(path:Path)->dict[str,Any]:
    p=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(p,dict):raise RuntimeError(path)
    return p
def atomic_copy(src:Path,dst:Path)->None:
    dst.parent.mkdir(parents=True,exist_ok=True);tmp=dst.with_suffix(dst.suffix+'.tmp');shutil.copyfile(src,tmp);tmp.replace(dst)
def verify_snapshot()->dict[str,Any]:
    manifest=load(SNAP/'verification-manifest.json')
    if manifest.get('research_generation')!='release-corrected-v2' or manifest.get('promotion_eligible') is not False:raise RuntimeError('invalid frozen v2 manifest')
    sums={}
    for line in (SNAP/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        if not line.strip():continue
        digest,relative=line.split('  ',1);sums[relative]=digest
    for relative,digest in sums.items():
        path=SNAP/relative
        if not path.is_file() or sha(path)!=digest:raise RuntimeError(f'frozen snapshot checksum mismatch: {relative}')
    return manifest
def extract_gz(src:Path,dst:Path)->None:
    dst.parent.mkdir(parents=True,exist_ok=True);tmp=dst.with_suffix(dst.suffix+'.tmp')
    with gzip.open(src,'rb') as inp,tmp.open('wb') as out:shutil.copyfileobj(inp,out)
    tmp.replace(dst)
def run(script:str)->None:subprocess.run([sys.executable,str(ROOT/script)],cwd=ROOT,check=True)
def install_copy_asset()->None:
    if not COPY_JS.is_file() or COPY_JS.stat().st_size<=0:raise FileNotFoundError(COPY_JS)
    if not HTML.is_file() or HTML.stat().st_size<=0:raise FileNotFoundError(HTML)
    text=HTML.read_text(encoding='utf-8')
    lines=[line for line in text.splitlines() if 'data-cot-intelligence-asset="v2-copy-js"' not in line]
    text='\n'.join(lines)+('\n' if text.endswith('\n') else '')
    if '</body>' not in text:raise RuntimeError('worldclass_dashboard.html is missing closing body')
    tag=f'<script defer src="worldclass/cot-intelligence-v2-copy.js?v={short_sha(COPY_JS)}" data-cot-intelligence-asset="v2-copy-js"></script>'
    text=text.replace('</body>',f'  {tag}\n</body>',1);HTML.write_text(text,encoding='utf-8')
    print(f'Installed release-corrected copy asset · v2-copy={short_sha(COPY_JS)}')
def main()->None:
    manifest=verify_snapshot()
    atomic_copy(SNAP/'cot-edge-registry-v2.json',CANON_REG)
    if CANON_DETAILS.exists():shutil.rmtree(CANON_DETAILS)
    CANON_DETAILS.mkdir(parents=True,exist_ok=True)
    for src in sorted((SNAP/'cot-edge-details-v2').glob('*.json')):atomic_copy(src,CANON_DETAILS/src.name)
    inference=RESEARCH/'cot-threshold-inference-v2.json';actor=RESEARCH/'cot-actor-event-research.json';summary=RESEARCH/'cot-actor-event-summary.json'
    extract_gz(SNAP/'cot-threshold-inference-v2.json.gz',inference);extract_gz(SNAP/'cot-actor-event-research.json.gz',actor);atomic_copy(SNAP/'cot-actor-event-summary.json',summary)
    try:
        run('build_cot_current_state.py');run('build_cot_active_edges_v2.py');run('build_cot_cross_market_runtime_v2.py')
        active_v2=WC/'cot-active-edges-v2.json';cross_v2=WC/'cot-cross-market-v2.json'
        atomic_copy(active_v2,CANON_ACTIVE);atomic_copy(cross_v2,CANON_CROSS)
        current=load(WC/'cot-current-state.json');active=load(CANON_ACTIVE);registry=load(CANON_REG);cross=load(CANON_CROSS)
        if registry.get('research_generation')!='release-corrected-v2' or active.get('research_generation')!='release-corrected-v2' or cross.get('research_generation')!='release-corrected-v2':raise RuntimeError('canonical runtime mixed research generations')
        if registry.get('automatic_promotion_allowed') is not False or active.get('automatic_promotion_allowed') is not False:raise RuntimeError('automatic promotion unexpectedly enabled')
        provenance={'schema_version':1,'research_generation':'release-corrected-v2','snapshot_id':manifest.get('snapshot_id'),'snapshot_manifest_sha256':sha(SNAP/'verification-manifest.json'),'release_calendar_sha256':manifest.get('release_calendar_sha256'),'current_state_generated_at_utc':current.get('generated_at_utc'),'registry_sha256':sha(CANON_REG),'active_edges_sha256':sha(CANON_ACTIVE),'cross_market_sha256':sha(CANON_CROSS),'detail_hashes':{p.name:sha(p) for p in sorted(CANON_DETAILS.glob('*.json'))},'historical_research_frozen':True,'automatic_promotion_allowed':False}
        (WC/'cot-research-provenance.json').write_text(json.dumps(provenance,separators=(',',':'),sort_keys=True)+'\n',encoding='utf-8')
        print(f"Installed frozen release-corrected v2 runtime · active={active.get('active_threshold_count')} · snapshot={manifest.get('snapshot_id')}")
    finally:
        for path in (inference,actor):
            try:path.unlink()
            except FileNotFoundError:pass
if __name__=='__main__':main()
