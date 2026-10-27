"""Scenario A against the real renamed exe, with actual legacy encrypted schemas."""
import json
import shutil
import uuid
from pathlib import Path
from tutor_ai.crypto import seal
from tutor_ai.service import Service
from tests.test_application import PASSWORD, CHILD_PASSWORD, PROFILE
from tests.test_feedback_02 import make_legacy
from tests.test_feedback_03 import legacy_v2
from tests.exe_qa_031 import run_case
from tutor_ai.transfer import inventory


def main():
    root = Path(__file__).resolve().parent.parent
    output = root / 'build' / ('exe-legacy040-' + uuid.uuid4().hex[:8])
    output.mkdir()
    results = []
    for version in (1, 2, 3):
        original = output / ('source' + str(version))
        app = Service(original / 'app-data')
        parent = app.register('Old AI-Tutor parent', PASSWORD, 'PARENT')
        child = app.register('Old student', CHILD_PASSWORD, 'STUDENT', PROFILE)
        with app.store.transaction():
            app.store.put('homework', 'preserved', {'id': 'preserved', 'student': child['id'],
                'text': 'AI-Tutor unchanged history', 'filename': 'old.txt',
                'original': seal(app.store.attachment_key(), b'old bytes', b'preserved')}, child['id'])
        if version == 1:
            make_legacy(app, child)
        elif version == 2:
            legacy_v2(app)
        app.store.close()
        before = inventory(original / 'app-data')
        target = output / ('case' + str(version))
        shutil.copytree(original / 'app-data', target / 'app-data')
        code = '''
(async()=>{try{
 const checks=[];const check=(name,ok)=>{checks.push({name,ok:!!ok});if(!ok)throw Error(name);};
 check('version',state.status.version==='0.4.0');
 check('old profiles before login',state.status.accounts.length===2);
 await rpc('login',{account:ACCOUNT,password:PASSWORD});await refresh();
 check('old identity',state.data.user.name==='Old AI-Tutor parent'&&state.data.students[0].id===CHILD);
 check('verbatim homework',student().homework.some(h=>h.id==='preserved'&&h.text==='AI-Tutor unchanged history'));
 check('old data opened without registration',state.status.exists&&state.status.authenticated);
 state.route='history';render();check('absent historical counters shown as unknown',!document.querySelector('.content').textContent.includes('undefined'));window.__testResult={passed:true,checks};
}catch(e){window.__testResult={passed:false,error:e.stack};}})();
'''.replace('ACCOUNT', json.dumps(parent['id'])).replace('PASSWORD', json.dumps(PASSWORD)).replace('CHILD', json.dumps(child['id']))
        result = run_case(target, code, executable=root / 'dist' / 'Tutor-AI-0.4.0.exe')
        assert inventory(original / 'app-data') == before
        results.append({'schema': version, 'result': result, 'source_unchanged': True})
    summary = {'passed': all(r['result']['passed'] for r in results), 'cases': results, 'directory': str(output)}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())