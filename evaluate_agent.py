"""Run and deterministically score the fixed ShopFlow end-to-end Agent benchmark."""
import argparse, copy, hashlib, json, os, sqlite3, time
from pathlib import Path
from unittest.mock import patch
import agent, core, provider, provenance, search_provider, store, tool_contracts

class FixedSearch:
    name="benchmark-fixture"
    def __init__(self,mode="normal"):self.mode=mode
    def search(self,query,max_results=5):
        if self.mode=="failure":raise core.AppError("固定评测：外部搜索服务不可用",502,"检索")
        if self.mode=="empty":return {"provider":self.name,"request_id":"fixture-empty","credits":0,"results":[]}
        key=hashlib.sha256(query.encode()).hexdigest()[:12]
        return {"provider":self.name,"request_id":"fixture-"+key,"credits":0,"results":[{
            "title":"固定外部搜索候选："+query[:80],"url":"https://example.com/search-result/"+key,
            "content":"固定评测摘要。型号和价格需在来源页面复核；该内容只用于验证实时搜索后的工具链。"}]}

def budget_used():
    with sqlite3.connect(core.ROOT/"data/model-budget.sqlite3") as db:
        row=db.execute("SELECT used FROM budgets WHERE id=?",(os.getenv("LLM_BUDGET_ID"),)).fetchone()
        return row[0] if row else 0
def budget_remaining():
    with sqlite3.connect(core.ROOT/"data/model-budget.sqlite3") as db:
        row=db.execute("SELECT cap,used FROM budgets WHERE id=?",(os.getenv("LLM_BUDGET_ID"),)).fetchone()
        return max(0,row[0]-row[1]) if row else 0
def budget_state():
    with sqlite3.connect(core.ROOT/"data/model-budget.sqlite3") as db:
        row=db.execute("SELECT cap,used FROM budgets WHERE id=?",(os.getenv("LLM_BUDGET_ID"),)).fetchone()
        return {"cap":row[0],"used":row[1],"remaining":max(0,row[0]-row[1])} if row else {"cap":None,"used":None,"remaining":None}
def events(row):return [e for trace in row["traces"] for e in trace.get("events",[])]
def categories(task):return [i["snapshot"]["product"]["category"] for i in task["items"]]
def item_for(task,category):return next((i for i in task["items"] if i["snapshot"]["product"]["category"]==category),None)

def check_constraint(rule,task):
    typ=rule["type"];cats=categories(task);offers=[i["offer_id"] for i in task["items"]]
    if typ=="budget_state":actual=task["budget_minor"];ok=actual==rule["value"]
    elif typ=="within_budget":actual=core.totals(task)["over_budget"];ok=not actual
    elif typ=="count":actual=len(task["items"]);ok=rule.get("min",0)<=actual<=rule.get("max",99)
    elif typ=="category_present":actual=cats;ok=rule["value"] in cats
    elif typ=="category_absent":actual=cats;ok=rule["value"] not in cats
    elif typ=="categories_exact":actual=sorted(cats);ok=actual==sorted(rule["value"])
    elif typ=="offer_present":actual=offers;ok=rule["value"] in offers
    elif typ=="owned_contains":actual=task["owned"];ok=rule["value"] in actual
    elif typ=="owned_exact":actual=task["owned"];ok=actual==rule["value"]
    elif typ=="excluded_contains":actual=task["excluded"];ok=rule["value"] in actual
    elif typ=="recipient":actual=task["recipient"];ok=actual==rule["value"]
    elif typ=="quantity":
        item=item_for(task,rule["category"]);actual=item["quantity"] if item else None;ok=actual==rule["value"]
    elif typ=="known_total":actual=core.totals(task)["known_total_minor"];ok=actual==rule["value"]
    elif typ=="unknown_price":actual=core.totals(task)["unknown"];ok=any("价格未知" in x or "实时售价" in x for x in actual)
    elif typ=="unconfirmed":actual=task["confirmation"];ok=actual is None
    else:actual=None;ok=False
    return {"type":typ,"expected":{k:v for k,v in rule.items() if k!="type"},"actual":actual,"passed":ok}

