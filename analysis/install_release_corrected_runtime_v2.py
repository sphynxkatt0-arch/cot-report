#!/usr/bin/env python3
"""Install the certified release-corrected v2 research into production runtime."""
from __future__ import annotations
import gzip,hashlib,json,shutil,subprocess,sys
from pathlib import Path
from typing import Any
import fetch_release_corrected_snapshot_v2 as remote_snapshot
ROOT=Path(__file__).resolve().parent;WC=ROOT/'worldclass';RESEARCH=WC/'research';SNAP=RESEARCH/'snapshots'/'2026-08-11-release-corrected-v2';V2_REG=WC/'cot-edge-registry-v2.json';CANON_REG=WC/'cot-edge-registry.json';CANON_ACTIVE=WC/'cot-active-edges.json';CANON_CROSS=WC/'cot-cross-market.json';CANON_DETAILS=WC/'cot-edge-details';COPY_JS=WC/'cot-intelligence-v2-copy.js';HTML=ROOT/'worldclass_dashboard.html'
def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def short_sha(path:Path)->str:return sha(path)[:12]
def load(path:Path)->dict[str,Any]:
 p=json.loads(path.read_text(encoding='utf-8'))
 if not isinstance(p,dict):raise RuntimeError(path)
 return p
def atomic_copy(src:Path,dst:Path)->None:
 dst.parent.mkdir(parents=True,exist_ok=True);tmp=dst.with_suffix(dst.suffix+'.tmp');shutil.copyfile(src,tmp);tmp.replace(dst)
def verify_snapshot()->dict[str,Any]:
 remote_snapshot.materialize();manifest=load(SNAP/'verification-manifest.json')
 if manifest.get('research_generation')!='release-corrected-v2' or manifest.get('promotion_eligible') is not False or manifest.get('automatic_promotion_allowed') is not False:raise RuntimeError('invalid frozen v2 manifest')
 files=manifest.get('files') or {}
 for relative in remote_snapshot.REQUIRED_FILES:
  if relative in {'verification-manifest.json','SHA256SUMS.txt'}:continue
  path=SNAP/relative;expected=((files.get(relative) or {}).get('sha256'))
  if not path.is_file() or not expected or sha(path)!=expected:raise RuntimeError(f'frozen snapshot checksum mismatch: {relative}')
 return manifest
def extract_gz(src:Path,dst:Path)->None:
 dst.parent.mkdir(parents=True,exist_ok=True);tmp=dst.with_suffix(dst.suffix+'.tmp')
 with gzip.open(src,'rb') as inp,tmp.open('wb') as out:shutil.copyfileobj(inp,out)
 tmp.replace(dst)
def run(script:str)->None:subprocess.run([sys.executable,str(ROOT/script)],cwd=ROOT,check=True)
def install_copy_asset()->None:
 if not COPY_JS.exists() or not HTML.exists():return
 text=HTML.read_text(encoding='utf-8');text='\n'.join(line for line in text.splitlines() if 'data-cot-intelligence-asset="v2-copy-js"' not in line)+('\n' if text.endswith('\n') else '')
 tag=f'<script defer src="worldclass/cot-intelligence-v2-copy.js?v={short_sha(COPY_JS)}" data-cot-intelligence-asset="v2-copy-js"></script>'
 if '</body>' not in text:raise RuntimeError('dashboard HTML missing </body>')
 HTML.write_text(text.replace('</body>',f'  {tag}\n</body>',1),encoding='utf-8')
def main()->None:
 manifest=verify_snapshot();atomic_copy(SNAP/'cot-edge-registry-v2.json',V2_REG);atomic_copy(V2_REG,CANON_REG)
 if CANON_DETAILS.exists():shutil.rmtree(CANON_DETAILS)
 CANON_DETAILS.mkdir(parents=True,exist_ok=True)
 for src in sorted((SNAP/'cot-edge-details-v2').glob('*.json')):atomic_copy(src,CANON_DETAILS/src.name)
 inference=RESEARCH/'cot-threshold-inference-v2.json';actor=RESEARCH/'cot-actor-event-research.json';summary=RESEARCH/'cot-actor-event-summary.json';extract_gz(SNAP/'cot-threshold-inference-v2.json.gz',inference);extract_gz(SNAP/'cot-actor-event-research.json.gz',actor);atomic_copy(SNAP/'cot-actor-event-summary.json',summary)
 try:
  run('build_cot_current_state.py');run('build_cot_active_edges_v2.py');run('build_cot_cross_market_runtime_v2.py');atomic_copy(WC/'cot-active-edges-v2.json',CANON_ACTIVE);atomic_copy(WC/'cot-cross-market-v2.json',CANON_CROSS);current=load(WC/'cot-current-state.json');active=load(CANON_ACTIVE);registry=load(CANON_REG);cross=load(CANON_CROSS)
  if registry.get('research_generation')!='release-corrected-v2' or active.get('research_generation')!='release-corrected-v2' or cross.get('research_generation')!='release-corrected-v2':raise RuntimeError('canonical runtime mixed research generations')
  if registry.get('automatic_promotion_allowed') is not False or active.get('automatic_promotion_allowed') is not False:raise RuntimeError('automatic promotion unexpectedly enabled')
  if active.get('schema_version')!=5 or CANON_ACTIVE.stat().st_size>180_000:raise RuntimeError('canonical active-edge runtime violates compact schema/budget')
  provenance={'schema_version':2,'research_generation':'release-corrected-v2','snapshot_id':manifest.get('snapshot_id'),'snapshot_manifest_sha256':sha(SNAP/'verification-manifest.json'),'gate_a_archive_sha256':manifest.get('gate_a_archive_sha256'),'b1_archive_sha256':manifest.get('b1_archive_sha256'),'b2_directional_sha256':manifest.get('b2_directional_sha256'),'active_compact_certified_sha256':manifest.get('active_compact_sha256'),'current_state_generated_at_utc':current.get('generated_at_utc'),'registry_sha256':sha(CANON_REG),'active_edges_sha256':sha(CANON_ACTIVE),'active_edges_bytes':CANON_ACTIVE.stat().st_size,'cross_market_sha256':sha(CANON_CROSS),'detail_hashes':{p.name:sha(p) for p in sorted(CANON_DETAILS.glob('*.json'))},'historical_research_frozen':True,'automatic_promotion_allowed':False};(WC/'cot-research-provenance.json').write_text(json.dumps(provenance,separators=(',',':'),sort_keys=True)+'\n',encoding='utf-8');install_copy_asset();print(f"Installed certified release-corrected v2 runtime · active={active.get('active_threshold_count')} · bytes={CANON_ACTIVE.stat().st_size} · snapshot={manifest.get('snapshot_id')}")
 finally:
  for path in (inference,actor):
   try:path.unlink()
   except FileNotFoundError:pass
if __name__=='__main__':main()
