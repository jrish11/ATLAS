import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import atticus


class SkillsAtomicWriteTests(unittest.TestCase):
    def test_temporary_file_uses_destination_directory_and_is_replaced(self):
        with tempfile.TemporaryDirectory() as root:
            profile = Path(root) / 'profile'
            target_dir = Path(root) / 'destination'
            target = target_dir / 'skills.json'
            original_replace = os.replace
            recorded = []
            def replace(source, destination):
                recorded.append((Path(source), Path(destination)))
                self.assertEqual(Path(source).parent.resolve(), target_dir.resolve())
                original_replace(source, destination)
            with patch.object(atticus, 'DIR', str(profile)), patch.object(atticus, 'SKILLS', str(target)), patch.object(atticus.os, 'replace', side_effect=replace):
                atticus.save_skills({'example': {'mine': True, 'cmds': ['open'], 'reply': 'ok'}})
            self.assertEqual(len(recorded), 1)
            self.assertEqual(json.loads(target.read_text())['example']['reply'], 'ok')
            self.assertFalse(recorded[0][0].exists())

    def test_failed_replace_preserves_previous_file_and_removes_temp(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / 'skills.json'
            target.write_text('{"original": true}', encoding='utf-8')
            with patch.object(atticus, 'DIR', str(Path(root) / 'elsewhere')), patch.object(atticus, 'SKILLS', str(target)), patch.object(atticus.os, 'replace', side_effect=OSError('simulated failure')):
                with self.assertRaises(OSError): atticus.save_skills({'new': {'mine': True}})
            self.assertEqual(json.loads(target.read_text()), {'original': True})
            self.assertEqual(sorted(p.name for p in Path(root).iterdir()), ['skills.json'])

if __name__ == '__main__': unittest.main()
