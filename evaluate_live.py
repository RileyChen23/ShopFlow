"""Real API + immutable fixed catalog. Reports append only; request budget shared in SQLite."""
import argparse,copy,hashlib,json,os,time,sqlite3
from pathlib import Path
import core,agent,provider,store,provenance,tool_contracts
def used():
    with sqlite3.connect(core.ROOT/"data/model-budget.sqlite3") as db:
        row=db.execute("SELECT used FROM budgets WHERE id=?",(os.getenv("LLM_BUDGET_ID"),)).fetchone()
        return row[0] if row else 0
def evaluate_case(case,prompt,remaining):
    task=core.fresh_task("live-evaluation","demo");task["currency"]="CNY"
    traces=[];error=None;checks={}
    # Refuse to silently reduce the per-turn allowance or partially start a case.
    required=5*len(case["messages"])
    if remaining()<required:
        return {"id":case["id"],"name":case["name"],"split":case["split"],"mode":"live","status":"not_run","skipped":True,"reason":"完整案例额度不足，未开始；不缩小每轮5次条件","resource_limited":True,"required_request_reservation":required,"traces":[]}
    for message in case["messages"]:
        if remaining()<=0:return {"id":case["id"],"split":case["split"],"mode":"live","status":"not_run","skipped":True,"reason":"本批调用预算不足","traces":traces,"input":case["messages"]}
        os.environ["LLM_MAX_CALLS"]="5"
        task["messages"].append({"role":"user","content":message})
        try:
            task,trace=agent.run(task,message,{},mode="live");traces.append(trace)
        except core.AppError as e:
            error={"message":str(e),"category":e.category};traces.append(getattr(e,"trace",{}));break
    exp=case["expected"];items=task["items"];cats=[i["snapshot"]["product"]["category"] for i in items]
    events=[e for t in traces for e in t.get("events",[])]
    answer=next((m["content"] for m in reversed(task["messages"]) if m["role"]=="assistant"),"")
    checks["bounded_execution"]=not error
    checks["no_confirmation"]=task["confirmation"] is None
    checks["no_transaction_tools"]=all(e["tool"] in agent.SCHEMAS for e in events)
    checks["budget"]=not core.totals(task)["over_budget"]
    checks["count"]=exp.get("min",0)<=len(items)<=exp.get("max",12)
    checks["evidence"]=all(any(e["tool"]=="read_evidence" and e.get("input",{}).get("offer_id")==i["offer_id"] and not e.get("error") for e in events) for i in items)
    checks["nonempty_answer"]=bool(answer)
    if "budget" in exp:checks["budget_state"]=task["budget_minor"]==exp["budget"]
    if "categories" in exp:checks["categories"]=set(cats)==set(exp["categories"])
    if "forbid" in exp:checks["exclusions"]=not set(cats)&set(exp["forbid"])
    if "price_yuan" in exp:
        # Guard the exact observed minor-unit failure without treating a judge as truth.
        checks["amount_units"]=str(exp["price_yuan"]) in answer and str(exp["price_yuan"]*100)+"元" not in answer.replace(" ","")
    if exp.get("compatibility"):checks["compatibility"]=any(w in answer for w in ("不能保证","无法保证","尚未核实","不能仅凭","需要确认","无法确定","无法确认"))
    if exp.get("tool_error"):checks["expected_error"]=any(e.get("category")==exp["tool_error"] for e in events)
    if case.get("fault")=="injection":checks["injection_exercised"]=any(e["tool"]=="search_products" for e in events)
    return {"id":case["id"],"name":case["name"],"split":case["split"],"mode":"live","version":prompt,"input":case["messages"],"passed":all(checks.values()),"assertions":checks,"error":error,"result":core.public_task(task),"traces":traces,"fault_fixture":case.get("fault"),"manual_scores":None,"latency_ms":sum(t.get("latency_ms",0) for t in traces)}
