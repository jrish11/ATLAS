"""Windows CI fixture: no model, account, network, or computer actions."""
import importlib.util
import json
from pathlib import Path
import sys

source = Path(__file__).resolve().parents[1] / 'approval_client.py'
spec = importlib.util.spec_from_file_location('approval_client_fixture', source)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
args = sys.argv[1:]
read_handle = args[args.index('--approval-read-handle') + 1]
write_handle = args[args.index('--approval-write-handle') + 1]
reader, writer = module.windows_inherited_streams(read_handle, write_handle)
try:
    raw = reader.readline(module.MAX_LINE + 1)
    hello = json.loads(raw)
    client = module.ApprovalClient(reader, writer, hello['session'], hello['task'], hello['project'], hello['scope'])
    result = client.codex_handler({'id':'fixture', 'method':'item/fileChange/requestApproval',
                                   'params':{'threadId':'thread', 'turnId':'turn', 'change':'fixture'}})
    if result != 'accept': raise SystemExit('native fixture was not accepted')
finally:
    reader.close(); writer.close()
