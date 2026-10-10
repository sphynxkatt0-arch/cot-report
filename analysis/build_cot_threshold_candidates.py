"""Materialize frozen threshold profiles for runtime current-report selection."""
import gzip
import json
from collections import defaultdict
from pathlib import Path
from build_cot_active_edges_v2 import metric_payload, ACTIVE_HORIZONS

ROOT = Path(__file__).resolve().parent
SNAP = ROOT / 'worldclass/research/snapshots/2026-08-11-release-corrected-v2'


def build():
    with gzip.open(SNAP / 'cot-threshold-inference-v2.json.gz', 'rt', encoding='utf-8') as stream:
        inference = json.load(stream)
    with gzip.open(SNAP / 'cot-actor-event-research.json.gz', 'rt', encoding='utf-8') as stream:
        actor = json.load(stream)
    registry = json.loads((SNAP / 'cot-edge-registry-v2.json').read_text(encoding='utf-8'))
    assert inference['research_generation'] == actor['research_generation'] == registry['research_generation'] == 'release-corrected-v2'
    metrics = defaultdict(dict)
    for row in inference['metrics']:
        metrics[(row['series'], row['direction'], int(row['threshold']))][row['horizon']] = row
    candidates = {}
    for edge in registry['threshold_edges'].values():
        series, direction, threshold = edge['series'], edge['direction'], int(edge['threshold'])
        row = candidates.setdefault(f'{series}:{direction}', {
            'series': series, 'dataset': edge['dataset'], 'market': edge['market'],
            'actor_role': edge['actor_role'], 'direction': direction, 'threshold_profiles': {}})
        evidence = metrics[(series, direction, threshold)]
        row['threshold_profiles'][str(threshold)] = [
            metric_payload(actor, series, direction, threshold, horizon, evidence[horizon])
            for horizon in ACTIVE_HORIZONS if horizon in evidence]
    output = {'schema_version': 1, 'research_generation': 'release-corrected-v2',
              'historical_research_frozen': True, 'candidates': list(candidates.values())}
    dest = ROOT / 'worldclass/cot-threshold-candidates.json'
    dest.write_text(json.dumps(output, separators=(',', ':'), sort_keys=True) + '\n', encoding='utf-8')
    print(f'Saved {dest.name}: {len(candidates)} candidates, {dest.stat().st_size} bytes')


if __name__ == '__main__':
    build()
