"""DeepSeek official non-thinking function tools adapter; no SDK or private reasoning logs."""
import os,time,datetime as dt,json
from urllib.parse import urlparse
import core,store

def configured():
    return bool(os.getenv("LLM_API_KEY") and os.getenv("LLM_MODEL") and os.getenv("LLM_BASE_URL"))

def payload(messages,tools):
    p={"model":os.getenv("LLM_MODEL"),"messages":messages,"tools":tools,"tool_choice":"auto",
       "max_tokens":min(int(os.getenv("LLM_MAX_OUTPUT_TOKENS","2000")),2000),"stream":False}
    if os.getenv("LLM_PROVIDER")=="deepseek":
        if os.getenv("LLM_THINKING","disabled")!="disabled":
            raise core.AppError("本适配器仅启用非思考模式；请设置 LLM_THINKING=disabled",503,"配置")
        p["thinking"]={"type":"disabled"}
    return p

def request(messages,tools,meta,post,deadline):
    limit=min(max(int(os.getenv("LLM_MAX_CALLS","8")),1),12)
    retries=min(max(int(os.getenv("LLM_MAX_RETRIES","1")),0),1)
    for attempt in range(retries+1):
        if meta["model_calls"]>=limit:raise core.AppError("达到本轮模型请求上限",429,"依赖故障")
        remaining=deadline-time.monotonic()
        if remaining<=0:raise core.AppError("本轮总耗时超过限制，方案未提交",504,"依赖故障")
        final_only=bool(meta.get("reserve_final_response")) and limit-meta["model_calls"]<=1
        effective_messages=messages
        if final_only and tools:
            effective_messages=messages+[{"role":"system","content":"Last request after retries: no tools; explain actual state or missing information only."}]
        body=payload(effective_messages,[] if final_only else tools)
        request_bytes=len(json.dumps(body,ensure_ascii=False).encode())
        max_request_bytes=min(max(int(os.getenv("LLM_MAX_REQUEST_BYTES","240000")),60000),500000)
        if request_bytes>max_request_bytes:raise core.AppError("完整模型请求超过本轮输入预算",429,"依赖故障")
        store.reserve_call();meta["model_calls"]+=1
        start=time.monotonic();stamp=core.now()
        event={"number":meta["model_calls"],"started_at":stamp,"status":"started","final_response_only":final_only,"request_bytes":request_bytes}
        meta["model_events"].append(event)
        try:
            r=post(os.getenv("LLM_BASE_URL").rstrip("/")+"/chat/completions",body,
                   {"Authorization":"Bearer "+os.getenv("LLM_API_KEY","")},min(float(os.getenv("LLM_TIMEOUT_SECONDS","35")),remaining))
            if not isinstance(r,dict):raise core.AppError("供应商响应不是对象，方案未提交",502,"依赖故障")
            event.update(status="success",response_id=r.get("id"),model=r.get("model"))
            usage=r.get("usage")
            normalized={k:usage.get(k) for k in ("prompt_tokens","completion_tokens","total_tokens","prompt_cache_hit_tokens","prompt_cache_miss_tokens")} if isinstance(usage,dict) else None
            meta["usage_reports"].append(normalized);event["usage"]=normalized
            event["estimated_cost_cny"]=cost(normalized,stamp) if os.getenv("LLM_PROVIDER")=="deepseek" else None
            return r
        except core.AppError as e:
            event.update(status="failed",error=str(e),usage_unknown=True)
            if getattr(e,"details",None):event["diagnostics"]=e.details
            meta["usage_reports"].append(None)
            if not getattr(e,"retryable",False) or attempt==retries or meta["model_calls"]>=limit:raise
            meta["retries"].append({"request":meta["model_calls"],"reason":str(e),"action":"重试模型请求"})
        finally:
            event["ended_at"]=core.now();event["ms"]=round((time.monotonic()-start)*1000,2);meta["model_ms"]+=event["ms"]

def cost(usage,stamp):
    if not isinstance(usage,dict) or not os.getenv("LLM_PRICE_DATE") or os.getenv("LLM_MODEL")!="deepseek-v4-flash":return None
    keys=("prompt_cache_hit_tokens","prompt_cache_miss_tokens","completion_tokens")
    if any(type(usage.get(k)) is not int or usage[k]<0 for k in keys):return None
    local=dt.datetime.fromisoformat(stamp).astimezone(dt.timezone(dt.timedelta(hours=8)))
    peak=local.weekday()<5 and (9<=local.hour<12 or 14<=local.hour<18)
    rates=(.10,3.,9.) if peak else (.05,1.5,4.5)
    return sum(usage[k]*r for k,r in zip(keys,rates))/1_000_000

def identity():
    return {"provider":os.getenv("LLM_PROVIDER") or "未记录","endpoint_host":urlparse(os.getenv("LLM_BASE_URL","")).hostname,
            "api_protocol":"chat-completions/function-tools","thinking":"disabled","stream":False}
