"""Read-only, explicit maintenance artifacts. No arbitrary file access."""
import hashlib, json
from core import ROOT, AppError
import store

FILES={
 "report":"reports/evaluation.json","cases":"eval/cases.json",
 "strategy-v1":"strategies/v1.json","strategy-v2":"strategies/v2.json",
 "prompt-v1":"prompts/v1.txt","prompt-v2":"prompts/v2.txt",
 "implementation":"core.py","agent":"agent.py","evaluation-code":"evaluate.py",
 "acceptance":"docs/acceptance.md","evaluation-notes":"docs/evaluation.md",
 "ui-verification":"reports/ui-verification.json","badcases":"reports/badcases.json","badcase-notes":"docs/badcases.md","browser-live-runs":"reports/browser-live-runs.json","protocol-1788878777288169500":"reports/protocol-1788878777288169500.json"}
def read_json(path):
    f=ROOT/path
    if not f.is_file():return None
    try:return json.loads(f.read_text(encoding="utf-8-sig"))
    except (ValueError,UnicodeError):return None
def live_reports():
    return [r for p in sorted((ROOT/"reports").glob("live-eval-*.json")) if (r:=read_json(p))]

def bundle():
    report=read_json(FILES["report"])
    dataset=read_json(FILES["cases"])
    catalog=ROOT/"data/catalog.json"
    cases_match=bool(report and (ROOT/FILES["cases"]).exists() and report.get("test_set_sha256")==hashlib.sha256((ROOT/FILES["cases"]).read_bytes()).hexdigest())
    catalog_match=bool(report and catalog.exists() and report.get("catalog_sha256")==hashlib.sha256(catalog.read_bytes()).hexdigest())
    return store.redact({"report":report,"cases":dataset.get("cases",[]) if cases_match and dataset else [],
        "verification":read_json(FILES["ui-verification"]),"live_reports":live_reports(),"badcases":read_json(FILES["badcases"]),"current_verification":read_json("reports/badcase-validation.json") or read_json("reports/live-verification.json"),
        "metadata":{"cases_match":cases_match,"catalog_match":catalog_match,
          "system_created":None,"current_code_verified_by_historical_report":False},
        "files":[{"id":k,"name":v,"url":"/files/"+k} for k,v in FILES.items() if (ROOT/v).is_file()]})
def artifact(key):
    if key.startswith("live-eval-") and key[10:].isdigit():
        f=ROOT/"reports"/(key+".json")
        if not f.is_file():raise AppError("文件未生成",404)
        return json.dumps(store.redact(read_json(f)),ensure_ascii=False,indent=2).encode("utf-8"),f.name
    if key not in FILES:raise AppError("文件不在允许列表",404)
    f=ROOT/FILES[key]
    if not f.is_file():raise AppError("文件未生成",404)
    text=f.read_text(encoding="utf-8-sig")
    if f.suffix==".json":
        text=json.dumps(store.redact(json.loads(text)),ensure_ascii=False,indent=2)
    else:text=store.redact(text)
    return text.encode("utf-8"),f.name
def run(owner,run_id):
    import contextlib
    with contextlib.closing(store.connect()) as db:
        row=db.execute("SELECT body,task_id FROM runs WHERE id=? AND owner=?",(run_id,owner)).fetchone()
        if not row:raise AppError("记录不存在或不可访问",404)
        return store.redact({**json.loads(row["body"]),"task_id":row["task_id"]})
