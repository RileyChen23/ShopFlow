import copy,json,os,time,unittest
from unittest.mock import patch
import core,agent,provider,store,maintenance

def task():
 t=core.fresh_task("contract","demo");t["currency"]="CNY";t["messages"]=[{"role":"user","content":"买键盘"}];return t
def response(calls=None,content=None):
 return {"choices":[{"finish_reason":"tool_calls" if calls else "stop","message":{"role":"assistant","content":content,"tool_calls":calls or []}}],"usage":{"prompt_tokens":10,"completion_tokens":3,"total_tokens":13,"prompt_cache_hit_tokens":0,"prompt_cache_miss_tokens":10}}
def call(name,args,ident="a"):
 return {"id":ident,"type":"function","function":{"name":name,"arguments":json.dumps(args)}}
class LiveContracts(unittest.TestCase):
 def setUp(self):
  self.env=patch.dict(os.environ,{"LLM_PROVIDER":"deepseek","LLM_BASE_URL":"https://api.deepseek.com","LLM_MODEL":"deepseek-v4-flash","LLM_API_KEY":"unit-test-placeholder","LLM_THINKING":"disabled","LLM_PROMPT_VERSION":"live-improved","LLM_MAX_CALLS":"5","LLM_PRICE_DATE":"2026-09-08"});self.env.start()
  self.reserve=patch.object(store,"reserve_call");self.reserve.start()
 def tearDown(self):self.reserve.stop();self.env.stop()
 def test_real_tool_result_returned_and_invalid_id_feedback(self):
  seen=[]
  def post(url,payload,headers,timeout):
   seen.append(copy.deepcopy(payload))
   if len(seen)==1:return response([call("read_evidence",{"offer_id":"invented"})])
   return response(content="商品资料读取失败，方案没有改变。")
  with patch.object(agent,"post_json",side_effect=post):
   t,r=agent.run(task(),"买键盘",{},mode="live")
  returned=json.loads(seen[1]["messages"][-1]["content"])
  self.assertFalse(returned["ok"]);self.assertEqual(t["items"],[])
  self.assertEqual(r["status"],"partial");self.assertEqual(r["model_calls"],2)
  self.assertTrue(r["started_at"]<=r["ended_at"]);self.assertEqual(r["events"][0]["status"],"failed")
 def test_malformed_provider_response_is_logged_without_private_details(self):
  with patch.object(agent,"post_json",return_value=[]):
   with self.assertRaises(core.AppError) as e:agent.run(task(),"键盘",{},mode="live")
  trace=e.exception.trace
  self.assertEqual(trace["status"],"failed");self.assertEqual(trace["model_calls"],1)
  self.assertEqual(trace["model_events"][0]["status"],"failed")
  self.assertIsNone(trace["estimated_cost_cny"])
 def test_no_silent_fallback(self):
  e=core.AppError("timeout",504);e.retryable=False
  with patch.object(agent,"post_json",side_effect=e):
   with self.assertRaises(core.AppError) as raised:agent.run(task(),"预算300买键盘",{},mode="live")
  self.assertEqual(raised.exception.trace["mode"],"live");self.assertIsNone(raised.exception.trace["fallback"])
 def test_retry_usage_unknown_not_zero(self):
  e=core.AppError("network",502);e.retryable=True
  with patch.object(agent,"post_json",side_effect=[e,response(content="请补充用途。")]):
   _,r=agent.run(task(),"用途",{},mode="live")
  self.assertEqual(r["model_calls"],2);self.assertEqual(len(r["retries"]),1);self.assertIsNone(r["estimated_cost_cny"])
 def test_loop_limit_does_not_commit_partial_state(self):
  original=task()
  with patch.dict(os.environ,{"LLM_MAX_CALLS":"1"}),patch.object(agent,"post_json",return_value=response([call("update_constraints",{"budget_minor":60000})])):
   with self.assertRaises(core.AppError):agent.run(original,"预算600",{},mode="live")
  self.assertIsNone(original["budget_minor"])
 def test_schema_error_rolls_back(self):
  t=task();ctx=agent.Context(t)
  with self.assertRaises(core.AppError):ctx.execute("update_constraints",{"budget_minor":True})
  self.assertIsNone(t["budget_minor"]);self.assertEqual(ctx.events[0]["status"],"failed")
 def test_update_quantity_without_search_and_invalidates_confirmation(self):
  t=task();core.set_plan(t,[{"offer_id":"test-kbd1-o","quantity":1,"required":True,"reason":"fixture"}]);t["confirmation"]={"anything":True}
  ctx=agent.Context(t);ctx.execute("update_item",{"offer_id":"test-kbd1-o","quantity":2})
  self.assertEqual(t["items"][0]["quantity"],2);self.assertIsNone(t["confirmation"]);self.assertEqual(len(ctx.events),1)
 def test_real_catalog_excludes_all_test_kinds(self):
  rows=core.search("real")
  self.assertGreaterEqual(len(rows),24);self.assertTrue(all(r["product"]["kind"]=="verified" for r in rows))
 def test_full_body_limit_before_reservation(self):
  meta={"model_calls":0}
  with self.assertRaises(core.AppError):provider.request([{"role":"user","content":"字"*60000}],[],meta,None,time.monotonic()+10)
  self.assertEqual(meta["model_calls"],0)
 def test_cost_zero_missing_and_peak(self):
  self.assertIsNone(provider.cost({},core.now()))
  u={"prompt_cache_hit_tokens":0,"prompt_cache_miss_tokens":0,"completion_tokens":0}
  self.assertEqual(provider.cost(u,core.now()),0)
  u["prompt_cache_miss_tokens"]=1000000
  self.assertEqual(provider.cost(u,"2026-09-08T02:00:00+00:00"),3)
  self.assertEqual(provider.cost(u,"2026-09-08T15:00:00+00:00"),1.5)
 def test_reasoning_not_stored(self):
  r=response(content="请明确用途。");r["choices"][0]["message"]["reasoning_content"]="PRIVATE"
  with patch.object(agent,"post_json",return_value=r):_,trace=agent.run(task(),"用途",{},mode="live")
  self.assertNotIn("PRIVATE",json.dumps(trace))
 def test_unconfigured_is_explicit(self):
  with patch.dict(os.environ,{"LLM_API_KEY":""}):
   with self.assertRaises(core.AppError) as e:agent.run(task(),"键盘",{},mode="live")
  self.assertEqual(e.exception.category,"配置")
 def test_report_download_cannot_traverse(self):
  for key in ["live-eval-../../.env","live-eval-1/../.env"]:
   with self.assertRaises(core.AppError):maintenance.artifact(key)
