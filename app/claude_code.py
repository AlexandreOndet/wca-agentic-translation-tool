"""Proposals through the user's own installed and signed-in Claude Code CLI."""
import json
import shutil
import subprocess
import tempfile

from core import ReviewError
from translation import INSTRUCTIONS, SCHEMA, compact_json, restore_keys, wire_context

MODELS = [{'id': 'opus', 'name': 'Claude Opus (latest)'}, {'id': 'sonnet', 'name': 'Claude Sonnet (latest)'}, {'id': 'haiku', 'name': 'Claude Haiku (latest)'}]
BATCH_TIMEOUT = 600
LOGIN_HINT = 'Install Claude Code and sign in with: claude auth login'


class ClaudeCodeTranslator:
    # The app never reads Claude credentials; the unmodified CLI authenticates itself.
    def __init__(self, command='claude'):
        self.command = command

    def credential(self, provider):
        binary = shutil.which(self.command)
        if not binary:
            raise ReviewError('Claude Code was not found. ' + LOGIN_HINT)
        return binary

    def status(self):
        try:
            completed = subprocess.run([self.credential('claude-code'), 'auth', 'status', '--json'], capture_output=True, text=True, timeout=15)
            info = json.loads(completed.stdout)
        except (ReviewError, OSError, subprocess.TimeoutExpired, ValueError):
            return {'available': False, 'logged_in': False, 'subscription': ''}
        return {'available': True, 'logged_in': info.get('loggedIn') is True, 'subscription': str(info.get('subscriptionType') or info.get('authMethod') or '')}

    def models(self, provider):
        self.credential(provider)
        return MODELS

    def propose(self, provider, model, context, progress=None):
        if model not in {item['id'] for item in MODELS}:
            raise ReviewError('Choose a Claude model.')
        wire, mapping = wire_context(context)
        # Tools, MCP servers, settings and project files stay out of the translation request.
        command = [self.credential(provider), '-p', '--model', model, '--output-format', 'json', '--tools', '', '--strict-mcp-config',
                   '--setting-sources', '', '--no-session-persistence', '--system-prompt', INSTRUCTIONS, '--json-schema', compact_json(SCHEMA)]
        try:
            with tempfile.TemporaryDirectory() as empty:
                completed = subprocess.run(command, input=compact_json(wire), capture_output=True, text=True, timeout=BATCH_TIMEOUT, cwd=empty)
        except subprocess.TimeoutExpired:
            raise ReviewError('Claude Code did not answer in time. Validated batches can be resumed.') from None
        except OSError:
            raise ReviewError('Could not start Claude Code. ' + LOGIN_HINT) from None
        try:
            payload = json.loads(completed.stdout)
        except ValueError:
            raise ReviewError('Claude Code did not return valid JSON. ' + LOGIN_HINT) from None
        if not isinstance(payload, dict) or payload.get('is_error') or payload.get('subtype') != 'success':
            detail = str(payload.get('result', ''))[:300] if isinstance(payload, dict) else ''
            raise ReviewError(f'Claude Code request failed: {detail or "no details"}. No translations were approved.')
        result = payload.get('structured_output')
        if progress:
            progress(len(compact_json(result)))
        return restore_keys(result, mapping)
