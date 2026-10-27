"""Synthetic no-provider fixtures and identification for user-feedback QA."""
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from tutor_ai.service import Service

PASSWORD = 'qa-feedback-password'
PROFILE = {'region': 'QA Region', 'city': 'QA City', 'school': 'QA School', 'grade': 7,
           'address': {'mode': 'manual'}}

def main():
    work = ROOT / 'build' / 'qa-user-feedback-20261027'
    work.mkdir(parents=True, exist_ok=False)
    files = [*ROOT.glob('tutor_ai/*.py'), *ROOT.glob('ui/*'), ROOT/'main.py', ROOT/'dist/Tutor-AI-0.4.0.exe']
    metadata = {'platform': platform.platform(), 'python': sys.version,
                'disk_before': shutil.disk_usage(ROOT)._asdict(),
                'sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in files if p.is_file()}, 'fixtures': []}
    git = ['git', '-c', 'safe.directory='+ROOT.as_posix()]
    for name, args in [('commit', ['rev-parse', 'HEAD']), ('status', ['status', '--short'])]:
        metadata[name] = subprocess.run(git+args, cwd=ROOT, capture_output=True, text=True,
                                        encoding='utf-8', errors='replace').stdout
    for label, count, notifications in [('small', 0, 0), ('history1500', 1500, 60)]:
        folder = work/label
        folder.mkdir()
        app = Service(folder/'app-data')
        parent = app.register('QA Feedback Parent', PASSWORD, 'PARENT')
        child = app.register('QA Feedback Child', PASSWORD, 'STUDENT', PROFILE)
        with app.store.transaction():
            for n in range(count):
                sid = f'qa-session-{n:05}'
                app.store.put('session', sid, {'id': sid, 'student': child['id'], 'subject': 'algebra',
                    'topic': 'math-equations', 'title': f'QA Lesson {n}', 'status': 'complete',
                    'mode': 'learn', 'created': '2026-10-27T00:00:00+00:00', 'seconds': 60,
                    'correct': 2, 'total': 3, 'program_snapshot': {},
                    'messages': [{'role': 'assistant', 'text': 'Synthetic learning record.'*8}]}, child['id'])
            for n in range(notifications):
                nid = f'qa-notification-{n}'
                app.store.put('notification', nid, {'id': nid, 'event': nid, 'recipient': parent['id'],
                    'student': child['id'], 'actor': child['id'], 'student_name': 'QA Feedback Child',
                    'actor_name': 'QA Feedback Child', 'at': '2026-10-27T00:00:00+00:00', 'read_at': None,
                    'changes': {'school': {'before': 'QA School', 'after': 'QA School B'}}}, child['id'])
        assert app.store.get('provider', 'family') is None
        vault_bytes = app.store.path.stat().st_size
        app.logout()
        exe = folder/'Tutor-AI-0.4.0.exe'
        shutil.copyfile(ROOT/'dist/Tutor-AI-0.4.0.exe', exe)
        metadata['fixtures'].append({'label': label, 'folder': str(folder), 'exe': str(exe),
            'parent': parent['id'], 'child': child['id'], 'sessions': count,
            'notifications': notifications, 'vault_bytes': vault_bytes, 'provider_configured': False})
    (OUT/'environment.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'fixtures': len(metadata['fixtures']), 'free_bytes': shutil.disk_usage(ROOT).free}))

if __name__ == '__main__':
    main()