if __name__=="__main__":unittest.main()
import tempfile,sqlite3,contextlib
from pathlib import Path
from server import Handler
class MoreLiveContracts(unittest.TestCase):
 def test_search_alias_and_no_fixture_leak(self):
  self.assertTrue(core.search("real","键盘","罗技 蓝牙"))
  self.assertTrue(all(x["product"]["kind"]=="verified" for x in core.search("real")))
 def test_budget_shared_cap_survives_connections(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/"data").mkdir()
   with contextlib.closing(sqlite3.connect(root/"data/model-budget.sqlite3",isolation_level=None)) as d:
    d.execute("CREATE TABLE budgets(id TEXT PRIMARY KEY,cap INTEGER,used INTEGER)")
    d.execute("INSERT INTO budgets VALUES ('test-budget',1,0)")
   with patch.object(store,"DB_PATH",str(root/"task.sqlite")),patch.dict(os.environ,{"LLM_BUDGET_ID":"test-budget","LLM_DAILY_CALL_LIMIT":"99"}):
    store.init()
    with patch.object(store,"ROOT",root):store.reserve_call()
    with patch.object(store,"ROOT",root),self.assertRaises(core.AppError):store.reserve_call()
   with contextlib.closing(sqlite3.connect(root/"data/model-budget.sqlite3",isolation_level=None)) as d:self.assertEqual(d.execute("SELECT used FROM budgets").fetchone()[0],1)
 def test_cas_conflict_retains_model_trace_without_claiming_saved_result(self):
  original=task();original["revision"]=0
  pending=copy.deepcopy(original);pending["revision"]=1
  trace={"id":"trace-id","mode":"live","model_calls":2,"events":[{"tool":"get_task"}],"status":"success","result":{"old":True}}
  handler=Handler.__new__(Handler);handler.owner="contract"
  with patch.object(store,"get_task",return_value=original),patch.object(store,"preferences",return_value={}),patch.object(store,"save_task",side_effect=[pending,core.AppError("newer edit",409)]),patch.object(agent,"run",return_value=(pending,trace)),patch.object(store,"run_log") as logged:
   with self.assertRaises(core.AppError):handler.post("/api/chat",{"task_id":original["id"],"revision":0,"text":"change"})
  saved=logged.call_args.args[2]
  self.assertEqual(saved["model_calls"],2);self.assertEqual(saved["status"],"failed")
  self.assertIsNone(saved["committed_revision"]);self.assertNotIn("result",saved)
