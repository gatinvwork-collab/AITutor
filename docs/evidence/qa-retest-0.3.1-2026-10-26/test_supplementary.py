"""Supplementary provider, password and import-limit coverage."""
import zipfile
import httpx
import pytest
from aitutor.providers import Provider
from aitutor.errors import AppError
from aitutor.documents import import_file
from tests.test_application import family as family_fixture, PASSWORD, child_login
family=family_fixture

@pytest.mark.parametrize("kind",["openai","gigachat","qwen","ollama"])
def test_list_models_contract_and_authorized_service_boundary(family,kind):
    app,_,child,_=family
    calls=[]
    def handle(request):
        calls.append(request)
        if "oauth" in str(request.url):
            return httpx.Response(200,json={"access_token":"local-token"})
        assert request.method=="GET"
        return httpx.Response(200,json={"models":[{"name":"qa-model"}]} if kind=="ollama"
                              else {"data":[{"id":"qa-model"}]})
    app.provider_factory=lambda config:Provider(config,transport=httpx.MockTransport(handle))
    app.save_provider({"kind":kind,"model":"qa-model","secret":"qa-only-secret",
                       "allow_text":True,"revision":1})
    result=app.list_models()
    assert result["models"]==["qa-model"]
    assert result["capabilities"]["text"] is True
    assert len(calls)==(2 if kind=="gigachat" else 1)
    child_login(app,child)
    before=len(calls)
    with pytest.raises(AppError):
        app.list_models()
    assert len(calls)==before

def test_provider_check_uses_configured_mock_and_student_is_denied(family):
    app,_,child,_=family
    assert app.test_provider()["text"]
    child_login(app,child)
    with pytest.raises(AppError):
        app.test_provider()

def test_change_own_password_keeps_child_and_old_password_stops_working(family):
    app,parent,child,_=family
    app.change_password("qa-new-parent-password")
    app.logout()
    with pytest.raises(AppError):
        app.login(parent["id"],PASSWORD)
    app.login(parent["id"],"qa-new-parent-password")
    assert app.snapshot()["students"][0]["id"]==child["id"]

def test_pdf_page_limit_rejects_without_mutating_homework(family,tmp_path):
    from pypdf import PdfWriter
    app,_,child,_=family
    child_login(app,child)
    p=tmp_path/"31-pages.pdf"
    writer=PdfWriter()
    for _ in range(31):
        writer.add_blank_page(width=100,height=100)
    writer.write(p)
    before=app.store.all("homework")
    with pytest.raises(AppError):
        import_file(app,p)
    assert app.store.all("homework")==before

def test_docx_unpacked_size_limit_rejects_before_parse(family,tmp_path):
    app,_,child,_=family
    child_login(app,child)
    p=tmp_path/"oversized.docx"
    with zipfile.ZipFile(p,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml",b"x"*(33*1024*1024))
    before=app.store.all("homework")
    with pytest.raises(AppError):
        import_file(app,p)
    assert app.store.all("homework")==before
