import unittest
from codex_account import check_account, AccountProbeError


class FakeTransport:
    def __init__(self, account=None, error=False, unexpected=False):
        self.account, self.error, self.unexpected = account, error, unexpected
        self.sent, self.pending, self.closed = [], [], False

    def send(self, message):
        self.sent.append(message)
        method = message.get('method')
        if method == 'initialize':
            self.pending.append({'id': message['id'], 'result': {}})
        elif method == 'account/read':
            if self.unexpected:
                self.pending.append({'id': 'request-1', 'method': 'item/commandExecution/requestApproval', 'params': {}})
            self.pending.append({'id': message['id'], **({'error': {}} if self.error else {'result': {'account': self.account}})})

    def receive(self, timeout):
        if not self.pending: raise AccountProbeError('timeout')
        return self.pending.pop(0)

    def close(self): self.closed = True


class CodexAccountTests(unittest.TestCase):
    def run_probe(self, *args, **kwargs):
        fake = FakeTransport(*args, **kwargs)
        result = check_account(lambda: fake)
        self.assertTrue(fake.closed)
        self.assertEqual([m.get('method') for m in fake.sent if m.get('method')], ['initialize', 'initialized', 'account/read'])
        self.assertEqual(fake.sent[-1].get('params'), {'refreshToken': False})
        return result, fake

    def test_chatgpt_redacts_account_details(self):
        result, _ = self.run_probe({'type': 'chatgpt', 'email': 'private@example.test'})
        self.assertEqual(result['status'], 'chatgpt')
        self.assertNotIn('private@example.test', str(result))

    def test_signed_out_api_and_unknown(self):
        for account, status in [(None, 'signed_out'), ({'type': 'apiKey'}, 'api_key'), ({'type': 'other'}, 'unknown')]:
            with self.subTest(status=status): self.assertEqual(self.run_probe(account)[0]['status'], status)

    def test_server_error_does_not_leak(self):
        result, _ = self.run_probe(error=True)
        self.assertEqual(result['status'], 'unavailable')

    def test_unexpected_server_request_rejected(self):
        fake = FakeTransport({'type': 'chatgpt'}, unexpected=True)
        result = check_account(lambda: fake)
        self.assertEqual(result['status'], 'chatgpt')
        self.assertEqual(fake.sent[-1]['error']['code'], -32601)
        self.assertTrue(fake.closed)

    def test_transport_failure(self):
        def fail(): raise OSError('private')
        self.assertEqual(check_account(fail)['status'], 'unavailable')

if __name__ == '__main__': unittest.main()