def tool_score(case,row):
    ev=events(row);names=[e.get("tool") for e in ev];rules=case.get("tool_rules",{});checks=[]
    for name in rules.get("required",[]):checks.append({"rule":"required","tool":name,"passed":name in names})
    for name in rules.get("forbidden",[]):checks.append({"rule":"forbidden","tool":name,"passed":name not in names})
    last=[e.get("tool") for e in (row["traces"][-1].get("events",[]) if row["traces"] else [])]
    for name in rules.get("forbidden_last_turn",[]):checks.append({"rule":"forbidden_last_turn","tool":name,"passed":name not in last})
    expected_error=rules.get("expected_error")
    if expected_error:checks.append({"rule":"expected_error","category":expected_error,"passed":any(e.get("status")=="failed" and e.get("category")==expected_error for e in ev)})
    duplicates=[]
    for trace in row["traces"]:
        seen=set()
        for e in trace.get("events",[]):
            key=json.dumps([e.get("tool"),e.get("input")],sort_keys=True,ensure_ascii=False)
            if key in seen:duplicates.append(key)
            seen.add(key)
    checks.append({"rule":"no_duplicate_tool_and_args_within_turn","passed":not duplicates,"duplicates":duplicates})
    checks.append({"rule":"selected_items_have_successful_read_evidence","passed":all(any(e.get("tool")=="read_evidence" and e.get("status")=="success" and e.get("input",{}).get("offer_id")==i["offer_id"] for e in ev) for i in row["task"]["items"])})
    checks.append({"rule":"real_search_query_nonempty","passed":all(e.get("input",{}).get("query","").strip() for e in ev if e.get("tool")=="search_products" and case["scope"]=="real")})
    unexpected=[e for e in ev if e.get("status")=="failed" and (not expected_error or e.get("category")!=expected_error)]
    checks.append({"rule":"no_unexpected_tool_failure","passed":not unexpected,"failures":[{"tool":e.get("tool"),"category":e.get("category")} for e in unexpected]})
    return {"passed":all(c["passed"] for c in checks),"checks":checks}

def dynamic_score(case,row):
    rule=case.get("dynamic")
    if not rule:return None
    states=row["states"]
    if len(states)<2:return {"passed":False,"checks":[{"rule":"two_completed_turns","passed":False}]}
    first,last=states[0],states[-1];checks=[]
    checks.append({"rule":"state_changed","passed":first!=last})
    first_cats=categories(first);last_cats=categories(last)
    checks.append({"rule":"new_requirements_satisfied","passed":row["hard_constraints_passed"]})
    for cat in rule.get("removed",[]):checks.append({"rule":"removed_category","value":cat,"passed":cat in first_cats and cat not in last_cats})
    for oid in rule.get("removed_offer",[]):checks.append({"rule":"removed_offer","value":oid,"passed":any(i["offer_id"]==oid for i in first["items"]) and all(i["offer_id"]!=oid for i in last["items"])})
    for cat in rule.get("preserve",[]):checks.append({"rule":"preserved_category","value":cat,"passed":cat in first_cats and cat in last_cats})
    for cat in rule.get("preserve_offer",[]):
        a=item_for(first,cat);b=item_for(last,cat);checks.append({"rule":"preserved_offer","value":cat,"passed":bool(a and b and a["offer_id"]==b["offer_id"])})
    return {"passed":all(c["passed"] for c in checks),"checks":checks}

def boundary_score(case,row):
    ev=events(row);task=row["task"];violations=[]
    if task.get("confirmation") is not None:violations.append("model_set_confirmation")
    if any(e.get("tool") not in agent.SCHEMAS for e in ev):violations.append("unauthorized_tool")
    if core.totals(task)["over_budget"]:violations.append("over_budget_plan")
    if any(i["snapshot"]["product"]["category"] in task["owned"]+task["excluded"] for i in task["items"]):violations.append("owned_or_excluded_item")
    if case["scope"]=="real" and any(i["snapshot"]["product"]["kind"]=="fixture" for i in task["items"]):violations.append("fixture_in_real_scope")
    if any(not any(e.get("tool")=="read_evidence" and e.get("status")=="success" and e.get("input",{}).get("offer_id")==i["offer_id"] for e in ev) for i in task["items"]):violations.append("plan_without_evidence")
    return {"violated":bool(violations),"violations":violations}

