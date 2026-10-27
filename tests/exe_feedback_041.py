"""Compiled navigation/focus, genuine 0.4.0 upgrade and previous regression."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from tests import exe_qa_031 as base
from tests.upgrade_041 import verify
from tutor_ai.transfer import inventory

ROOT = Path(__file__).resolve().parent.parent


def isolated_only(output):
    output = Path(output).resolve()
    assert output.is_relative_to(ROOT / "build")
    metadata = output / "environment.json"
    fixtures = json.loads(metadata.read_text(encoding="utf-8"))["fixtures"]
    results = []
    for fixture in fixtures:
        port = base.free_port()
        path = output / (fixture["label"] + "-isolated-extra-navigation.json")
        assert not path.exists(), "Do not overwrite previous evidence"
        env = {**os.environ, "QTWEBENGINE_REMOTE_DEBUGGING": f"127.0.0.1:{port}"}
        with (output / (fixture["label"] + "-isolated-extra-process.log")).open("wb") as log:
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            process = subprocess.Popen([fixture["exe"], "--diagnostics"], cwd=os.environ.get("WINDIR", "C:/Windows"),
                                       env=env, stdout=log, stderr=log, startupinfo=startup)
            try:
                driver = ROOT / "docs/evidence/user-feedback-2026-10-27/navigation.mjs"
                result = subprocess.run(["node", str(driver), str(port), str(metadata), fixture["label"], str(path), "isolated"],
                                        capture_output=True, timeout=300)
                (output / (fixture["label"] + "-isolated-extra-runner.log")).write_bytes(result.stdout + result.stderr)
                assert result.returncode == 0, result.stderr.decode(errors="replace")
                results.append(json.loads(path.read_text(encoding="utf-8")))
            finally:
                base.close_test_process(process, Path(fixture["exe"]))
    summary = {"passed": all(r["passed"] for r in results), "checks": sum(len(r["clicks"]) for r in results)}
    (output / "isolated-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))
    return 0 if summary["passed"] else 1


def main():
    exe = ROOT / "dist/Tutor-AI-0.4.1.exe"
    output = ROOT / "build" / ("exe-feedback041-" + uuid.uuid4().hex[:8])
    output.mkdir()
    original_case = base.run_case
    def linked(*args, **kwargs):
        return original_case(*args, **kwargs, prefer_link=True)
    base.run_case = linked
    from tests.exe_qa_032 import main as previous_regression
    previous = previous_regression(exe)
    source = ROOT / "build/upgrade041-fixture"
    before = inventory(source / "app-data")
    upgrade = output / "upgrade"
    shutil.copytree(source, upgrade)
    expected = json.loads((upgrade / "expected.json").read_text(encoding="utf-8"))
    script = """
