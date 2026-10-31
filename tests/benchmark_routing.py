"""Offline baseline/fork routing fixtures. No browser, speech, network, or model calls."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import personal_commands


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def measure(fn, iterations):
    values=[]; success=0
    for _ in range(iterations):
        start=time.perf_counter_ns(); result=fn(); values.append((time.perf_counter_ns()-start)/1e6)
        success += bool(result)
    values.sort()
    return {'n':iterations,'median_ms':round(statistics.median(values),4),
            'p95_ms':round(values[max(0, (95*iterations+99)//100-1)],4), 'recognized':success}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--iterations',type=int,default=1000); args=parser.parse_args()
    if not 1 <= args.iterations <= 100000: parser.error('iterations must be between 1 and 100000')
    with tempfile.TemporaryDirectory(prefix='atticus-routing-bench-') as tmp:
        os.environ['ATTICUS_DIR']=tmp; os.environ['ATTICUS_POSTHOG_KEY']=''
        source=subprocess.run(['git','show','upstream/main:atticus.py'],cwd=ROOT,capture_output=True,text=True,check=True).stdout
        baseline=Path(tmp,'upstream.py');baseline.write_text(source)
        original=load('atticus_benchmark_original',baseline); fork=load('atticus_benchmark_fork',ROOT/'atticus.py')
        personal_commands.save(tmp,'Schoology','https://school.example/',[])
        personal_commands.save(tmp,'Lovable','https://lovable.example/',[])
        results={}
        for command in ('open schoology','go to lovable'):
            with patch.object(original,'fast_hands',return_value=None), patch.object(original,'skills',return_value={}), \
                 patch.object(original,'app_named',return_value=None), patch.object(original,'app_heard',return_value=None), \
                 patch.object(fork,'fast_hands',return_value=None), patch.object(fork,'skills',return_value={}), \
                 patch.object(personal_commands,'open_destination',return_value='fixture action requested'):
                results[command]={'upstream':measure(lambda: original.fast(command),args.iterations),
                                  'fork':measure(lambda: fork.fast(command),args.iterations)}
        print(json.dumps({'kind':'offline_fixture','note':'Upstream has no configured saved destination; fork has a confirmed fake destination. Browser action is mocked. No speech, process startup, page loading, fallback, model calls or network are measured.', 'scenarios':results},indent=2))

if __name__=='__main__':main()
