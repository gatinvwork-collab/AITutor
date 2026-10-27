"""Additional independent checks for the full 0.3.2 contract."""
import copy
import pytest
from aitutor.education import topic
from aitutor.documents import import_file
from aitutor.errors import AppError
from tests.test_application import family as family_fixture, child_login
family=family_fixture

def test_failed_hint_does_not_extend_inactivity(family,monkeypatch):
    app,_,child,clock=family
    child_login(app,child)
    lesson=app.start_lesson("math-equations")
    real_save=app.store.save
    def fail_hint():
        if app.lesson(lesson["id"])["hints_used"]:
            raise OSError("QA injected hint publication failure")
        real_save()
    monkeypatch.setattr(app.store,"save",fail_hint)
    clock[0]+=100
    with pytest.raises(OSError):
        app.hint(lesson["id"])
    assert app.lesson(lesson["id"])["hints_used"]==0
    clock[0]+=100
    app.tick()
    actual=app.lesson(lesson["id"])
    assert actual["status"]=="paused" and actual["seconds"]==180, {
        "status":actual["status"],"seconds":actual["seconds"],
        "last_action":app.last_action,"initial_action":100,"clock":clock[0]}

def test_subject_diagnosis_transition_failure_preserves_queue(family,monkeypatch):
    app,_,child,clock=family
    child_login(app,child)
    lesson=app.start_lesson("math-equations","subject_diagnose")
    for n in range(2):
        current=app.lesson(lesson["id"])
        expected=topic(current["topic"])["tasks"][current["index"]][1]
        app.answer(lesson["id"],expected,"independent-diag-"+str(n))
    before=copy.deepcopy(app.lesson(lesson["id"]))
    real_save=app.store.save
    def fail_transition():
        if app.lesson(lesson["id"])["topic"]!=before["topic"]:
            raise OSError("QA diagnosis next topic write failure")
        real_save()
    monkeypatch.setattr(app.store,"save",fail_transition)
    expected=topic(before["topic"])["tasks"][before["index"]][1]
    with pytest.raises(OSError):
        app.answer(lesson["id"],expected,"independent-diag-transition")
    assert app.lesson(lesson["id"])==before and app.active_lesson==lesson["id"]
    monkeypatch.setattr(app.store,"save",real_save)
    result=app.answer(lesson["id"],expected,"independent-diag-transition")
    assert result["session"]["topic"]!=before["topic"]
    assert app.answer(lesson["id"],expected,"independent-diag-transition")==result

@pytest.mark.parametrize("command",["start","resume"])
def test_failed_start_or_resume_preserves_persisted_and_controller_state(family,monkeypatch,command):
    app,_,child,clock=family
    child_login(app,child)
    old=app.start_lesson("math-equations")
    app.pause(old["id"])
    before=copy.deepcopy(app.store.all("session"))
    markers=(app.active_lesson,app.last_tick,app.last_action)
    def fail_save():
        raise OSError("QA start or resume failure")
    monkeypatch.setattr(app.store,"save",fail_save)
    with pytest.raises(OSError):
        if command=="start":
            app.start_lesson("physics-speed")
        else:
            app.resume(old["id"])
    assert app.store.all("session")==before
    assert (app.active_lesson,app.last_tick,app.last_action)==markers

@pytest.mark.parametrize("ext",["txt","py","csv"])
@pytest.mark.parametrize("length",[29999,30000,30001])
def test_agreed_policy_with_non_bmp_and_bom(family,tmp_path,ext,length):
    app,_,child,_=family
    child_login(app,child)
    p=tmp_path/("unicode."+ext)
    raw=b"\xef\xbb\xbf"+("😀"*length).encode()
    p.write_bytes(raw)
    before=app.store.all("homework")
    if length>30000:
        with pytest.raises(AppError) as error:
            import_file(app,p)
        assert error.value.code=="text_limit" and "Разбейте" in str(error.value)
        assert app.store.all("homework")==before
    else:
        result=import_file(app,p)
        assert result["text"]=="😀"*length and result["extraction"]["characters"]==length