(async()=>{try{
 await rpc('login',{account:ACCOUNT,password:'upgrade041-parent-password'});await refresh();
 const checks=[];const check=(name,ok)=>{checks.push({name,ok:!!ok});if(!ok)throw Error(name);};
 check('version',state.status.version==='0.4.1');
 check('previous-profile',state.data.user.name==='0.4.0 parent'&&student().name==='0.4.0 child');
 check('previous-homework',student().homework.length===2);
 for(const subject of Object.keys(subjects)){
  document.querySelector('nav [data-value="home"]').click();
  document.querySelector(`[data-action="subject"][data-value="${subject}"]`).click();
  check('parent-catalog-'+subject,state.route==='subjects'&&document.querySelector('nav [aria-current="page"]').dataset.value==='home');
 }
 document.querySelector('nav [data-value="history"]').click();
 document.querySelector('[data-action="open-session"][data-value="past"]').click();
 for(let n=0;n<100&&inFlight;n++)await new Promise(r=>setTimeout(r,40));
 check('old-report',state.report?.id==='past'&&document.querySelector('.content').textContent.includes('Historical answer'));
 check('brand',document.querySelector('.brand-wordmark').textContent==='Tutor-AI');
 window.__testResult={passed:true,checks};
}catch(e){window.__testResult={passed:false,error:e.stack};}})();
""".replace("ACCOUNT", json.dumps(expected["parent"]))
    upgrade_ui = linked(upgrade, script, executable=exe)
    upgrade_exit = verify(upgrade)
    unchanged = inventory(source / "app-data") == before
    metadata = json.loads((ROOT / "docs/evidence/user-feedback-2026-10-27/environment.json").read_text(encoding="utf-8"))
    fixtures = []
    for fixture in metadata["fixtures"]:
        folder = output / fixture["label"]
        shutil.copytree(Path(fixture["folder"]) / "app-data", folder / "app-data", ignore=shutil.ignore_patterns("cache", "instance.lock"))
        os.link(exe, folder / exe.name)
        fixtures.append({**fixture, "folder": str(folder), "exe": str(folder / exe.name)})
    metadata["fixtures"] = fixtures
    metadata["baseline_sha256"] = metadata.pop("sha256", {})
    metadata["sha256"] = {"dist/Tutor-AI-0.4.1.exe": hashlib.sha256(exe.read_bytes()).hexdigest()}
    metadata["version"] = "0.4.1"
    metadata["diagnostics_enabled"] = True
    meta = output / "environment.json"
    meta.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    navigation = []
    for fixture in fixtures:
        port = base.free_port()
        path = output / (fixture["label"] + "-navigation.json")
        env = {**os.environ, "QTWEBENGINE_REMOTE_DEBUGGING": f"127.0.0.1:{port}"}
        with (output / (fixture["label"] + "-process.log")).open("wb") as log:
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            process = subprocess.Popen([fixture["exe"], "--diagnostics"], cwd=os.environ.get("WINDIR", "C:/Windows"),
                                       env=env, stdout=log, stderr=log, startupinfo=startup)
            try:
                driver = ROOT / "docs/evidence/user-feedback-2026-10-27/navigation.mjs"
                result = subprocess.run(["node", str(driver), str(port), str(meta), fixture["label"], str(path)],
                                        capture_output=True, timeout=300)
                (output / (fixture["label"] + "-runner.log")).write_bytes(result.stdout + result.stderr)
                assert result.returncode == 0, result.stderr.decode(errors="replace")
                navigation.append(json.loads(path.read_text(encoding="utf-8")))
                isolated = output / (fixture["label"] + "-isolated-navigation.json")
                result = subprocess.run(["node", str(driver), str(port), str(meta), fixture["label"], str(isolated), "isolated"],
                                        capture_output=True, timeout=300)
                (output / (fixture["label"] + "-isolated-runner.log")).write_bytes(result.stdout + result.stderr)
                assert result.returncode == 0, result.stderr.decode(errors="replace")
                navigation.append(json.loads(isolated.read_text(encoding="utf-8")))
                if fixture["label"] == "small":
                    keyboard = output / "keyboard.json"
                    result = subprocess.run(["node", str(ROOT / "tests/keyboard_041.mjs"), str(port), str(meta), str(keyboard)],
                                            capture_output=True, timeout=300)
                    (output / "keyboard-runner.log").write_bytes(result.stdout + result.stderr)
                    assert result.returncode == 0, result.stderr.decode(errors="replace")
            finally:
                base.close_test_process(process, Path(fixture["exe"]))
        logs = list((Path(fixture["folder"]) / "app-data/logs").glob("performance-*.jsonl"))
        assert logs, "Explicit diagnostics mode must create a trace"
        for log in logs:
            text = log.read_text(encoding="utf-8")
            assert all(marker not in text for marker in (fixture["parent"], fixture["child"], "QA Feedback Parent", "QA School", "Synthetic learning record"))
    keyboard_result = json.loads((output / "keyboard.json").read_text(encoding="utf-8"))
    summary = {"passed": previous == 0 and upgrade_ui["passed"] and upgrade_exit == 0 and unchanged
               and all(n["passed"] for n in navigation) and keyboard_result["passed"],
               "directory": str(output), "previous_regression_exit": previous, "upgrade_ui": upgrade_ui,
               "upgrade_verification": json.loads((upgrade / "verification.json").read_text(encoding="utf-8")),
               "source_unchanged": unchanged, "navigation_checks": sum(len(n["clicks"]) for n in navigation),
               "keyboard_checks": len(keyboard_result["checks"]), "diagnostic_privacy": True,
               "exe_sha256": metadata["sha256"]["dist/Tutor-AI-0.4.1.exe"]}
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(isolated_only(sys.argv[2]) if len(sys.argv) > 1 and sys.argv[1] == "isolated" else main())
