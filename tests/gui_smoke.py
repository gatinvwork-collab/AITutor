"""Run the actual WebView, bridge and rendered screens with synthetic data.

Only the HTTP provider is replaced; this is not a live-provider acceptance test.
Output is written under build/gui-<random>/, never to the user's app-data.
"""

import json
import uuid
from pathlib import Path

import httpx
from PySide6.QtCore import QTimer

from tutor_ai.addresses import AddressDirectory
from tutor_ai.desktop import run
from tutor_ai.service import Service
from tests.test_application import FakeProvider

ROOT = Path(__file__).resolve().parent.parent / "build" / ("gui-" + uuid.uuid4().hex[:8])
SCRIPT = """
(async () => {
  try {
    const until=async predicate=>{for(let n=0;n<300;n++){if(predicate())return;await new Promise(r=>setTimeout(r,50));}throw new Error('UI condition timeout');};
    const parent = await rpc('register',{name:'Тестовый родитель',password:'test-parent-password',role:'PARENT'});
    state.route='students';await refresh();
    const form=document.querySelector('form[data-form="register"]');
    form.elements.role.value='STUDENT';form.elements.name.value='Алексей';form.elements.password.value='test-child-password';
    form.elements.region.value='Сам';form.elements.region.dispatchEvent(new Event('input',{bubbles:true}));
    await until(()=>form.querySelector('#region-options button'));
    form.querySelector('#region-options button').click();
    form.elements.city.value='Сам';form.elements.city.dispatchEvent(new Event('input',{bubbles:true}));
    await until(()=>form.querySelector('#city-options button'));
    form.querySelector('#city-options button').click();form.elements.school.value='Тестовая школа';
    form.requestSubmit();
    await until(()=>document.querySelector('#secret').open&&!inFlight);
    document.querySelector('#secret-close').click();
    const child=state.data.students.find(s=>s.name==='Алексей');
    if(!child || child.profile.address.mode!=='catalog')throw new Error('address selection not saved');
    await rpc('save_provider',{config:{kind:'ollama',model:'mock-gui-only',revision:0}});
    state.route='security';await refresh();
    if(!document.body.innerText.includes('Автор: Тестовый родитель')||!document.body.innerText.includes('Профиль: Алексей'))throw new Error('audit names missing');
    state.route='home';render();
    await refresh();
    if(!document.body.innerText.includes('Обучение: Алексей')) throw new Error('parent dashboard missing');
    window.__testPhase='parent';
    await new Promise(resolve=>setTimeout(resolve,1500));
    await rpc('logout');
    state.authMode='login';
    await refresh();
    if(!document.querySelector(`option[value="${child.id}"]`)?.textContent.includes('Алексей'))throw new Error('login name missing');
    await rpc('login',{account:child.id,password:'test-child-password'});
    await refresh();
    if(Object.keys(subjects).length!==4||subjects.math)throw new Error('subject catalog not migrated');
    state.route='subjects';state.subject='algebra';render();
    document.querySelector('.subject-switcher [data-value="geometry"]').click();
    if(state.subject!=='geometry'||!document.body.innerText.includes('Треугольники'))throw new Error('subject switch failed');
    state.route='homework';selectLearningSubject('geometry');await learnRefresh();render();
    const geom=await learnCall('work',{student:child.id,subject:'geometry'});await learnRefresh();render();
    let draft=document.querySelector('[data-learning-form="work_revision"] textarea');
    draft.value='Условие: угол 90 градусов; решение: 35+55=90';draft.dispatchEvent(new Event('input',{bubbles:true}));
    selectLearningSubject('informatics');render();selectLearningSubject('geometry');render();
    if(!document.querySelector('[data-learning-form="work_revision"] textarea').value.includes('35+55'))throw Error('draft lost on subject switch');
    const inf=await learnCall('work',{student:child.id,subject:'informatics'});await learnRefresh();render();
    if(!document.querySelector('[data-learning="analyze"][data-id="'+inf.id+'"]')||document.querySelector('[data-learning="analyze"][data-id="'+geom.id+'"]'))throw Error('Python scope incorrect');
    state.lesson=await rpc('start_lesson',{topic_id:'geometry-basics'});state.route='lesson';render();
    const result=await rpc('answer',{session:state.lesson.id,answer:'54 градусов',operation_id:'gui-answer-wrong'});
    state.lesson=result.session;render();
    if(!document.body.innerText.includes('Пока не сходится'))throw Error('feedback missing');
    await rpc('hint',{session:state.lesson.id});await rpc('pause',{session:state.lesson.id});
    selectLearningSubject('geometry');state.route='homework';await learnRefresh();render();
    await learnCall('work_revision',{work:geom.id,value:'Условие: угол 90 градусов; решение: 35+55=90',expected_revision:0,confirm:true});
    const queued=await learnCall('work_check',{work:geom.id,expected_revision:1});
    await until(async()=>true);
    for(let i=0;i<200;i++){const job=await rpc('learning',{action:'job',job:queued.job});if(job.status==='succeeded')break;if(job.status==='failed'||job.status==='stale')throw Error('homework check failed');await new Promise(r=>setTimeout(r,40));}
    await refresh();await learnRefresh();render();
    const hwSession=student().sessions.find(x=>x.homework===geom.id);
    if(!hwSession||hwSession.subject!=='geometry')throw Error('homework context incorrect');
    await rpc('set_theme',{theme:'dark'});
    await refresh();
    if(document.body.dataset.theme!=='dark')throw new Error('theme not applied');
    window.__testPhase='student';
    window.__testResult={passed:true,parent:parent.id,child:child.id};
  }catch(error){window.__testResult={passed:false,error:error.message};}
})();
"""


def main():
    result = {}

    def hook(window, page, service):
        timer = QTimer(window)
        timer.setInterval(500)
        started = [False]
        elapsed = [0]

        def poll():
            elapsed[0] += 1
            if elapsed[0] > 180:
                result.update(passed=False, error="GUI timeout")
                finish()
                return
            if not started[0]:
                def ready(value):
                    if value and not started[0]:
                        started[0] = True
                        page.runJavaScript(SCRIPT)
                page.runJavaScript("typeof bridge !== 'undefined' && !!bridge && !inFlight", ready)
            else:
                def phase(value):
                    if value == "parent":
                        window.grab().save(str(ROOT / "parent.png"))
                page.runJavaScript("window.__testPhase||''", phase)

                def completed(value):
                    if value and not result:
                        result.update(json.loads(value))
                        window.grab().save(str(ROOT / "student.png"))
                        finish()
                page.runJavaScript("window.__testResult?JSON.stringify(window.__testResult):''", completed)

        def finish():
            timer.stop()
            (ROOT / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            window.close()

        timer.timeout.connect(poll)
        timer.start()

    ROOT.mkdir(parents=True)
    def addresses(request):
        city = request.url.path.startswith('/structured')
        return httpx.Response(200, json={"features": [{"properties": {"countrycode": "RU", "osm_type": "R",
            "osm_id": 2 if city else 1, "type": "city" if city else "state",
            "name": "Самара" if city else "Самарская область", "state": "Самарская область"}}]})

    run(root_override=ROOT, service_factory=lambda root: Service(root, provider_factory=FakeProvider,
        address_directory=AddressDirectory(transport=httpx.MockTransport(addresses))),
        test_hook=hook)
    print(json.dumps({"directory": str(ROOT), **result}, ensure_ascii=True))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
