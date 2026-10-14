"""settings.save() is owner-only and atomic: the retained store must never be world-readable."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import settings


def mode_of(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def test_save_creates_owner_only_directory_and_file(tmp_path, monkeypatch):
    target = tmp_path/'context-recall'/'settings.json'
    monkeypatch.setenv('RECALL_SETTINGS', str(target))
    settings.set_value('codex_import', 'on')
    assert mode_of(target.parent) == 0o700
    assert mode_of(target) == 0o600
    assert json.loads(target.read_text(encoding='utf-8'))['codex_import'] is True


def test_save_does_not_follow_a_symlinked_temp_path(tmp_path, monkeypatch):
    directory = tmp_path/'context-recall'
    directory.mkdir(mode=0o700)
    target = directory/'settings.json'
    victim = tmp_path/'victim'
    victim.write_text('ORIGINAL', encoding='utf-8')
    (directory/'settings.tmp').symlink_to(victim)
    monkeypatch.setenv('RECALL_SETTINGS', str(target))
    settings.set_value('codex_import', 'on')
    assert victim.read_text(encoding='utf-8') == 'ORIGINAL'
    assert not target.is_symlink()
    assert json.loads(target.read_text(encoding='utf-8'))['codex_import'] is True


def test_concurrent_saves_neither_collide_nor_leave_temporaries(tmp_path, monkeypatch):
    target = tmp_path/'context-recall'/'settings.json'
    monkeypatch.setenv('RECALL_SETTINGS', str(target))

    def save_repeatedly():
        for _ in range(50):
            settings.save({'codex_import': True, 'codex_import_seconds': 4.0})

    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in [pool.submit(save_repeatedly) for _ in range(2)]:
            future.result()
    assert json.loads(target.read_text(encoding='utf-8'))['codex_import'] is True
    assert [p.name for p in target.parent.iterdir()] == ['settings.json']
