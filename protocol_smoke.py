import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import agent,provider,core,store
store.init()
meta={"id":"protocol-"+str(time.time_ns()),"started_at":core.now(),"model_calls":0,"model_ms":0,"model_events":[],"usage_reports":[],"retries":[],"mode":"live",**provider.identity()}
deadline=time.monotonic()+140
try:
    p=[{"role":"user","content":"请只回复连接正常。"}]
    first=provider.request(p,[],meta,agent.post_json,deadline)
    meta["minimal_response"]=first["choices"][0]["message"].get("content")
    # Force one harmless read for protocol verification; task planning uses auto separately.
    tool=[x for x in agent.TOOLS if x["function"]["name"]=="get_task"]
    msgs=[{"role":"user","content":"你必须先调用 get_task 读取当前任务，然后根据工具返回告诉我预算金额，不能猜测。"}]
    response=provider.request(msgs,tool,meta,agent.post_json,deadline)
    message=response["choices"][0]["message"]
    calls=message.get("tool_calls") or []
    if not calls:raise core.AppError("模型未选择读取工具；协议冒烟未通过")
    task=core.fresh_task("protocol-smoke","real");task["budget_minor"]=50000
    ctx=agent.Context(task)
    msgs.append({k:message[k] for k in ("role","content","tool_calls") if k in message})
    for c in calls:
        if c["function"]["name"]!="get_task":raise core.AppError("非预期工具")
        raw=ctx.execute("get_task",json.loads(c["function"]["arguments"]))
        value=agent.tool_contracts.result(ctx,"get_task",raw,{})
        ctx.events[-1]["model_result"]=value
        msgs.append({"role":"tool","tool_call_id":c["id"],"content":json.dumps(value,ensure_ascii=False)})
    final=provider.request(msgs,[],meta,agent.post_json,deadline)
    meta.update(status="success",events=ctx.events,answer=final["choices"][0]["message"].get("content"),tool_result_returned=True,tools_selected=len(calls))
except core.AppError as e:meta.update(status="failed",error=str(e))
finally:
    meta["ended_at"]=core.now()
    path=core.ROOT/"reports"/(meta["id"]+".json")
    path.write_text(json.dumps(store.redact(meta),ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:meta.get(k) for k in ("status","model_calls","tools_selected","tool_result_returned","minimal_response","answer","error")},ensure_ascii=True))
    print("Report: "+path.name)

