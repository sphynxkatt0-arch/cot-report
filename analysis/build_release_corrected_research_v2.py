#!/usr/bin/env python3
"""Build and validate the complete release-corrected COT research generation."""
from __future__ import annotations
import hashlib,json,subprocess,sys
from datetime import UTC,datetime
from pathlib import Path

import build_worldclass_research_artifacts as research
from cftc_release_calendar import calendar_hash

ROOT=Path(__file__).resolve().parent
MANIFEST=ROOT/'worldclass'/'research'/'release-corrected-v2-build-manifest.json'
STEPS=(
 'build_worldclass_backtest.py',
 'build_worldclass_regime_backtest.py',
 'evaluate_analog_robustness_v2.py',
 'evaluate_financial_actor_weights_v2.py',
 'evaluate_disaggregated_weights_v2.py',
 'evaluate_actor_weights_walkforward_v2.py',
 'build_cot_actor_event_research_release_corrected.py',
 'evaluate_cot_threshold_inference_v2.py',
 'evaluate_cot_actor_predictive_power_v2.py',
 'evaluate_cot_raw_position_oi_predictive_power_v2.py',
 'validate_directional_cot_v2.py',
 'build_cot_current_state.py',
 'build_cot_edge_details_v2.py',
 'build_cot_edge_registry_v2.py',
 'build_cot_active_edges_v2.py',
 'build_cot_cross_market_runtime_v2.py',
 'build_backtest_correctness_report.py',
 'validate_cot_research_correctness.py',
)
OUTPUTS=(
 'worldclass/backtest.json','worldclass/regime_backtest.json','worldclass/research/analog-robustness.json',
 'worldclass/financial-weight-study.json','worldclass/metal-weight-study.json','worldclass/research/actor-weight-walkforward-v2.json',
 'worldclass/research/cot-actor-event-research.json','worldclass/research/cot-actor-event-summary.json',
 'worldclass/research/cot-threshold-inference-v2.json','worldclass/research/cot-threshold-inference-v2-summary.json',
 'worldclass/research/cot-actor-predictive-power.json','worldclass/research/cot-raw-position-oi-predictive-power.json',
 'worldclass/research/directional-validation-v2.json','worldclass/cot-current-state.json','worldclass/research/cot-position-oi-audit-v2.json',
 'worldclass/cot-edge-registry-v2.json','worldclass/cot-active-edges-v2.json','worldclass/cot-cross-market-v2.json',
 'worldclass/research/BACKTEST_CORRECTNESS_REPORT.md',
)
def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def run(script:str)->None:
    print(f'\n=== {script} ===',flush=True);subprocess.run([sys.executable,str(ROOT/script)],cwd=ROOT,check=True)
def main()->None:
    research.WORLDCLASS.mkdir(parents=True,exist_ok=True)
    base=research.build_research_base();metals=research.ensure_full_metals();research.atomic_write(research.WORLDCLASS/'base.json',base);research.atomic_write(research.WORLDCLASS/'metals.json',metals)
    if not research.metals_history_is_full(metals):raise RuntimeError('full metals history contract failed')
    for script in STEPS:run(script)
    files={}
    for relative in OUTPUTS:
        path=ROOT/relative
        if not path.is_file() or path.stat().st_size<=0:raise RuntimeError(f'missing v2 output: {relative}')
        files[relative]={'bytes':path.stat().st_size,'sha256':sha(path)}
    details={}
    detail_dir=ROOT/'worldclass'/'cot-edge-details-v2'
    for path in sorted(detail_dir.glob('*.json')):details[str(path.relative_to(ROOT))]={'bytes':path.stat().st_size,'sha256':sha(path)}
    if len(details)!=7:raise RuntimeError(f'expected seven v2 detail payloads, got {len(details)}')
    payload={'schema_version':1,'research_generation':'release-corrected-v2','information_contract_version':'cftc-public-availability-v2','release_calendar_hash':calendar_hash(),'built_at_utc':datetime.now(UTC).isoformat(timespec='seconds').replace('+00:00','Z'),'steps':list(STEPS),'files':files,'detail_files':details,'production_model_changed':False,'automatic_promotion_allowed':False,'status':'VALIDATED_BUILD'}
    MANIFEST.parent.mkdir(parents=True,exist_ok=True);MANIFEST.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(f'\nRelease-corrected v2 build PASS · outputs={len(files)+len(details)} · manifest={MANIFEST}')
if __name__=='__main__':main()
