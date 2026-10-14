#!/usr/bin/env python3
"""WI-25: db.py tracks a schema version so future migrations have a managed path.

The only prior migration was the one-shot v1 index.json -> SQLite import; there
was no schema_version, so v2 -> v3 (vector/tier tables) had no framework.
"""

import sys
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import db
from db import (get_connection, insert_session, insert_exchanges, insert_tag,
                search_exchanges_fts)


class TestSchemaVersion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = Path(self.tmp) / 'sv.db'

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _user_version(self, path):
        conn = get_connection(path)
        v = conn.execute('PRAGMA user_version').fetchone()[0]
        conn.close()
        return v

    def test_schema_version_constant_is_set(self):
        self.assertGreaterEqual(db.SCHEMA_VERSION, 1)

    def test_fresh_db_is_stamped_current(self):
        """A brand-new DB ends up at the current SCHEMA_VERSION."""
        self.assertEqual(self._user_version(self.db_path), db.SCHEMA_VERSION)

    def test_pre_versioning_db_is_upgraded(self):
        """An existing DB at user_version 0 is stamped to current on reconnect."""
        conn = get_connection(self.db_path)
        conn.execute('PRAGMA user_version = 0')  # simulate a pre-versioning store
        conn.commit()
        conn.close()
        self.assertEqual(self._user_version(self.db_path), db.SCHEMA_VERSION)

    def test_reconnect_is_idempotent(self):
        self._user_version(self.db_path)
        self.assertEqual(self._user_version(self.db_path), db.SCHEMA_VERSION)

    def test_creation_interrupted_before_exchanges_is_completed(self):
        """A first-ever creation interrupted after `sessions` committed has no
        `exchanges`; the bootstrap test is keyed on `sessions` alone, so opening it
        raised 'no such table: exchanges' — and `doctor --repair` cannot open a store
        it cannot open. The fix completes the missing objects from the idempotent DDL.
        """
        raw = sqlite3.connect(self.db_path)
        raw.executescript(
            "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, project_path TEXT NOT NULL,"
            " project_hash TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT,"
            " exchange_count INTEGER DEFAULT 0, transcript_path TEXT, byte_offset INTEGER DEFAULT 0,"
            " metadata TEXT);")
        raw.commit()
        raw.close()

        conn = get_connection(self.db_path)   # raised OperationalError before
        try:
            insert_session(conn, 'sess-half', '/p', 'h', '2026-10-14T10:00:00Z')
            insert_exchanges(conn, 'sess-half', [
                {'idx': 0, 'timestamp': '2026-10-14T10:00:01Z', 'preview': 'half-built',
                 'user_text': 'repaired store', 'assistant_text': 'works'}])
            self.assertEqual(
                [r['idx'] for r in search_exchanges_fts(conn, 'repaired', session_id='sess-half')], [0])
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], db.SCHEMA_VERSION)
        finally:
            conn.close()

    def test_creation_interrupted_before_tags_is_completed(self):
        """The repair guard was keyed on `exchanges` alone, so a first-ever
        creation interrupted after `exchanges` committed but before `tags` still
        opened un-repaired — and the next tag write raised 'no such table: tags'.
        Any missing base table now re-runs the idempotent DDL.
        """
        raw = sqlite3.connect(self.db_path)
        raw.executescript(
            "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, project_path TEXT NOT NULL,"
            " project_hash TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT,"
            " exchange_count INTEGER DEFAULT 0, transcript_path TEXT, byte_offset INTEGER DEFAULT 0,"
            " metadata TEXT);"
            "CREATE TABLE exchanges (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,"
            " idx INTEGER NOT NULL, timestamp TEXT NOT NULL, preview TEXT NOT NULL,"
            " user_text TEXT, assistant_text TEXT, tool_text TEXT, UNIQUE(session_id, idx));")
        raw.commit()
        raw.close()

        conn = get_connection(self.db_path)   # opened, then insert_tag raised before
        try:
            insert_session(conn, 'sess-torn', '/p', 'h', '2026-10-14T10:00:00Z')
            insert_exchanges(conn, 'sess-torn', [
                {'idx': 0, 'timestamp': '2026-10-14T10:00:01Z', 'preview': 'torn store',
                 'user_text': 'torn store repair', 'assistant_text': 'works'}])
            insert_tag(conn, 'repaired', 'sess-torn', 0)
            self.assertEqual(
                [r['tag'] for r in conn.execute(
                    "SELECT tag FROM tags WHERE session_id = 'sess-torn'")], ['repaired'])
            self.assertEqual(
                [r['idx'] for r in search_exchanges_fts(conn, 'torn', session_id='sess-torn')], [0])
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], db.SCHEMA_VERSION)
        finally:
            conn.close()


if __name__ == '__main__':
    unittest.main()