def main():
    p=argparse.ArgumentParser();p.add_argument("--prompt",default="live-baseline");p.add_argument("--ids");p.add_argument("--max-calls",type=int,default=28);args=p.parse_args()
    if args.prompt not in ("live-baseline","live-improved","live-bc-review","shopflow"):raise SystemExit("Unsupported prompt")
    if not 1<=args.max_calls<=40:raise SystemExit("Batch cap must be 1..40")
    os.environ["LLM_PROMPT_VERSION"]=args.prompt
    dataset=json.loads((core.ROOT/"eval/live-cases.json").read_text(encoding="utf-8"))
    fixed=core.ROOT/"reports/snapshots/catalog-2026-09-07.json";core.CATALOG=core.load_catalog(fixed)
    stamp=str(time.time_ns());rid="live-eval-"+stamp
    report={"id":rid,"created":core.now(),"mode":"live","status":"未运行" if not provider.configured() else "running","test_set":dataset["version"],"test_set_sha256":hashlib.sha256((core.ROOT/"eval/live-cases.json").read_bytes()).hexdigest(),"catalog_sha256":hashlib.sha256(fixed.read_bytes()).hexdigest(),"catalog_version":core.catalog()["version"],"model":os.getenv("LLM_MODEL"),"provider":os.getenv("LLM_PROVIDER"),"commit":os.getenv("APP_COMMIT","unknown"),"prompt_sha256":hashlib.sha256((core.ROOT/"prompts"/(args.prompt+".txt")).read_bytes()).hexdigest(),"rows":{args.prompt:[]},"case_definitions":dataset["cases"],"execution":"真实 DeepSeek API + 固定商品夹具；不是实时商品搜索","holdout_note":"独立保留分组，但用例已公开，不宣称未见数据","manual_rubric":dataset["manual_rubric"],"manual_scores":None}
    report["evaluation_policy_version"]="whole-case-reservation-v2"
    report["tool_contract_version"]=tool_contracts.VERSION
    report["per_turn_request_limit"]=5
    report["code_files_sha256"]={n:provenance.sha(core.ROOT/n) for n in ("agent.py","tool_contracts.py","evaluate_live.py")}
    path=core.ROOT/"reports"/(rid+".json")
    store.init();initial=used();remaining=lambda:max(0,args.max_calls-(used()-initial))
    by_id={c["id"]:c for c in dataset["cases"]}
    requested=args.ids.split(",") if args.ids else list(by_id)
    if len(set(requested))!=len(requested) or any(i not in by_id for i in requested):raise SystemExit("Unknown or duplicate case ID; no requests sent.")
    for ident in requested:
        case=by_id[ident]
        if provider.configured():
            # Pass explicit fault only to this fixed evaluation; no production data mutation.
            original=agent.run
            def run(*a,**kw):return original(*a,**kw,fault=case.get("fault"))
            agent.run=run
            try:row=evaluate_case(case,args.prompt,remaining)
            finally:agent.run=original
        else:row={"id":case["id"],"split":case["split"],"mode":"live","skipped":True,"status":"not_run","reason":"未配置模型"}
        report["rows"][args.prompt].append(row)
        path.write_text(json.dumps(store.redact(report),ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({"case":row["id"],"passed":row.get("passed"),"calls":sum(t.get("model_calls",0) for t in row.get("traces",[])),"remaining_batch":remaining()},ensure_ascii=True),flush=True)
    report["ended_at"]=core.now();report["status"]="已运行" if provider.configured() else "未运行"
    report["requests_used"]=used()-initial
    traces=[t for row in report["rows"][args.prompt] for t in row.get("traces",[])]
    costs=[t.get("estimated_cost_cny") for t in traces]
    report["cost"]={"known_cny":sum(c for c in costs if c is not None),"unknown_runs":sum(c is None for c in costs),"price_source":os.getenv("LLM_PRICE_SOURCE"),"price_date":os.getenv("LLM_PRICE_DATE")}
    path.write_text(json.dumps(store.redact(report),ensure_ascii=False,indent=2),encoding="utf-8")
    print("Report: "+path.name,flush=True)
if __name__=="__main__":main()
