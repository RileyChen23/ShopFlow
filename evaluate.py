"""Separate deterministic evidence from bounded real-model evaluation."""
import argparse, copy, hashlib, io, json, os, statistics, sys, time, unittest
import core, agent, store
sys.path.insert(0,str(core.ROOT/"tests"))
import test_system

def priority_case(case,version):
    t=core.fresh_task("eval");t["currency"]="CNY"
    optional=case["expected"].get("optional","test-stand1-o")
    core.set_plan(t,[test_system.line(optional,required=False),test_system.line(required=True)])
    t["budget_minor"]=20000;before=copy.deepcopy(t["items"])
    start=time.monotonic();core.repair_budget(t,version)
    kept=[i["offer_id"] for i in t["items"]]
    ok=case["expected"]["required_offer"] in kept
    return {"id":case["id"],"split":case["split"],"passed":ok,"category":None if ok else "推荐约束",
            "input":case["messages"],"before":[i["offer_id"] for i in before],"kept":kept,
            "latency_ms":round((time.monotonic()-start)*1000,2),"version":version,"mode":"deterministic"}

def run_case(case,mode,version):
    exp=case["expected"]
    if exp.get("scenario")=="priority":return priority_case(case,version)
    if exp.get("scenario"):
        cls=test_system.APITests if exp["scenario"]=="api" else test_system.DomainTests
        result=unittest.TestResult();unittest.TestSuite([cls(exp["test"])]).run(result)
        return {"id":case["id"],"split":case["split"],"passed":result.wasSuccessful(),"mode":"deterministic",
                "input":case["messages"],"test":exp["test"],"errors":[e[1] for e in result.errors+result.failures]}
    t=core.fresh_task("eval",exp.get("scope","demo"));t["currency"]="CNY";t["owned"]=exp.get("owned",[])
    traces=[];start=time.monotonic();error=None;assertions={}
    try:
        for message in case["messages"]:
            t["messages"].append({"role":"user","content":message})
            t,trace=agent.run(t,message,{},mode=mode,version=version,fault=exp.get("fault"));traces.append(trace)
        cats=[i["snapshot"]["product"]["category"] for i in t["items"]]
        assertions["budget"]=not core.totals(t)["over_budget"]
        assertions["no_confirmation"]=t["confirmation"] is None
        assertions["count"]=exp.get("min",0)<=len(t["items"])<=exp.get("max",12)
        if "categories" in exp:assertions["categories"]=set(cats)==set(exp["categories"])
        if "forbid_categories" in exp:assertions["exclusions"]=not set(cats)&set(exp["forbid_categories"])
        if exp.get("quantity"):assertions["quantity"]=all(i["quantity"]==exp["quantity"] for i in t["items"]) and bool(t["items"])
        if exp.get("clarify"):assertions["clarify"]="？" in t["messages"][-1]["content"] or "?" in t["messages"][-1]["content"]
        if exp.get("unknown"):assertions["unknown"]=core.totals(t)["final_total_minor"] is None
        if exp.get("compatibility"):assertions["compatibility"]=any("尚未核实" in x for x in core.compatibility(t))
        if exp.get("error"):assertions["expected_error"]=False
    except core.AppError as e:
        error={"message":str(e),"category":e.category};traces.append(getattr(e,"trace",{}))
        assertions["expected_error"]=exp.get("error")==e.category
    return {"id":case["id"],"split":case["split"],"passed":all(assertions.values()),"mode":mode,"version":version,
            "input":case["messages"],"assertions":assertions,"error":error,"result":core.public_task(t),"traces":traces,
            "latency_ms":round((time.monotonic()-start)*1000,2),"manual_scores":None}

def summarize(rows):
    timings=[r["latency_ms"] for r in rows if "latency_ms" in r]
    return {"total":len(rows),"passed":sum(r["passed"] for r in rows),"failed":sum(not r["passed"] for r in rows),
            "failures":[r["id"] for r in rows if not r["passed"]],
            "median_ms":statistics.median(timings) if timings else None,
            "cost_note":"离线规则不调用模型；这些数字不是模型效果或用户满意度"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=["offline","live"],default="offline")
    p.add_argument("--version",choices=["v1","v2","both"],default="both")
    p.add_argument("--split",choices=["development","holdout","all"],default="development")
    p.add_argument("--limit",type=int,default=3)
    args=p.parse_args();root=core.ROOT
    dataset=json.loads((root/"eval/cases.json").read_text(encoding="utf-8"))
    versions=["v1","v2"] if args.version=="both" else [args.version]
    base={"created":core.now(),"test_set":dataset["version"],"catalog_version":core.catalog()["version"],
          "catalog_sha256":hashlib.sha256((root/"data/catalog.json").read_bytes()).hexdigest(),
          "test_set_sha256":hashlib.sha256((root/"eval/cases.json").read_bytes()).hexdigest(),"commit":os.getenv("APP_COMMIT","unknown")}
    if args.mode=="live":
        raise SystemExit("Use evaluate_live.py --prompt live-baseline --max-calls N after approving the shared budget.")
    suite=unittest.defaultTestLoader.discover(str(root/"tests"));stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (root/("reports/system-tests-"+str(time.time_ns())+".txt")).write_text(stream.getvalue(),encoding="utf-8")
    rows={v:[run_case(c,"offline",v) for c in dataset["cases"]] for v in versions}
    comparison={}
    if len(versions)==2:
        one={r["id"]:r["passed"] for r in rows["v1"]};two={r["id"]:r["passed"] for r in rows["v2"]}
        comparison={"improved":[k for k in one if not one[k] and two[k]],"regressed":[k for k in one if one[k] and not two[k]]}
    report={**base,"system":{"total":result.testsRun,"passed":result.testsRun-len(result.failures)-len(result.errors),"failures":[str(x[0]) for x in result.failures+result.errors]},
            "live_status":"未运行","external_checkout":"未运行：缺测试店铺配置","real_transactions":"不可测，无可信订单回传",
            "iteration":{"description":"初版预算修复按检索顺序保留。开发案例 D07 的可选支架挤占必要键盘预算；v2 按必要性优先保留，在 H14 检查回归。这是确定性修复，不代表模型提升。",
                         **comparison,"evidence":{v:[r for r in rows[v] if r["id"] in ("D07","H14")] for v in versions},
                         "holdout_note":"固定案例首次执行后不据此调整本轮策略；尚未用于真实模型验证。"},
            "summaries":{v:{split:summarize([r for r in rs if r["split"]==split]) for split in ("development","holdout")} for v,rs in rows.items()},
            "rows":rows,"metrics":{"plan_validity":"仅为代码断言；依据正确性与主观质量仍需人工复核","checkout_handoff":"外部测试店铺分母为 0，成功率不可计算；本地演练见系统测试","dependency_failure":"系统测试验证保留状态，无假成功","real_sales":"不可测"}}
    (root/("reports/offline-"+str(time.time_ns())+".json")).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"system":report["system"],"summaries":report["summaries"],"comparison":comparison},ensure_ascii=True,indent=2))
    if not result.wasSuccessful():raise SystemExit(1)
if __name__=="__main__":main()
