import json, tempfile, unittest, uuid
from pathlib import Path
from unittest.mock import patch
import memory_rules_store as rules
import memory_transactions as tx
import memory_inspector as index
import memory_corrections as corrections

class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.d=str(self.root)
    def test_rule_legacy_migration_stale_reorder_and_undo_keep_uuid(self):
        path=self.root/'memory.md';legacy=b'- first\n- second\n';path.write_bytes(legacy)
        rows=[r for r in index.inspect(self.d) if r['category']=='rules'];self.assertEqual(path.read_bytes(),legacy)
        old=rows[0];result=tx.manage(self.d,'rules','edit',identifier=old['identifier'],revision=old['revision'],value='revised',confirmed=True)
        records=rules.parse(path.read_bytes());first=records[0]['id'];self.assertEqual(uuid.UUID(hex=first).version,4)
        with self.assertRaises(ValueError):tx.manage(self.d,'rules','edit',identifier=old['identifier'],revision=old['revision'],value='wrong',confirmed=True)
        current=[r for r in index.inspect(self.d) if r['category']=='rules'][0]
        self.assertEqual(current['identifier'],'rule:'+first)
        path.write_bytes(rules.encode(list(reversed(records))))
        with self.assertRaises(ValueError):tx.manage(self.d,'rules','restore',backup_id=result['backup'],confirmed=True)
        path.write_bytes(rules.encode(records));tx.manage(self.d,'rules','restore',backup_id=result['backup'],confirmed=True)
        restored=rules.parse(path.read_bytes());self.assertEqual([r['text'] for r in restored],['first','second']);self.assertEqual(restored[0]['id'],first)
        with self.assertRaises(ValueError):tx.manage(self.d,'rules','edit',identifier='rule:'+first,revision=current['revision'],value='wrong',confirmed=True)
    def test_legacy_reference_cannot_target_uuid_named_record(self):
        path=self.root/'memory.md';target=uuid.UUID('12345678-1234-4234-8234-123456789abc');other=uuid.UUID('22345678-1234-4234-8234-123456789abc')
        path.write_text('- one\n- rule:'+target.hex+'\n')
        stale=next(r for r in index.inspect(self.d) if r['category']=='rules' and r['title'].startswith('rule:'))
        with patch.object(rules.uuid, 'uuid4', side_effect=[target,other,uuid.UUID('32345678-1234-4234-8234-123456789abc')]):
            tx.manage(self.d,'rules','edit',identifier='one',revision=tx.digest('one'),value='changed',confirmed=True)
        with self.assertRaises(ValueError):tx.manage(self.d,'rules','delete',identifier=stale['identifier'],revision=stale['revision'],confirmed=True)
        self.assertEqual([r['text'] for r in rules.parse(path.read_bytes())],['changed','rule:'+target.hex])
    def test_existing_rule_writer_preserves_uuid_after_edit_and_add(self):
        import atticus
        path=self.root/'memory.md';path.write_text('- first\n- second\n')
        with patch.object(atticus, 'DIR',self.d), patch.object(atticus,'MEMORY',str(path)):
            self.assertEqual(atticus.memory_rules(),['first','second']);self.assertEqual(path.read_text(),'- first\n- second\n')
            atticus.edit_rule('first','changed');before=rules.parse(path.read_bytes());first=before[0]['id'];second=before[1]['id']
            atticus.remember_rule('third');after=rules.parse(path.read_bytes())
            self.assertEqual([r['id'] for r in after[:2]],[first,second]);self.assertEqual(atticus.memory_rules(),['changed','second','third'])
    def test_destination_writers_create_uuid_for_new_corrections(self):
        import personal_commands, memory_destinations
        personal_commands.save(self.d,'Fixture','https://example.org/old',[])
        personal_commands.save(self.d,'Fixture','https://example.org/new',[])
        rows=personal_commands.read(self.d);first=rows[0]['corrections'][0]['id'];self.assertEqual(uuid.UUID(hex=first).version,4)
        memory_destinations.manage(self.d,'edit',label='Fixture',url='https://example.org/next',aliases=[],confirmed=True,revision=memory_destinations.digest(rows[0]))
        ids=[item['id'] for item in personal_commands.read(self.d)[0]['corrections']]
        self.assertEqual(len(ids),len(set(ids)));self.assertEqual(ids[0],first)
    def test_noncanonical_legacy_rules_remain_readable_but_mutation_fails_closed(self):
        import atticus
        path=self.root/'memory.md';raw=b'- canonical\nLegacy heading\n- final without newline';path.write_bytes(raw)
        with patch.object(atticus,'DIR',self.d), patch.object(atticus,'MEMORY',str(path)):
            self.assertEqual(atticus.memory_rules(),['canonical','Legacy heading','final without newline'])
        displayed=[r for r in index.inspect(self.d) if r['category']=='rules']
        self.assertEqual([r['title'] for r in displayed],['canonical','Legacy heading','final without newline'])
        with self.assertRaises(ValueError):tx.manage(self.d,'rules','delete',identifier='canonical',revision=tx.digest('canonical'),confirmed=True)
        self.assertEqual(path.read_bytes(),raw)
    def test_rule_duplicates_unknown_format_and_uuid_collision_reject_safely(self):
        path=self.root/'memory.md';original=b'- same\n- same\n';path.write_bytes(original)
        with self.assertRaises(ValueError):tx.manage(self.d,'rules','delete',identifier='same',revision=tx.digest('same'),confirmed=True)
        self.assertEqual(path.read_bytes(),original)
        path.write_text('<!-- atticus-rule-ids:v1 -->\n- malformed unknown metadata\n');original=path.read_bytes()
        with self.assertRaises(ValueError):tx.manage(self.d,'rules','delete',identifier='x',revision='x',confirmed=True)
        self.assertEqual(path.read_bytes(),original)
        path.write_text('- first\n- second\n');original=path.read_bytes()
        with patch.object(rules.uuid,'uuid4',return_value=uuid.UUID('12345678-1234-4234-8234-123456789abc')):
            with self.assertRaises(ValueError):tx.manage(self.d,'rules','delete',identifier='first',revision=tx.digest('first'),confirmed=True)
        self.assertEqual(path.read_bytes(),original)
    def seed(self, items):
        row={'label':'Portal','url':'https://example.org/','aliases':['portal'],'browser':'Safari','source':'owner','confirmed':True,'confidence':1.0,'updated':0,'scope':'device','future':{'keep':True},'corrections':items}
        path=self.root/'destinations.json';path.write_text(json.dumps([row]));return path
    def test_corrections_migrate_preserve_unknown_fields_stale_and_undo(self):
        item={'url':'https://example.org/old','source':'owner','confirmed':True,'future':{'keep':'fixture'}}
        path=self.seed([item]);legacy=path.read_bytes();row=next(r for r in index.inspect(self.d) if r['category']=='corrections');self.assertEqual(path.read_bytes(),legacy)
        with self.assertRaises(ValueError):corrections.manage(self.d,'edit',identifier=row['identifier'],revision=row['revision'],value='https://example.org/new')
        self.assertEqual(path.read_bytes(),legacy)
        result=corrections.manage(self.d,'edit',identifier=row['identifier'],revision=row['revision'],value='https://example.org/new',confirmed=True)
        data=json.loads(path.read_text());new=data[0]['corrections'][0];identifier=new['id'];self.assertEqual(uuid.UUID(hex=identifier).version,4);self.assertEqual(new['future'],item['future']);self.assertTrue(data[0]['future']['keep'])
        with self.assertRaises(ValueError):corrections.manage(self.d,'delete',identifier=row['identifier'],revision=row['revision'],confirmed=True)
        after=path.read_bytes();data[0]['other']='change';path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):corrections.manage(self.d,'restore',backup_id=result['backup'],confirmed=True)
        path.write_bytes(after);corrections.manage(self.d,'restore',backup_id=result['backup'],confirmed=True)
        restored=json.loads(path.read_text())[0]['corrections'][0];self.assertEqual(restored['id'],identifier);self.assertEqual(restored['url'],item['url']);self.assertEqual(restored['future'],item['future'])
    def test_correction_duplicates_and_collision_never_mutate(self):
        item={'url':'https://example.org/old','source':'owner','confirmed':True}
        path=self.seed([item,item]);original=path.read_bytes();row=next(r for r in index.inspect(self.d) if r['category']=='corrections')
        with self.assertRaises(ValueError):corrections.manage(self.d,'delete',identifier=row['identifier'],revision=row['revision'],confirmed=True)
        self.assertEqual(path.read_bytes(),original)
        path=self.seed([item,dict(item,url='https://example.org/other')]);original=path.read_bytes();row=next(r for r in index.inspect(self.d) if r['category']=='corrections')
        with patch.object(corrections.uuid,'uuid4',return_value=uuid.UUID('12345678-1234-4234-8234-123456789abc')):
            with self.assertRaises(ValueError):corrections.manage(self.d,'delete',identifier=row['identifier'],revision=row['revision'],confirmed=True)
        self.assertEqual(path.read_bytes(),original)
    def test_identical_corrections_are_distinct_after_other_record_migrates(self):
        item={'url':'https://example.org/old','source':'owner','confirmed':True}
        path=self.seed([item,item,dict(item,url='https://example.org/unique')])
        rows=[r for r in index.inspect(self.d) if r['category']=='corrections'];unique=next(r for r in rows if r['editValue'].endswith('/unique'))
        corrections.manage(self.d,'edit',identifier=unique['identifier'],revision=unique['revision'],value='https://example.org/new',confirmed=True)
        data=json.loads(path.read_text());items=data[0]['corrections'];self.assertNotEqual(items[0]['id'],items[1]['id'])
        corrections.manage(self.d,'delete',identifier='correction:'+items[0]['id'],revision=corrections.digest(items[0]),confirmed=True)
        remaining=json.loads(path.read_text())[0]['corrections'];self.assertEqual(remaining[0]['id'],items[1]['id'])
    def test_unsupported_or_missing_url_can_be_forgotten_without_exposing_it(self):
        item={'url':'https://example.org/?token=fixture-secret','source':'owner','unknown':{'keep':True}}
        path=self.seed([item]);row=next(r for r in index.inspect(self.d) if r['category']=='corrections')
        self.assertEqual(row['editValue'],'');self.assertNotIn('fixture-secret',json.dumps(row))
        result=corrections.manage(self.d,'delete',identifier=row['identifier'],revision=row['revision'],confirmed=True)
        self.assertEqual(result['status'],'deleted');corrections.manage(self.d,'restore',backup_id=result['backup'],confirmed=True)
        self.assertEqual(json.loads(path.read_text())[0]['corrections'][0]['unknown'],item['unknown'])
    def test_destination_writer_rejects_correction_uuid_collision(self):
        import personal_commands, memory_destinations
        item={'id':'12345678123442348234123456789abc','url':'https://example.org/old','source':'owner'}
        path=self.seed([item]);data=json.loads(path.read_text());data[0].pop('future');path.write_text(json.dumps(data))
        before=path.read_bytes();row=personal_commands.read(self.d)[0]
        with patch.object(personal_commands.uuid,'uuid4',return_value=uuid.UUID(hex=item['id'])):
            with self.assertRaises(ValueError):personal_commands.save(self.d,'Portal','https://example.org/new',[])
            with self.assertRaises(ValueError):memory_destinations.manage(self.d,'edit',label='Portal',url='https://example.org/new',aliases=[],revision=memory_destinations.digest(row),confirmed=True)
        self.assertEqual(path.read_bytes(),before)
        data=json.loads(path.read_text());data[0]['future']={'keep':True};path.write_text(json.dumps(data))
        personal_commands.save(self.d,'Portal','https://example.org/new',[])
        self.assertEqual(json.loads(path.read_text())[0]['future'], {'keep':True})
    def test_correction_uuid_survives_reordering(self):
        item={'url':'https://example.org/old','source':'owner','confirmed':True}
        path=self.seed([item,dict(item,url='https://example.org/other')]);row=next(r for r in index.inspect(self.d) if r['category']=='corrections')
        corrections.manage(self.d,'edit',identifier=row['identifier'],revision=row['revision'],value='https://example.org/new',confirmed=True)
        data=json.loads(path.read_text());selected=data[0]['corrections'][0];data[0]['corrections'].reverse();path.write_text(json.dumps(data))
        result=corrections.manage(self.d,'delete',identifier='correction:'+selected['id'],revision=corrections.digest(selected),confirmed=True)
        self.assertEqual(result['status'],'deleted');self.assertEqual(len(json.loads(path.read_text())[0]['corrections']),1)

if __name__=='__main__':unittest.main()
