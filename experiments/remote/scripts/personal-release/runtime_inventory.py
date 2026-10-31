#!/usr/bin/env python3
"""Create a private review inventory; hashes alone do not prove vendor provenance."""
import argparse,importlib.util,json,os
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('release_stage',HERE/'stage.py');stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)
p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
try:
 stage.safe_tree(a.runtime)
 data=json.dumps(stage.runtime_manifest(a.runtime),sort_keys=True,indent=2)+'\n'
 fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(data);f.flush();os.fsync(f.fileno())
 print(json.dumps({'entries':len(json.loads(data)),'inventory_sha256':stage.digest(a.output),'provenance':'unverified until compared with trusted vendor artifacts'}))
except (OSError,ValueError) as error:raise SystemExit('Inventory failed: '+str(error))
