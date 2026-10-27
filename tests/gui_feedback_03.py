"""Real Qt/WebView checks and screenshots; isolated synthetic data only."""
import json
import uuid
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication

from tutor_ai.desktop import run
from tutor_ai.service import Service
from tests.test_application import FakeProvider

ROOT = Path(__file__).resolve().parent.parent / "build" / ("gui03-" + uuid.uuid4().hex[:8])
SCRIPT = r"""
(async()=>{
  try {
    const assert=(test,message)=>{if(!test)throw new Error(message);};
    const until=async test=>{for(let n=0;n<300;n++){if(test())return;await new Promise(r=>setTimeout(r,40));}throw new Error('UI timeout');};
    const shot=async name=>{window.__capture=name;await until(()=>window.__captured===name);};
    const p=await rpc('register',{name:'Анна · родитель',password:'test-parent-password',role:'PARENT'});
    const c=await rpc('register',{name:'Алексей',password:'test-child-password',role:'STUDENT',profile:{region:'Самарская область',city:'Самара',school:'Школа № 7',grade:7,address:{mode:'manual'}}});
    const c2=await rpc('register',{name:'Мария',password:'test-child-password',role:'STUDENT',profile:{region:'Самарская область',city:'Самара',school:'Школа № 7',grade:7}});
    await rpc('save_provider',{config:{kind:'ollama',model:'mock-gui-only',revision:0}});
    await refresh();assert(document.body.dataset.design==='strict','parent default');
    await rpc('logout');await rpc('login',{account:c.id,password:'test-child-password'});await refresh();
    assert(document.body.dataset.design==='modern','student default');
    state.route='knowledge';render();assert(!document.querySelector('option[value="math_archive"]'),'empty archive');
    // Exercise actual form submission, not just service calls.
    state.route='settings';render();document.querySelector('[data-action="edit-profile"]').click();
    await until(()=>document.querySelector('form[data-form="profile"]')&&!inFlight);
    let form=document.querySelector('form[data-form="profile"]');
    assert(form.elements.city.value==='Самара','prefilled address');
    form.elements.school.value='Лицей № 1';form.elements.school.dispatchEvent(new Event('input',{bubbles:true}));
    form.requestSubmit();await until(()=>state.route==='settings'&&!inFlight);
    assert(state.data.students[0].profile.school==='Лицей № 1','school saved');
    const theme=document.querySelector('form[data-form="theme"]');
    theme.elements.design.value='strict';theme.elements.design.dispatchEvent(new Event('change',{bubbles:true}));
    assert(document.body.dataset.design==='strict','preview design');
    theme.elements.theme.value='dark';theme.requestSubmit();await until(()=>!inFlight&&state.data.user.theme==='dark');
    state.lesson=await rpc('start_lesson',{topic_id:'geometry-triangles'});
    // Four visual combinations, overview + learning + profile for each.
    for(const design of ['strict','modern'])for(const theme of ['light','dark']){
      await rpc('set_theme',{theme,design});await refresh();
      state.route='home';render();await shot(design+'-'+theme+'-overview');
      state.route='lesson';render();await shot(design+'-'+theme+'-lesson');
      await openProfile(c.id);await shot(design+'-'+theme+'-profile');
      assert(document.documentElement.scrollWidth<=innerWidth,'horizontal overflow');
    }
    state.profileDirty=false;
    await rpc('logout');await rpc('login',{account:p.id,password:'test-parent-password'});await refresh();
    assert(state.data.notifications.length===1,'parent notification');
    assert(state.data.notifications[0].changes.school.after==='Лицей № 1','notification values');
    state.route='notifications';render();await shot('notifications');
    document.querySelector('[data-action="read-notification"]').click();
    await until(()=>!inFlight&&!!state.data.notifications[0].read_at);
    // Parent editing an actual linked child's form.
    await openProfile(c.id);form=document.querySelector('form[data-form="profile"]');
    form.elements.name.value='Алексей Новый';form.requestSubmit();
    // 0.4.1 defines returning to the section where the profile was opened.
    await until(()=>state.route==='notifications'&&!inFlight);
    assert(state.data.students.find(s=>s.id===c.id).name==='Алексей Новый','parent editing');
    for(const design of ['strict','modern'])for(const theme of ['light','dark']){
      await rpc('set_theme',{theme,design});state.route='home';await refresh();await shot(design+'-'+theme+'-parent');
    }
    // Seeded historical archive is outside the current week; empty sibling stays clean.
    await rpc('snapshot');state.selected=c.id;state.route='history';await refresh();
    assert(document.querySelector('option[value="math_archive"]'),'archive availability');
    state.reportSubject='math_archive';state.selected=c2.id;render();
    assert(!document.querySelector('option[value="math_archive"]')&&!state.reportSubject,'archive reset');
    for(const design of ['strict','modern']){
      await rpc('set_theme',{theme:'system',design});state.route='settings';await refresh();
      await shot(design+'-system-dark');assert(document.body.dataset.theme==='dark'&&state.data.user.theme==='system','system dark change');
      await shot(design+'-system-light');assert(document.body.dataset.theme==='light'&&state.data.user.theme==='system','system light change');
    }
    window.__testResult={passed:true,captures:21};
  }catch(error){window.__testResult={passed:false,error:error.message};}
})();
"""


def main():
    result = {}
    ROOT.mkdir(parents=True)

    def hook(window, page, service):
        started = [False]
        captured = set()
        timer = QTimer(window)
        elapsed = [0]

        def finish():
            timer.stop()
            (ROOT / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            window.close()

        def poll():
            elapsed[0] += 1
            if elapsed[0] > 700:
                result.update(passed=False, error="GUI timeout")
                finish()
                return
            if not started[0]:
                def ready(value):
                    if value and not started[0]:
                        started[0] = True
                        page.runJavaScript(SCRIPT)
                page.runJavaScript("typeof bridge!=='undefined'&&!!bridge&&!inFlight", ready)
                return

            def capture(value):
                if value and value not in captured:
                    captured.add(value)
                    if value.endswith('system-dark'):
                        QApplication.instance().styleHints().setColorScheme(Qt.ColorScheme.Dark)
                    elif value.endswith('system-light'):
                        QApplication.instance().styleHints().setColorScheme(Qt.ColorScheme.Light)
                    # Seed historical data after the screens of the clean profile have been checked.
                    if value == "modern-dark-parent":
                        child = next(s["id"] for s in service.snapshot()["students"] if s["name"] == "Алексей Новый")
                        with service.store.transaction():
                            service.store.put("session", "legacy", {"id": "legacy", "subject": "math",
                                "topic": "unknown", "created": "2020-01-01", "status": "complete", "seconds": 0,
                                "title": "Историческое занятие", "messages": [{"text": "Сохранённый разбор"}],
                                "program_snapshot": {}, "correct": 0, "total": 0}, child)
                    def painted():
                        window.grab().save(str(ROOT / (value + ".png")))
                        page.runJavaScript("window.__captured=" + json.dumps(value))
                    QTimer.singleShot(450, painted)
            page.runJavaScript("window.__capture||''", capture)

            def complete(value):
                if value and not result:
                    result.update(json.loads(value))
                    if not result.get("passed"):
                        window.grab().save(str(ROOT / "failure.png"))
                    finish()
            page.runJavaScript("window.__testResult?JSON.stringify(window.__testResult):''", complete)

        timer.setInterval(250)
        timer.timeout.connect(poll)
        timer.start()

    run(root_override=ROOT, service_factory=lambda root: Service(root, provider_factory=FakeProvider), test_hook=hook)
    print(json.dumps({"directory": str(ROOT), **result}))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