def clarification_score(case,row):
    expected=case.get("clarification")
    if not expected:return None
    first=row["states"][0] if row["states"] else row["task"];first_trace=row["traces"][0] if row["traces"] else {};names=[e.get("tool") for e in first_trace.get("events",[])]
    if expected=="required":passed=not first["items"] and "set_plan" not in names and bool(row["answers"][0] if row["answers"] else "")
    else:passed=bool(first["items"])
    return {"expected":expected,"passed":passed,"observed_items":len(first["items"]),"tools":names}

def score_row(case,row):
    task=row["task"]
    row["hard_constraints"]=[check_constraint(r,task) for r in case.get("hard_constraints",[])]
    row["hard_constraints_passed"]=all(x["passed"] for x in row["hard_constraints"])
    row["tool_call_correctness"]=tool_score(case,row);row["dynamic_modification"]=dynamic_score(case,row)
    row["boundary"]=boundary_score(case,row);row["clarification"]=clarification_score(case,row)
    expected_error=case.get("tool_rules",{}).get("expected_error");run_error=row.get("run_error")
    run_ok=run_error is None or bool(expected_error and any(e.get("status")=="failed" and e.get("category")==expected_error for e in events(row)))
    row["task_success"]=run_ok and row["hard_constraints_passed"] and row["tool_call_correctness"]["passed"] and not row["boundary"]["violated"] and \
        (row["dynamic_modification"] is None or row["dynamic_modification"]["passed"]) and (row["clarification"] is None or row["clarification"]["passed"])
    return row

def evaluate_case(case,prompt,remaining):
    required=5*len(case["messages"])
    if remaining()<required:return {"case_id":case["case_id"],"scenario":case["scenario"],"status":"not_run","required_reservation":required,"traces":[],"states":[],"answers":[]}
    task=core.fresh_task("agent-benchmark",case["scope"]);task["currency"]="CNY"
    for key,value in case.get("initial",{}).items():task[key]=copy.deepcopy(value)
    traces=[];states=[];answers=[];run_error=None;searcher=FixedSearch(case.get("search_fixture","normal")) if case["scope"]=="real" else None
    for text in case["messages"]:
        task["messages"].append({"role":"user","content":text})
        try:
            if searcher:
                with patch.object(search_provider,"get",return_value=searcher):
                    task,trace=agent.run(task,text,{},mode="live",fault=case.get("fault"))
            else:task,trace=agent.run(task,text,{},mode="live",fault=case.get("fault"))
            traces.append(trace)
        except core.AppError as error:
            trace=getattr(error,"trace",{});traces.append(trace);run_error={"message":str(error),"category":error.category};break
        states.append(copy.deepcopy(task));answers.append(next((m["content"] for m in reversed(task["messages"]) if m["role"]=="assistant"),""))
    row={"case_id":case["case_id"],"scenario":case["scenario"],"status":"ran","messages":case["messages"],"expected_behavior":case["expected_behavior"],
        "task":task,"states":states,"answers":answers,"traces":traces,"run_error":run_error}
    return score_row(case,row)

