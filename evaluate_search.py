"""Repeatable before/after evaluation for the real-product retrieval pipeline."""
import argparse, json
from pathlib import Path
from urllib.parse import urlparse
import agent, core, provenance, search_provider

FIELDS=("name","price","source_url","evidence","collected_at")

def load_cases(path):return json.loads(Path(path).read_text(encoding="utf-8"))
def valid(row):
    try:
        return row["product"]["kind"] in ("verified","external") and bool(row["product"]["name"]) and \
            urlparse(row["offer"]["url"]).scheme=="https" and bool(row["product"]["evidence"][0]["excerpt"])
    except (KeyError,IndexError,TypeError):return False
def completeness(row):
    checks={"name":"name" in row.get("product",{}),"price":"price_minor" in row.get("offer",{}),
        "source_url":bool(row.get("offer",{}).get("url")),"evidence":bool(row.get("product",{}).get("evidence")),
        "collected_at":bool(row.get("offer",{}).get("captured_at"))}
    return sum(checks.values()),checks
def run_case(case,rows,source,request_id=None,credits=0):
    rows=rows[:5];valid_rows=[r for r in rows if valid(r)];field_hits=0;field_total=len(rows)*len(FIELDS)
    for row in rows:field_hits+=completeness(row)[0]
    outcome={"id":case["id"],"query":case["query"],"category":case["category"],"source":source,"request_id":request_id,"credits":credits,
        "returned":len(rows),"valid_top5":len(valid_rows),"covered":bool(valid_rows),"field_hits":field_hits,
        "field_total":field_total,"known_prices":sum(r["offer"]["price_minor"] is not None for r in rows),
        "agent_task_success":False,"hard_constraints_met":False,"failure":None}
    if not valid_rows:return outcome
    task=core.fresh_task("search-eval","real");task.update(currency="CNY",budget_minor=case["budget_minor"],owned=case.get("owned",[]),excluded=case.get("excluded",[]))
    try:
        core.cache_search(task,valid_rows,case["query"],source)
        ctx=agent.Context(task,searcher=None);chosen=valid_rows[0];oid=chosen["offer"]["id"]
        ctx.execute("read_evidence",{"offer_id":oid})
        ctx.execute("set_plan",{"items":[{"offer_id":oid,"quantity":1,"required":True,"reason":"检索评测：首个有效结果"}]})
        outcome["agent_task_success"]=True
        item=task["items"][0];product=item["snapshot"]["product"];offer=item["snapshot"]["offer"]
        outcome["hard_constraints_met"]=product["category"]==case["category"] and product["kind"]!="fixture" and \
            offer["currency"]=="CNY" and not core.totals(task)["over_budget"] and product["category"] not in task["owned"]+task["excluded"] and \
            task["confirmation"] is None and oid in ctx.read
    except core.AppError as error:outcome["failure"]={"category":error.category,"message":str(error)}
    return outcome
def metrics(rows):
    n=len(rows);hits=sum(r["field_hits"] for r in rows);total=sum(r["field_total"] for r in rows);returned=sum(r["returned"] for r in rows)
    rate=lambda a,b:round(a/b,4) if b else None
    return {"cases":n,"top5_valid_result_coverage_rate":rate(sum(r["covered"] for r in rows),n),
        "structured_field_completeness_rate":rate(hits,total),"known_price_rate":rate(sum(r["known_prices"] for r in rows),returned),
        "agent_task_success_rate":rate(sum(r["agent_task_success"] for r in rows),n),
        "hard_constraint_satisfaction_rate":rate(sum(r["hard_constraints_met"] for r in rows),n),
        "returned_results":returned,"provider_credits":sum(r.get("credits") or 0 for r in rows)}
def evaluate(cases,provider):
    before=[];after=[]
    for case in cases["cases"]:
        local=core.search("real",case["category"],case["query"])
        before.append(run_case(case,local,"local-catalog-before"))
        batch=provider.search(case["query"],5)
        normalized=search_provider.normalize(batch,case["category"],"CNY")
        after.append(run_case(case,normalized,batch.get("provider","external"),batch.get("request_id"),batch.get("credits")))
    b=metrics(before);a=metrics(after)
    return {"before":{"metrics":b,"cases":before},"after":{"metrics":a,"cases":after},
        "delta":{k:(round(a[k]-b[k],4) if isinstance(a.get(k),(int,float)) and isinstance(b.get(k),(int,float)) else None) for k in a}}
class FixtureProvider:
    name="fixture"
    def __init__(self,path):self.data=json.loads(Path(path).read_text(encoding="utf-8"))
    def search(self,query,max_results=5):return {"provider":"fixture","query":query,"request_id":None,"credits":0,"results":self.data.get(query,[])[:max_results]}
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--cases",default="eval/search-cases.json");parser.add_argument("--fixture");parser.add_argument("--output")
    args=parser.parse_args();cases=load_cases(args.cases);provider=FixtureProvider(args.fixture) if args.fixture else search_provider.get()
    result=evaluate(cases,provider);report={"version":"search-eval-v1","created_at":core.now(),"execution_mode":"fixture" if args.fixture else "external-live",
        "provider":provider.name,"cases_sha256":provenance.sha(Path(args.cases)),"definitions":{
        "top5_valid_result_coverage_rate":"有至少一个有效 Top-5 结果的案例数 / 全部案例数",
        "structured_field_completeness_rate":"返回结果中 name、price字段（可为null）、source_url、evidence、collected_at 的存在项 / 应有项",
        "agent_task_success_rate":"固定选择首个有效结果后，read_evidence 与 set_plan 均成功的案例数 / 全部案例数；不调用LLM",
        "hard_constraint_satisfaction_rate":"成功方案同时满足品类、非fixture、币种、预算、已有/排除、证据读取和未确认边界的案例数 / 全部案例数"},**result}
    target=Path(args.output or ("reports/search-eval-"+core.now().replace(":","").replace("-","")+".json"));target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"report":str(target),"mode":report["execution_mode"],"before":report["before"]["metrics"],"after":report["after"]["metrics"],"delta":report["delta"]},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
