import json
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from claude_code import ClaudeCodeTranslator
from core import ReviewError
from translation import Translators, generate_proposals
from workspace import Workspace
from test_locales import locale_download

# Fake CLI: records its arguments and stdin, then answers like `claude -p --output-format json`.
FAKE = textwrap.dedent('''\
    #!{python}
    import json, os, sys
    log = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'calls.jsonl')
    if sys.argv[1:3] == ['auth', 'status']:
        print(json.dumps({{'loggedIn': True, 'subscriptionType': 'max', 'email': 'private@example.com'}}))
        sys.exit(0)
    data = json.loads(sys.stdin.read())
    with open(log, 'a') as f:
        f.write(json.dumps({{'argv': sys.argv[1:], 'input': data, 'cwd': os.getcwd()}}) + '\\n')
    if os.environ.get('FAKE_CLAUDE_FAIL'):
        print(json.dumps({{'type': 'result', 'subtype': 'success', 'is_error': True, 'result': 'Not logged in'}}))
        sys.exit(1)
    entries = [{{'key': e['key'], 'target': ['Traducción'] * e['target_count'], 'note': ''}} for e in data['requested_entries']]
    print(json.dumps({{'type': 'result', 'subtype': 'success', 'is_error': False, 'structured_output': {{'entries': entries}}}}))
''')


class ClaudeCodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.bin = root / 'claude';self.bin.write_text(FAKE.format(python=sys.executable));self.bin.chmod(0o700)
        self.claude = ClaudeCodeTranslator(str(self.bin))
        client = Mock();client.env_path = root / '.env';client.download.return_value = locale_download()
        self.w = Workspace(root / 'data', client);self.w.sync('locales')

    def calls(self):
        return [json.loads(line) for line in (self.bin.parent / 'calls.jsonl').read_text().splitlines()]

    def test_generation_through_cli_restores_keys_and_never_approves(self):
        state = generate_proposals(self.w, Translators({'claude-code': self.claude}), 'claude-code', 'sonnet')
        self.assertTrue(state['workspace']['ready']);self.assertEqual(state['counts']['accepted'], 0)
        call = self.calls()[0]
        argv = call['argv']
        self.assertEqual(argv[argv.index('--tools') + 1], '')
        self.assertEqual(argv[argv.index('--setting-sources') + 1], '')
        self.assertIn('--no-session-persistence', argv);self.assertIn('--strict-mcp-config', argv)
        self.assertEqual([e['key'] for e in call['input']['requested_entries']], ['1', '2'])
        self.assertNotEqual(Path(call['cwd']).resolve(), Path.cwd().resolve())

    def test_cli_error_raises_without_writing_proposals(self):
        import os
        os.environ['FAKE_CLAUDE_FAIL'] = '1';self.addCleanup(os.environ.pop, 'FAKE_CLAUDE_FAIL')
        with self.assertRaisesRegex(ReviewError, 'Not logged in'):
            generate_proposals(self.w, Translators({'claude-code': self.claude}), 'claude-code', 'sonnet')
        self.assertFalse((self.w.directory(self.w.active_id) / 'proposals.json').exists())

    def test_status_omits_account_identity_and_missing_cli_is_unavailable(self):
        self.assertEqual(self.claude.status(), {'available': True, 'logged_in': True, 'subscription': 'max'})
        self.assertFalse(ClaudeCodeTranslator('definitely-not-installed-claude').status()['available'])

    def test_unknown_model_and_provider_are_rejected(self):
        with self.assertRaises(ReviewError):self.claude.propose('claude-code', 'gpt-5', {'requested_entries': []})
        with self.assertRaises(ReviewError):Translators({}).credential('claude-code')


if __name__ == '__main__':
    unittest.main()