def ratio(n,d):return {"numerator":n,"denominator":d,"rate":round(n/d,4) if d else None,"percent":round(100*n/d,1) if d else None}
def summarize(rows):
    ran=[r for r in rows if r.get("status")=="ran"];hard=[x for r in ran for x in r["hard_constraints"]];dynamic=[r for r in ran if r["dynamic_modification"] is not None];clar=[r for r in ran if r["clarification"] is not None]
    model_calls=sum(t.get("model_calls",0) for r in ran for t in r["traces"]);tool_calls=sum(len(t.get("events",[])) for r in ran for t in r["traces"])
    return {"task_success":ratio(sum(r["task_success"] for r in ran),len(ran)),"hard_constraint_item_satisfaction":ratio(sum(x["passed"] for x in hard),len(hard)),
        "hard_constraint_task_satisfaction":ratio(sum(r["hard_constraints_passed"] for r in ran),len(ran)),"dynamic_modification_success":ratio(sum(r["dynamic_modification"]["passed"] for r in dynamic),len(dynamic)),
        "tool_call_correctness":ratio(sum(r["tool_call_correctness"]["passed"] for r in ran),len(ran)),"boundary_violation":ratio(sum(r["boundary"]["violated"] for r in ran),len(ran)),
        "clarification_appropriateness":ratio(sum(r["clarification"]["passed"] for r in clar),len(clar)),"average_model_calls_per_task":round(model_calls/len(ran),2) if ran else None,
        "average_tool_calls_per_task":round(tool_calls/len(ran),2) if ran else None,"model_calls":model_calls,"tool_calls":tool_calls,"ran":len(ran),"not_run":len(rows)-len(ran)}

def is_local_daily_limit(row):
    error=row.get("run_error") or {}
    return error.get("message")=="已达到今日模型调用预算上限" and all(t.get("model_calls",0)==0 for t in row.get("traces",[]))

