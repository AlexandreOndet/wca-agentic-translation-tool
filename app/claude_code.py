"""Proposals through the user's own installed and signed-in Claude Code CLI."""
import json
import re
import shutil
import subprocess
import tempfile

from core import ReviewError
from translation import INSTRUCTIONS, SCHEMA, compact_json, restore_keys, wire_context

MODELS = [{'id': 'opus', 'name': 'Claude Opus (latest)'}, {'id': 'sonnet', 'name': 'Claude Sonnet (latest)'}, {'id': 'haiku', 'name': 'Claude Haiku (latest)'}]
BATCH_TIMEOUT = 600
LOGIN_HINT = 'Install Claude Code and sign in with: claude auth login'
UNAVAILABLE = {'available': False, 'logged_in': False, 'subscription': ''}


def failure(detail, code=None):
    detail = ' '.join(str(detail).split())[-300:] or 'no details'
    hint = ' ' + LOGIN_HINT if re.search(r'log(?:ged)? ?in|authenticat', detail, re.I) else ''
    exit_code = f' (exit {code})' if code else ''
    return ReviewError(f'Claude Code request failed{exit_code}: {detail}. No translations were approved.{hint}')


class ClaudeCodeTranslator:
    # The app never reads Claude credentials; the unmodified CLI authenticates itself.
    def __init__(self, command='claude'):
        self.command = command

    def binary(self):
        binary = shutil.which(self.command)
        if not binary:
            raise ReviewError('Claude Code was not found. ' + LOGIN_HINT)
        return binary

    def check_access(self):
        self.binary()

    def status(self):
        try:
            binary = self.binary()
        except ReviewError:
            return UNAVAILABLE
        try:
            completed = subprocess.run([binary, 'auth', 'status', '--json'], capture_output=True, text=True, encoding='utf-8', timeout=15)
            info = json.loads(completed.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            info = None
        # An installed CLI that predates `auth status` still counts as installed.
        if not isinstance(info, dict):
            return dict(UNAVAILABLE, available=True)
        return {'available': True, 'logged_in': info.get('loggedIn') is True, 'subscription': str(info.get('subscriptionType') or info.get('authMethod') or '')}

    def models(self):
        self.binary()
        return MODELS

    def propose(self, model, context, progress=None):
        if model not in {item['id'] for item in MODELS}:
            raise ReviewError('Choose a Claude model.')
        wire, mapping = wire_context(context)
        # Tools, MCP servers, settings and project files stay out of the translation request.
        command = [self.binary(), '-p', '--model', model, '--output-format', 'json', '--tools', '', '--strict-mcp-config',
                   '--setting-sources', '', '--no-session-persistence', '--system-prompt', INSTRUCTIONS, '--json-schema', compact_json(SCHEMA)]
        try:
            with tempfile.TemporaryDirectory() as empty:
                completed = subprocess.run(command, input=compact_json(wire), capture_output=True, text=True, encoding='utf-8', timeout=BATCH_TIMEOUT, cwd=empty)
        except subprocess.TimeoutExpired:
            raise ReviewError('Claude Code did not answer in time. Validated batches can be resumed.') from None
        except OSError:
            raise ReviewError('Could not start Claude Code. ' + LOGIN_HINT) from None
        try:
            payload = json.loads(completed.stdout)
        except ValueError:
            raise failure(completed.stderr or completed.stdout, completed.returncode) from None
        if not isinstance(payload, dict) or payload.get('is_error') or payload.get('subtype') != 'success':
            detail = payload.get('result', '') if isinstance(payload, dict) else ''
            raise failure(detail or completed.stderr, completed.returncode)
        return restore_keys(payload.get('structured_output'), mapping)
