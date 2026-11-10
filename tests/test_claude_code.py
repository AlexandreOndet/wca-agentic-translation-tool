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
from server import ai_translators
from translation import generate_proposals
from workspace import Workspace
from test_locales import locale_download

# Fake CLI: records its arguments and stdin, then answers like `claude -p --output-format json`.
FAKE = textwrap.dedent('''\
    #!{python}
    import json, os, sys
    log = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'calls.jsonl')
    mode = {mode!r}
    if sys.argv[1:3] == ['auth', 'status']:
        if mode == 'old':
            print('error: unknown command auth', file=sys.stderr)
            sys.exit(1)
        print(json.dumps({{'loggedIn': True, 'subscriptionType': 'max', 'email': 'private@example.com'}} if mode == 'ok' else ['unexpected']))
        sys.exit(0)
    data = json.loads(sys.stdin.read())
    with open(log, 'a') as f:
        f.write(json.dumps({{'argv': sys.argv[1:], 'input': data, 'cwd': os.getcwd()}}) + '\\n')
    if mode == 'logged-out':
        print(json.dumps({{'type': 'result', 'subtype': 'success', 'is_error': True, 'result': 'Not logged in'}}))
        sys.exit(1)
    if mode == 'crash':
        print('Error: model overloaded', file=sys.stderr)
        sys.exit(2)
    if mode == 'wrong-shape':
        print(json.dumps({{'type': 'result', 'subtype': 'success', 'is_error': False, 'structured_output': 'plain text'}}))
        sys.exit(0)
    entries = [{{'key': e['key'], 'target': ['Traducción'] * e['target_count'], 'note': ''}} for e in data['requested_entries']]
    print(json.dumps({{'type': 'result', 'subtype': 'success', 'is_error': False, 'structured_output': {{'entries': entries}}}}))
''')


class ClaudeCodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.claude = self.fake('ok')
        client = Mock();client.env_path = self.root / '.env';client.download.return_value = locale_download()
        self.w = Workspace(self.root / 'data', client);self.w.sync('locales')

    def fake(self, mode):
        folder = self.root / mode;folder.mkdir()
        binary = folder / 'claude';binary.write_text(FAKE.format(python=sys.executable, mode=mode));binary.chmod(0o700)
        return ClaudeCodeTranslator(str(binary))

    def generate(self, claude):
        return generate_proposals(self.w, ai_translators(Mock(), Mock(), claude), 'claude-code', 'sonnet')

    def test_generation_through_cli_restores_keys_and_never_approves(self):
        state = self.generate(self.claude)
        self.assertTrue(state['workspace']['ready']);self.assertEqual(state['counts']['accepted'], 0)
        call = json.loads((self.root / 'ok' / 'calls.jsonl').read_text().splitlines()[0])
        argv = call['argv']
        self.assertEqual(argv[argv.index('--tools') + 1], '')
        self.assertEqual(argv[argv.index('--setting-sources') + 1], '')
        self.assertIn('--no-session-persistence', argv);self.assertIn('--strict-mcp-config', argv)
        self.assertEqual([e['key'] for e in call['input']['requested_entries']], ['1', '2'])
        self.assertNotEqual(Path(call['cwd']).resolve(), Path.cwd().resolve())

    def test_cli_error_raises_without_writing_proposals(self):
        with self.assertRaisesRegex(ReviewError, r'Not logged in.*claude auth login'):
            self.generate(self.fake('logged-out'))
        self.assertFalse((self.w.directory(self.w.active_id) / 'proposals.json').exists())

    def test_cli_crash_reports_stderr_and_exit_code_without_login_hint(self):
        with self.assertRaises(ReviewError) as caught:
            self.generate(self.fake('crash'))
        self.assertIn('exit 2', str(caught.exception));self.assertIn('model overloaded', str(caught.exception))
        self.assertNotIn('auth login', str(caught.exception))

    def test_structured_output_of_the_wrong_type_is_rejected(self):
        with self.assertRaisesRegex(ReviewError, 'list of proposals'):
            self.fake('wrong-shape').propose('sonnet', {})

    def test_status_omits_account_identity(self):
        self.assertEqual(self.claude.status(), {'available': True, 'logged_in': True, 'subscription': 'max'})

    def test_status_missing_cli_is_unavailable_but_old_or_odd_cli_is_installed(self):
        self.assertFalse(ClaudeCodeTranslator('definitely-not-installed-claude').status()['available'])
        for mode in ('old', 'odd'):
            self.assertEqual(self.fake(mode).status(), {'available': True, 'logged_in': False, 'subscription': ''})

    def test_unknown_model_is_rejected(self):
        with self.assertRaises(ReviewError):self.claude.propose('gpt-5', {'requested_entries': []})

    def test_unknown_provider_is_rejected(self):
        with self.assertRaisesRegex(ReviewError, 'Choose an AI connection'):
            generate_proposals(self.w, ai_translators(Mock(), Mock(), self.claude), 'gemini', 'sonnet')


if __name__ == '__main__':
    unittest.main()