def finalize_report(report,by_id):
    report["rows"]=[score_row(by_id[row["case_id"]],row) for row in report["rows"]]
    total_cases=len(by_id)
    report["status"]="complete" if len({r["case_id"] for r in report["rows"] if r.get("status")=="ran"})==total_cases else "partial"
    report["summary"]=summarize(report["rows"])
    report["budget_reservations_used"]=sum(r.get("requests_used",0) for r in report.get("runs",[]))
    report["model_requests"]=report["summary"]["model_calls"]
    model_events=[e for row in report["rows"] for trace in row.get("traces",[]) for e in trace.get("model_events",[])]
    known=[e["estimated_cost_cny"] for e in model_events if isinstance(e.get("estimated_cost_cny"),(int,float))]
    report["cost"]={"known_cny":round(sum(known),6),"known_model_requests":len(known),"unknown_model_requests":len(model_events)-len(known),
        "source":os.getenv("LLM_PRICE_SOURCE"),"date":os.getenv("LLM_PRICE_DATE")}
    report["persistent_budget_at_finalize"]=budget_state()
    return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--benchmark",default="eval/agent-benchmark.json");parser.add_argument("--prompt",default="shopflow");parser.add_argument("--ids");parser.add_argument("--max-calls",type=int,default=240);parser.add_argument("--output");parser.add_argument("--resume",action="store_true");parser.add_argument("--finalize-only",action="store_true");parser.add_argument("--manual-review");parser.add_argument("--dry-run",action="store_true");args=parser.parse_args()
    data=json.loads(Path(args.benchmark).read_text(encoding="utf-8"));by_id={c["case_id"]:c for c in data["cases"]}
    path=Path(args.output) if args.output else core.ROOT/"reports"/("agent-eval-"+str(time.time_ns())+".json")
    previous=json.loads(path.read_text(encoding="utf-8")) if args.resume and path.is_file() else None
    if previous:
        invalid=[r for r in previous.get("rows",[]) if is_local_daily_limit(r)]
        if invalid:
            previous.setdefault("invalid_attempts",[]).append({"reason":"local_daily_limit_before_provider_request","case_ids":[r["case_id"] for r in invalid],"rows":invalid})
            previous["rows"]=[r for r in previous["rows"] if not is_local_daily_limit(r)]
    completed={r["case_id"] for r in previous.get("rows",[]) if r.get("status")=="ran"} if previous else set()
    ids=args.ids.split(",") if args.ids else [i for i in by_id if i not in completed]
    if len(ids)!=len(set(ids)) or any(i not in by_id for i in ids):raise SystemExit("Unknown or duplicate case ID")
    reservation=sum(5*len(by_id[i]["messages"]) for i in ids)
    if args.dry_run:print(json.dumps({"cases":len(ids),"already_completed":len(completed),"turns":reservation//5,"maximum_model_requests":reservation,"batch_cap":args.max_calls,"persistent_remaining":budget_remaining()},ensure_ascii=False));return
    if args.finalize_only:
        if not previous:raise SystemExit("--finalize-only requires an existing --output report")
        if args.manual_review:previous["manual_review"]=json.loads(Path(args.manual_review).read_text(encoding="utf-8"))
        finalize_report(previous,by_id);path.write_text(json.dumps(store.redact(previous),ensure_ascii=False,indent=2),encoding="utf-8");print("Report: "+str(path));return
    if not provider.configured():raise SystemExit("LLM is not configured")
    if args.resume and not previous:raise SystemExit("--resume requires an existing --output report")
    largest_case=max((5*len(by_id[i]["messages"]) for i in ids),default=0)
    if args.max_calls<largest_case:raise SystemExit(f"Batch cap {args.max_calls} cannot reserve the largest case ({largest_case}); no requests sent")
    if budget_remaining()<largest_case:raise SystemExit(f"Persistent budget cannot reserve the largest case ({largest_case}); no requests sent")
    os.environ["LLM_PROMPT_VERSION"]=args.prompt;os.environ["LLM_MAX_CALLS"]="5";store.init();start_used=budget_used()
    remaining=lambda:min(max(0,args.max_calls-(budget_used()-start_used)),budget_remaining())
    report=previous or {"id":"agent-eval-"+str(time.time_ns()),"version":"agent-eval-v1","evaluation_label":"eval-baseline-v1","started_at":core.now(),"status":"running","commit":provenance.commit(),"git_tag":"eval-baseline-v1","comparison_baseline":None,
        "comparison_baseline_reason":"当前提交被固定为 V1 baseline，供后续 V2 使用同一 benchmark 比较；仓库不存在可信的更早优化前 Agent 版本。",
        "benchmark":data["version"],"benchmark_sha256":provenance.sha(Path(args.benchmark)),"scoring":data["scoring"],"model":os.getenv("LLM_MODEL"),"provider":os.getenv("LLM_PROVIDER"),
        "prompt":args.prompt,"prompt_sha256":provenance.sha(core.ROOT/"prompts"/(args.prompt+".txt")),"temperature":"provider default","per_turn_max_calls":5,
        "search_execution":"fixed external-search response for real-scope cases; demo catalog for deterministic price cases","rows":[],"runs":[],"invalid_attempts":[],"manual_review":None}
    expected={"benchmark_sha256":provenance.sha(Path(args.benchmark)),"commit":provenance.commit(),"model":os.getenv("LLM_MODEL"),"provider":os.getenv("LLM_PROVIDER"),"prompt":args.prompt,"prompt_sha256":provenance.sha(core.ROOT/"prompts"/(args.prompt+".txt"))}
    mismatches={k:(report.get(k),v) for k,v in expected.items() if report.get(k)!=v}
    if mismatches:raise SystemExit("Resume configuration mismatch: "+json.dumps(mismatches,ensure_ascii=False))
    run={"started_at":core.now(),"case_ids":ids,"maximum_model_requests":reservation,"budget_used_before":start_used}
    report["status"]="running";report.setdefault("runs",[]).append(run)
    for ident in ids:
        row=evaluate_case(by_id[ident],args.prompt,remaining);report["rows"].append(row);path.write_text(json.dumps(store.redact(report),ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({"case":ident,"success":row.get("task_success"),"used":budget_used()-start_used,"remaining_batch":remaining()},ensure_ascii=False),flush=True)
    run["ended_at"]=core.now();run["requests_used"]=budget_used()-start_used;run["budget_used_after"]=budget_used()
    report["ended_at"]=core.now();finalize_report(report,by_id)
    path.write_text(json.dumps(store.redact(report),ensure_ascii=False,indent=2),encoding="utf-8");print("Report: "+str(path))
if __name__=="__main__":main()
