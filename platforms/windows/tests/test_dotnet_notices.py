import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('harvest_dotnet_notices', Path(__file__).resolve().parents[1] / 'harvest-dotnet-notices.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class DotnetNoticeTests(unittest.TestCase):
    def test_manifest_records_notices_files_and_missing_packages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / 'nuget/example/1.0.0'
            package.mkdir(parents=True)
            (package / 'LICENSE.txt').write_text('example license')
            publish = root / 'publish'
            publish.mkdir()
            (publish / 'app.dll').write_bytes(b'fixture')
            assets = root / 'assets.json'
            assets.write_text(json.dumps({'libraries': {'runtimepack.Example/1.0.0': {'type': 'runtimepack'}, 'Missing/2.0.0': {'type': 'package'}}}))
            deps = root / 'app.deps.json'
            deps.write_text(json.dumps({'runtimeTarget': {'name':'win-x64'}, 'libraries': {}}))
            result = module.harvest(assets, deps, publish, root/'nuget', root/'dotnet', root/'out')
            self.assertEqual(len(result['published_files']), 1)
            self.assertEqual(len(result['packages']), 2)
            by_id = {p['id']: p for p in result['packages']}
            self.assertTrue(by_id['runtimepack.Example/1.0.0']['notice_files'])
            self.assertFalse(by_id['Missing/2.0.0']['notice_files'])
            self.assertEqual(result['runtime_target']['name'], 'win-x64')

    def test_rejects_path_traversal_package_name(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            assets = root/'assets.json'; assets.write_text(json.dumps({'libraries': {'../1.0': {'type':'package'}}}))
            deps = root/'deps.json'; deps.write_text('{}')
            with self.assertRaises(ValueError): module.harvest(assets, deps, root, root, root, root/'out')

if __name__ == '__main__': unittest.main()
