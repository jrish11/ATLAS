import unittest
from unittest.mock import patch
import atticus
class SafeMemoryExportTests(unittest.TestCase):
    def test_private_categories_and_sensitive_preferences_excluded(self):
        profile={'facts':[
            {'category':'preferences','kind':'style','value':'concise','source':'you','date':'2026-01-01'},
            {'category':'preferences','kind':'password','value':'dummy secret','source':'you'},
            {'category':'preferences','kind':'style','value':'private','source':'learned','sensitive':True},
            {'category':'school_work','kind':'homework','value':'private','source':'you'},
        ]}
        with patch.object(atticus,'me',return_value=profile): result=atticus.export_safe_preferences()
        self.assertEqual([x['value'] for x in result['facts']],['concise'])
        self.assertNotIn('dummy secret',str(result))
        self.assertNotIn('homework',str(result))
    def test_token_and_email_are_redacted(self):
        with patch.object(atticus,'me',return_value={'facts':[{'category':'preferences','kind':'style','value':'contact test@example.com abcdefghijklmnopqrstuvwxyz12345','source':'you'}]}):
            value=atticus.export_safe_preferences()['facts'][0]['value']
        self.assertNotIn('test@example.com',value);self.assertNotIn('abcdefghijklmnopqrstuvwxyz',value)
if __name__=='__main__':unittest.main()
