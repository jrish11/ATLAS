import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import atticus
import personal_commands

class ResidentCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.patch=patch.object(atticus,'DIR',self.tmp.name);self.patch.start();self.addCleanup(self.patch.stop)
        self.events=[]; self.manager=atticus.Agents(emit=self.events.append);self.addCleanup(self.manager.close)
        personal_commands.save(self.tmp.name,'Fixture','https://fixture.example/', ['fixture portal'])

    def until(self, pred):
        end=time.monotonic()+3
        while time.monotonic()<end:
            if pred():return
            time.sleep(.01)
        self.fail('resident command timed out')

    def test_confirmed_destination_executes_once_and_records_truthfully(self):
        identifier='a'*32
        with patch.dict(os.environ,{},clear=True), patch.object(personal_commands,'open_destination',return_value='Requested Fixture in Safari; check that the page loaded.') as action:
            request={'action':'personal-open','id':identifier,'text':'open fixture portal','confirmed':True}
            self.manager.command(request);self.until(lambda:bool(self.events))
            self.manager.command(request)
            self.assertEqual(action.call_count,1)
        self.assertEqual(self.events[-1]['reply'],'Requested Fixture in Safari; check that the page loaded.')
        record=json.loads(Path(self.tmp.name,'log.jsonl').read_text().splitlines()[-1])
        self.assertEqual((record['path'],record['outcome'],record['model']),('personal-resident','unverified','instant'))

    def test_inflight_duplicate_is_not_executed_twice(self):
        entered, release = threading.Event(), threading.Event()
        def action(row):
            entered.set(); release.wait(2)
            return 'Switched to Fixture in Safari.'
        request={'action':'personal-open','id':'e'*32,'text':'open fixture','confirmed':True}
        with patch.dict(os.environ,{},clear=True), patch.object(personal_commands,'open_destination',side_effect=action) as run:
            self.manager.command(request)
            self.assertTrue(entered.wait(2))
            self.manager.command(request)
            release.set(); self.until(lambda:bool(self.events))
            self.assertEqual(run.call_count,1)

    def test_changed_binding_is_not_opened(self):
        row=personal_commands.resolve(self.tmp.name,'open fixture')
        with patch.dict(os.environ,{},clear=True), patch.object(personal_commands,'resolve',side_effect=[row, None]), patch.object(personal_commands,'open_destination') as action:
            self.manager.command({'action':'personal-open','id':'f'*32,'text':'open fixture','confirmed':True})
            self.until(lambda:bool(self.events))
            action.assert_not_called()
        self.assertIn('changed',self.events[-1]['reply'])

    def test_missing_request_cache_is_bounded(self):
        with patch.dict(os.environ,{},clear=True):
            for i in range(150):
                self.manager.command({'action':'personal-open','id':format(i,'032x'),'text':'open unknown','confirmed':True})
        self.assertLessEqual(len(self.manager.personal_requests),100)

    def test_unconfirmed_agent_and_unknown_requests_do_not_act(self):
        with patch.dict(os.environ,{},clear=True),patch.object(personal_commands,'open_destination') as action:
            self.manager.command({'action':'personal-open','id':'b'*32,'text':'open fixture','confirmed':False})
            with patch.dict(os.environ,{'ATTICUS_AGENT':'1'}):
                self.manager.command({'action':'personal-open','id':'c'*32,'text':'open fixture','confirmed':True})
            self.manager.command({'action':'personal-open','id':'d'*32,'text':'open unknown fixture','confirmed':True})
            action.assert_not_called()
        self.assertEqual(self.events[-1]['matched'],False)

if __name__=='__main__':unittest.main()
