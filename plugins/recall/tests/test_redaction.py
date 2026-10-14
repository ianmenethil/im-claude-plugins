#!/usr/bin/env python3
"""v2.4: credential-looking strings are redacted at index time (PRIVACY.md promise)."""
import json, sqlite3, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'hooks'))
from utils import redact_secrets
from prompt_submit import build_new_exchanges


class TestRedactSecrets(unittest.TestCase):
    def test_known_token_formats(self):
        cases = {
            'aws AKIAIOSFODNN7EXAMPLE': 'aws-access-key',
            'key sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789': 'anthropic-key',
            'key sk-proj-abcdefghijklmnopqrstuvwxyz0123456789': 'openai-key',
            'gh ghp_abcdefghijklmnopqrstuvwxyz0123456789': 'github-token',
            'hf hf_abcdefghijklmnopqrstuvwxyz012345': 'huggingface-token',
            'slack xoxb-123456789012-abcdefghij': 'slack-token',
            'Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789': 'bearer-token',
            'jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U': 'jwt',
        }
        for text, kind in cases.items():
            out = redact_secrets(text)
            self.assertIn(f'[REDACTED:{kind}]', out, text)
            self.assertNotIn(text.split()[-1], out, text)   # the secret itself is gone

    def test_private_key_block(self):
        pem = '-----BEGIN RSA PRIVATE KEY-----\nMIIEow...\nlots\n-----END RSA PRIVATE KEY-----'
        self.assertEqual(redact_secrets(f'here {pem} end'), 'here [REDACTED:private-key] end')

    def test_generic_assignment(self):
        out = redact_secrets('set API_KEY=abc123def456ghi789 and password: hunter2hunter2')
        self.assertIn('API_KEY=[REDACTED:credential]', out)
        self.assertIn('password: [REDACTED:credential]', out)

    def test_ordinary_text_untouched(self):
        for t in ('the token count was 4000', 'password reset flow', 'sk is short',
                  'use the secret sauce', 'tokens per second: 120', 'Bearer of bad news',
                  'the api key is invalid', 'the token is expired'):
            self.assertEqual(redact_secrets(t), t)

    def test_natural_language_secret(self):
        out = redact_secrets('My password is fake-password-for-review-only, ok?')
        self.assertNotIn('fake-password', out)
        self.assertIn('[REDACTED:credential]', out)

    def test_assignment_values_with_punctuation_or_spaces(self):
        """PRIVACY.md names the `KEY=value` and `"password": "…"` shapes. A value
        whose first 8 characters are not all word characters (a `%` in a password
        is normal) and a quoted value containing spaces were stored in full."""
        for text, leaked in (('PASSWORD=abc%defghijklmnop', 'abc%defghijklmnop'),
                             ('password = "hunter 2 hunter 2"', 'hunter 2 hunter 2')):
            out = redact_secrets(text)
            self.assertIn('[REDACTED:credential]', out, text)
            self.assertNotIn(leaked, out, text)

    def test_working_directory_variables_are_evidence_not_secrets(self):
        """`pwd` was a credential keyword, so PWD=/home/cae and OLDPWD=… — the paths
        users most often recall — were replaced before storage. `passwd` and
        `password` keys are still covered by their own keyword."""
        for text in ('PWD=/home/cae', 'OLDPWD=/home/cae/repos/claude-recall',
                     'cd $PWD && ls', 'export PWD=/tmp/x',
                     'declare -x PWD="/home/cae"'):
            self.assertEqual(redact_secrets(text), text, text)
        self.assertIn('[REDACTED:credential]', redact_secrets('passwd=supersecret1'))

    def test_underscore_pwd_keys_are_still_credentials(self):
        """Dropping `pwd` from the keywords also un-redacted the real password
        variables — MYSQL_PWD is the MySQL password. A keyword branch that needs
        an underscore before `pwd` catches *_PWD keys; OLDPWD has none, so it
        stays readable evidence."""
        for text in ('MYSQL_PWD=hunter2hunter2', 'DB_PWD=hunter2hunter2',
                     'ROOT_PWD=hunter2hunter2'):
            self.assertEqual(redact_secrets(text),
                             text.split('=')[0] + '=[REDACTED:credential]', text)
        self.assertEqual(redact_secrets('PWD=/home/cae'), 'PWD=/home/cae')
        self.assertEqual(redact_secrets('OLDPWD=/home/cae/repos'), 'OLDPWD=/home/cae/repos')
        self.assertEqual(redact_secrets('declare -x PWD="/home/cae"'),
                         'declare -x PWD="/home/cae"')

    def test_unpaired_surrogate_escape_is_stored_not_wedged(self):
        """A JSON `\\ud800` escape parses to a lone surrogate, which SQLite cannot
        bind. redact_secrets is the shared pre-store choke point, so it has to
        return storable text: the capture hook would otherwise fail before
        advancing byte_offset and re-read the same record on every later run."""
        text = json.loads(r'"caf\ude00 output"')
        out = redact_secrets(text)
        out.encode('utf-8')            # raised UnicodeEncodeError before
        self.assertIn('caf', out)

    def test_surrogate_reaching_the_store_through_the_hook_path(self):
        """The values build_new_exchanges hands to insert_exchanges must be bindable."""
        msgs = [{'role': 'user', 'text': 'lone \ud800 surrogate', 'timestamp': 't', 'tools': []},
                {'role': 'assistant', 'text': 'reply \ude00 here', 'timestamp': 't', 'tools': []}]
        ex = build_new_exchanges(msgs)[0]
        conn = sqlite3.connect(':memory:')
        conn.execute('CREATE TABLE exchanges (user_text TEXT, preview TEXT)')
        conn.execute('INSERT INTO exchanges VALUES (?, ?)', (ex['user_text'], ex['preview']))
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM exchanges').fetchone()[0], 1)
        conn.close()

    def test_applied_when_building_exchanges(self):
        msgs = [{'role': 'user', 'text': 'my key is sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123', 'timestamp': 't', 'tools': []},
                {'role': 'assistant', 'text': 'exporting AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY', 'timestamp': 't',
                 'tools': ['$ export TOKEN=ghp_abcdefghijklmnopqrstuvwxyz0123456789']}]
        ex = build_new_exchanges(msgs)[0]
        self.assertIn('[REDACTED:anthropic-key]', ex['user_text'])
        self.assertIn('[REDACTED:', ex['assistant_text']); self.assertNotIn('wJalrXUtnFEMIK7MDENG', ex['assistant_text'])
        self.assertIn('[REDACTED:', ex['tool_text']); self.assertNotIn('ghp_abc', ex['tool_text'])
        self.assertNotIn('sk-ant', ex['preview'])


if __name__ == '__main__':
    unittest.main()


class TestRedactionIsLinear(unittest.TestCase):
    """v2.4.0's generic credential pattern backtracked quadratically on long
    no-space runs (20k chars: 7 s; 80k: hang), which would time out the capture
    hook on a pasted blob. All quantifiers are now bounded."""

    def test_long_no_space_runs_are_fast(self):
        import time
        for n in (80_000, 400_000):
            t = time.perf_counter(); redact_secrets('x' * n); dt = time.perf_counter() - t
            self.assertLess(dt, 0.5, f"{n} chars took {dt:.2f}s")

    def test_still_redacts_assignments(self):
        out = redact_secrets('export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY')
        self.assertIn('[REDACTED:credential]', out); self.assertNotIn('wJalr', out)
