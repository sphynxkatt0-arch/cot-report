#!/usr/bin/env python3
"""Materialize the independently certified release-corrected v2 snapshot.

The full historical research was executed on an independent build plane while
GitHub-hosted Actions were unavailable. Production accepts exactly one certified
hash chain: Gate A -> B1 -> B2 -> compact active runtime -> frozen snapshot.
Every required file is then verified against the frozen snapshot manifest.
"""
from __future__ import annotations
import hashlib,json,urllib.request
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parent
SNAP=ROOT/'worldclass'/'research'/'snapshots'/'2026-08-11-release-corrected-v2'
REMOTE='https://cot-v2-final-certification.vercel.app';FINAL_URL=f'{REMOTE}/FINAL_CERTIFICATION.json';SNAP_URL=f'{REMOTE}/snapshot'
EXPECTED_GATE_A_SHA256='8025d66c8457789ceb0811bde3df4fc6878f74b4e62ec73d862b88dceb51a7e6'
EXPECTED_B1_SHA256='11be5034064b384a9e49582e69e053fc45cf0f2e99cddfa05d617f52a6f2d2ce'
EXPECTED_B2_SHA256='3abecd211ddbfd51acb858793232c73d71af0d6f5be88bf26daffdd00b92759a'
EXPECTED_ACTIVE_SHA256='e205bd07ac6e35c8abc120264e013b73656e60ba6d8d5918b6ab1e1480e923d2'
EXPECTED_SNAPSHOT_MANIFEST_SHA256='16d61f2937d98ab7fb21d96a73fbae58695f34a59d3fee726a056a8dbc154a8e'
REQUIRED_FILES=(
 'verification-manifest.json','SHA256SUMS.txt','cot-edge-registry-v2.json','cot-actor-event-summary.json',
 'cot-threshold-inference-v2.json.gz','cot-actor-event-research.json.gz','directional-validation-v2.json',
 'cot-edge-details-v2/sp500.json','cot-edge-details-v2/nq.json','cot-edge-details-v2/vix.json','cot-edge-details-v2/rty.json',
 'cot-edge-details-v2/dow.json','cot-edge-details-v2/gold.json','cot-edge-details-v2/silver.json',
)
def sha256_bytes(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def sha256(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def fetch_bytes(url:str)->bytes:
 request=urllib.request.Request(url,headers={'User-Agent':'cot-report-release-corrected-v2'})
 with urllib.request.urlopen(request,timeout=120) as response:return response.read()
def load_json_bytes(data:bytes,label:str)->dict[str,Any]:
 value=json.loads(data.decode('utf-8'))
 if not isinstance(value,dict):raise RuntimeError(f'{label} root must be an object')
 return value
def atomic_write(path:Path,data:bytes)->None:
 path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix(path.suffix+'.tmp');temp.write_bytes(data);temp.replace(path)
def verify_existing()->bool:
 manifest_path=SNAP/'verification-manifest.json'
 if not manifest_path.exists() or sha256(manifest_path)!=EXPECTED_SNAPSHOT_MANIFEST_SHA256:return False
 try:manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
 except Exception:return False
 if manifest.get('snapshot_id')!='2026-08-11-release-corrected-v2' or manifest.get('research_generation')!='release-corrected-v2':return False
 if manifest.get('gate_a_archive_sha256')!=EXPECTED_GATE_A_SHA256 or manifest.get('b1_archive_sha256')!=EXPECTED_B1_SHA256 or manifest.get('b2_directional_sha256')!=EXPECTED_B2_SHA256 or manifest.get('active_compact_sha256')!=EXPECTED_ACTIVE_SHA256:return False
 files=manifest.get('files') or {}
 for relative in REQUIRED_FILES:
  if relative in {'verification-manifest.json','SHA256SUMS.txt'}:continue
  expected=((files.get(relative) or {}).get('sha256'));path=SNAP/relative
  if not expected or not path.exists() or sha256(path)!=expected:return False
 return True
def materialize(force:bool=False)->dict[str,Any]:
 if not force and verify_existing():return json.loads((SNAP/'verification-manifest.json').read_text(encoding='utf-8'))
 final_bytes=fetch_bytes(FINAL_URL);final=load_json_bytes(final_bytes,'final certification')
 expected={'status':'PASS','research_generation':'release-corrected-v2','gate_a_archive_sha256':EXPECTED_GATE_A_SHA256,'b1_archive_sha256':EXPECTED_B1_SHA256,'b2_directional_sha256':EXPECTED_B2_SHA256,'active_compact_sha256':EXPECTED_ACTIVE_SHA256,'snapshot_manifest_sha256':EXPECTED_SNAPSHOT_MANIFEST_SHA256,'promotion_eligible':False,'production_weight_changes':False,'automatic_promotion_allowed':False}
 for key,value in expected.items():
  if final.get(key)!=value:raise RuntimeError(f'remote v2 final certification mismatch for {key}: {final.get(key)!r} != {value!r}')
 if int(final.get('active_compact_bytes') or 0)>180_000:raise RuntimeError('certified active runtime exceeds transport budget')
 manifest_bytes=fetch_bytes(f'{SNAP_URL}/verification-manifest.json');manifest_sha=sha256_bytes(manifest_bytes)
 if manifest_sha!=EXPECTED_SNAPSHOT_MANIFEST_SHA256 or final.get('snapshot_manifest_sha256')!=manifest_sha:raise RuntimeError('remote v2 snapshot-manifest hash mismatch')
 manifest=load_json_bytes(manifest_bytes,'snapshot verification manifest')
 for key,value in {'snapshot_id':'2026-08-11-release-corrected-v2','research_generation':'release-corrected-v2','gate_a_archive_sha256':EXPECTED_GATE_A_SHA256,'b1_archive_sha256':EXPECTED_B1_SHA256,'b2_directional_sha256':EXPECTED_B2_SHA256,'active_compact_sha256':EXPECTED_ACTIVE_SHA256,'promotion_eligible':False,'production_weight_changes':False,'automatic_promotion_allowed':False}.items():
  if manifest.get(key)!=value:raise RuntimeError(f'snapshot manifest mismatch for {key}')
 files=manifest.get('files') or {};staged={'verification-manifest.json':manifest_bytes,'SHA256SUMS.txt':fetch_bytes(f'{SNAP_URL}/SHA256SUMS.txt')}
 for relative in REQUIRED_FILES:
  if relative in staged:continue
  expected_sha=((files.get(relative) or {}).get('sha256'))
  if not expected_sha:raise RuntimeError(f'snapshot manifest lacks SHA256 for {relative}')
  data=fetch_bytes(f'{SNAP_URL}/{relative}');actual=sha256_bytes(data)
  if actual!=expected_sha:raise RuntimeError(f'snapshot SHA256 mismatch for {relative}: {actual} != {expected_sha}')
  staged[relative]=data
 for relative,data in staged.items():atomic_write(SNAP/relative,data)
 if not verify_existing():raise RuntimeError('materialized v2 snapshot failed local verification')
 return manifest
def main()->None:
 manifest=materialize();print(f"Release-corrected v2 snapshot materialized · snapshot={manifest['snapshot_id']} · files={len(manifest.get('files') or {})}")
if __name__=='__main__':main()
