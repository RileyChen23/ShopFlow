import copy,json,os,time,unittest
from pathlib import Path
from unittest.mock import patch
import core,agent,provider,store,tool_contracts,evaluate_live,maintenance

def t(scope="demo"):
    value=core.fresh_task("badcase-contract",scope);value["currency"]="CNY"
    value["messages"]=[{"role":"user","content":"budget and plan"}];return value
def line(oid="test-kbd1-o"):
    return {"offer_id":oid,"quantity":1,"required":True,"reason":"fixture"}
def response(name=None,args=None,answer=None):
    m={"role":"assistant","content":answer}
    if name:m["tool_calls"]=[{"id":"call-"+name,"type":"function","function":{"name":name,"arguments":json.dumps(args or {})}}]
    return {"choices":[{"message":m,"finish_reason":"tool_calls" if name else "stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2,"prompt_cache_hit_tokens":0,"prompt_cache_miss_tokens":1}}
class BadcaseContracts(unittest.TestCase):
 def setUp(self):
    self.env=patch.dict(os.environ,{"LLM_API_KEY":"test-only-not-real","LLM_PROVIDER":"deepseek","LLM_BASE_URL":"https://api.deepseek.com","LLM_MODEL":"deepseek-v4-flash","LLM_MAX_CALLS":"5","LLM_MAX_RETRIES":"1","LLM_THINKING":"disabled","LLM_PROMPT_VERSION":"live-bc-review"});self.env.start()
    self.reserve=patch.object(store,"reserve_call");self.reserve.start()
 def tearDown(self):self.reserve.stop();self.env.stop()
 def test_units_display_zero_unknown_currency_and_no_mutation(self):
    source={"budget_minor":50000,"currency":"CNY","offer":{"currency":"USD","price_minor":1299,"shipping_minor":None},"zero_minor":0}
    original=copy.deepcopy(source);view=tool_contracts.money_view(source)
    self.assertEqual(view["amounts"]["budget_minor"]["display"],"CNY 500.00")
    self.assertEqual(view["offer"]["amounts"]["price_minor"]["display"],"USD 12.99")
    self.assertIsNone(view["offer"]["amounts"]["shipping_minor"]["major_units"])
    self.assertEqual(view["amounts"]["zero_minor"]["major_units"],"0.00");self.assertEqual(source,original)
 def test_search_scope_counts_do_not_equal_subset(self):
    class Searcher:
      def search(self,q,n):return {"provider":"test","request_id":"r","credits":0,"results":[{"title":"K1","url":"https://example.com/k1","content":"wireless USB keyboard"}]}
    ctx=agent.Context(t("real"),searcher=Searcher());args={"category":"键盘","query":"键盘 无线 USB"}
    raw=ctx.execute("search_products",args);wire=tool_contracts.result(ctx,"search_products",raw,args)
    self.assertEqual((wire["scope_total"],wire["total"],wire["category_total"]),(None,None,None))
    self.assertEqual(wire["source"],"external_search");self.assertEqual(wire["matched"],1)
 def test_empty_search_is_not_failure(self):
    class Empty:
      def search(self,q,n):return {"provider":"test","request_id":"r","credits":0,"results":[]}
    ctx=agent.Context(t("real"),searcher=Empty());args={"category":"键盘","query":"unfindable-xyz"}
    wire=tool_contracts.result(ctx,"search_products",ctx.execute("search_products",args),args)
    self.assertEqual(wire["matched"],0);self.assertIsNone(wire["category_total"])
    with self.assertRaises(core.AppError):agent.Context(t(),fault="search").execute("search_products",args)
 def test_scope_authorization_never_authorizes_purchase(self):
    for scope,allowed in [("demo",True),("real",False)]:
      view=tool_contracts.task_view(t(scope))
      self.assertEqual(view["execution_policy"]["fixture_planning_allowed"],allowed)
      self.assertIsNone(view["confirmation"])
    with self.assertRaises(core.AppError):core.set_plan(t("real"),[line()])
 def test_budget_side_effect_returns_current_offer_ids(self):
    task=t();core.set_plan(task,[line(),line("test-lamp1-o")]);ctx=agent.Context(task)
    raw=ctx.execute("update_constraints",{"budget_minor":20000})
    wire=tool_contracts.result(ctx,"update_constraints",raw,{"budget_minor":20000})
    self.assertEqual([x["offer_id"] for x in wire["current_items"]],["test-kbd1-o"])
    with self.assertRaises(core.AppError):ctx.execute("update_item",{"offer_id":"test-lamp1-o","remove":True})
    self.assertEqual(task["items"][0]["offer_id"],"test-kbd1-o")
 def test_evidence_prerequisite_is_not_relaxed(self):
    task=t();ctx=agent.Context(task)
    staged=ctx.execute("set_plan",{"items":[line()]})
    self.assertEqual(task["items"],[]);self.assertEqual(staged["status"],"awaiting_evidence")
    ctx.execute("read_evidence",{"offer_id":"test-kbd1-o"})
    raw=ctx.recover_pending_plan();view=tool_contracts.result(ctx,"commit_pending_plan",raw,{})
    self.assertTrue(view["validation"]["budget_checked"]);self.assertFalse(view["validation"]["committed"]);self.assertFalse(view["validation"]["purchase_confirmed"])
 def test_evidence_failure_stages_and_recovers_same_plan_once(self):
    task=t();ctx=agent.Context(task)
    staged=ctx.execute("set_plan",{"items":[line()]})
    self.assertEqual(staged["missing_offer_ids"],["test-kbd1-o"]);self.assertTrue(staged["pending_plan_staged"])
    ctx.execute("read_evidence",{"offer_id":"test-kbd1-o"});result=ctx.recover_pending_plan()
    self.assertEqual(task["items"][0]["offer_id"],"test-kbd1-o");self.assertTrue(result["totals"])
    self.assertTrue(ctx.events[-1]["controller_recovery"]);self.assertIsNone(ctx.recover_pending_plan())
 def test_search_phase_closes_redundant_search_and_reports_fallback(self):
    ctx=agent.Context(t(),target_categories=["键盘"])
    args={"category":"键盘","query":"不存在于夹具的复杂形容词"};raw=ctx.execute("search_products",args);wire=tool_contracts.result(ctx,"search_products",raw,args)
    self.assertTrue(wire["items"]);self.assertTrue(wire["category_fallback"])
    names={x["function"]["name"] for x in agent.workflow_tools(ctx)}
    self.assertNotIn("search_products",names);self.assertIn("read_evidence",names);self.assertIn("set_plan",names)
    two=agent.Context(t(),target_categories=["键盘","台灯"]);two.execute("search_products",{"category":"键盘","query":"键盘"})
    search=next(x for x in agent.workflow_tools(two) if x["function"]["name"]=="search_products")
    self.assertEqual(search["function"]["parameters"]["properties"]["category"]["enum"],["台灯"])
 def test_existing_plan_routes_to_state_patch_tools(self):
    task=t();core.set_plan(task,[line(),line("test-lamp1-o")])
    kinds={"键盘数量改成2把":"quantity","换成蓝牙键盘":"replacement","台灯先不买，预算降到200元":"prune"}
    for text,kind in kinds.items():
      ctx=agent.Context(copy.deepcopy(task),target_categories=agent.categories(text),mutation_kind=agent.mutation_kind(text,task));names={x["function"]["name"] for x in agent.workflow_tools(ctx)}
      self.assertEqual(ctx.mutation_kind,kind)
      if kind in ("quantity","prune"):self.assertNotIn("search_products",names)
      if kind=="replacement":self.assertNotIn("update_item",names);self.assertIn("replace_item",names)
 def test_atomic_replace_preserves_unrelated_items(self):
    task=t();core.set_plan(task,[line(),line("test-lamp1-o")]);ctx=agent.Context(task)
    ctx.execute("read_evidence",{"offer_id":"test-kbd2-o"})
    ctx.execute("replace_item",{"old_offer_id":"test-kbd1-o","new_item":line("test-kbd2-o")})
    self.assertEqual([i["offer_id"] for i in task["items"]],["test-kbd2-o","test-lamp1-o"])
 def test_atomic_replace_failure_keeps_old_plan(self):
    task=t();task["budget_minor"]=16000;core.set_plan(task,[line()]);ctx=agent.Context(task)
    ctx.execute("read_evidence",{"offer_id":"test-mon1-o"})
    with self.assertRaises(core.AppError):ctx.execute("replace_item",{"old_offer_id":"test-kbd1-o","new_item":line("test-mon1-o")})
    self.assertEqual([i["offer_id"] for i in task["items"]],["test-kbd1-o"])
 def test_read_only_scope_schema_error_is_machine_readable(self):
    ctx=agent.Context(t())
    with self.assertRaises(core.AppError) as raised:ctx.execute("update_constraints",{"scope":"demo"})
    self.assertNotIn("scope",raised.exception.details["allowed_fields"]);self.assertIn("budget_minor",raised.exception.details["allowed_fields"])
 def test_validated_plan_survives_final_response_failure(self):
    calls=[{"id":"search","type":"function","function":{"name":"search_products","arguments":json.dumps({"category":"键盘","query":"键盘"})}}]
    planned=[
      {"id":"read","type":"function","function":{"name":"read_evidence","arguments":json.dumps({"offer_id":"test-kbd1-o"})}},
      {"id":"plan","type":"function","function":{"name":"set_plan","arguments":json.dumps({"items":[line()]})}}
    ]
    first={"choices":[{"message":{"role":"assistant","content":None,"tool_calls":calls},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2,"prompt_cache_hit_tokens":0,"prompt_cache_miss_tokens":1}}
    second={"choices":[{"message":{"role":"assistant","content":None,"tool_calls":planned},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2,"prompt_cache_hit_tokens":0,"prompt_cache_miss_tokens":1}}
    failure=core.AppError("final response unavailable",502,"依赖故障");failure.retryable=False
    with patch.dict(os.environ,{"LLM_MAX_CALLS":"3","LLM_MAX_RETRIES":"0","LLM_PROMPT_VERSION":"shopflow-v2"}),patch.object(agent,"post_json",side_effect=[first,second,failure]):
      task,trace=agent.run(t(),"预算300元买键盘",{},mode="live")
    self.assertEqual(task["items"][0]["offer_id"],"test-kbd1-o");self.assertEqual(trace["fallback"]["type"],"validated_state_summary")
    self.assertEqual(trace["status"],"partial");self.assertIn("购物方案",task["messages"][-1]["content"])
    self.assertNotIn("服务端",task["messages"][-1]["content"])
 def test_live_controller_recovers_plan_called_before_evidence(self):
    search_call={"id":"search","type":"function","function":{"name":"search_products","arguments":json.dumps({"category":"键盘","query":"键盘"})}}
    reversed_calls=[
      {"id":"plan","type":"function","function":{"name":"set_plan","arguments":json.dumps({"items":[line()]})}},
      {"id":"read","type":"function","function":{"name":"read_evidence","arguments":json.dumps({"offer_id":"test-kbd1-o"})}}
    ]
    replies=[
      {"choices":[{"message":{"role":"assistant","content":None,"tool_calls":[search_call]},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2,"prompt_cache_hit_tokens":0,"prompt_cache_miss_tokens":1}},
      {"choices":[{"message":{"role":"assistant","content":None,"tool_calls":reversed_calls},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2,"prompt_cache_hit_tokens":0,"prompt_cache_miss_tokens":1}},
      response(answer="方案已形成，等待用户确认。")]
    with patch.dict(os.environ,{"LLM_MAX_CALLS":"3","LLM_MAX_RETRIES":"0","LLM_PROMPT_VERSION":"shopflow-v2"}),patch.object(agent,"post_json",side_effect=replies):
      task,trace=agent.run(t(),"预算300元买键盘",{},mode="live")
    self.assertEqual(task["items"][0]["offer_id"],"test-kbd1-o")
    self.assertEqual([e["tool"] for e in trace["events"]],["search_products","set_plan","read_evidence","commit_pending_plan"])
    self.assertTrue(all(e["status"]=="success" for e in trace["events"]));self.assertTrue(trace["events"][-1]["controller_recovery"])
 def test_l02_final_slot_contains_results_and_no_tools(self):
    seen=[]
    replies=[response("search_products",{"category":"键盘","query":""}),response("read_evidence",{"offer_id":"test-kbd1-o"}),response("update_constraints",{"budget_minor":100000}),response("set_plan",{"items":[line()]}),response(answer="已生成演练键盘方案，未知运费。")]
    def post(url,payload,headers,timeout):
      seen.append(copy.deepcopy(payload));return replies[len(seen)-1]
    with patch.object(agent,"post_json",side_effect=post):task,trace=agent.run(t(),"plan",{},mode="live")
    self.assertEqual(len(seen),5);self.assertEqual(seen[-1]["tools"],[])
    result=json.loads(next(m["content"] for m in reversed(seen[-1]["messages"]) if m["role"]=="tool"))
    self.assertTrue(result["validation"]["budget_checked"]);self.assertEqual(len(task["items"]),1)
    self.assertEqual(trace["model_calls"],5);self.assertNotIn("check_plan",[e["tool"] for e in trace["events"]])
 def test_retry_cannot_reopen_tools_in_last_slot(self):
    failure=core.AppError("simulated transport",502);failure.retryable=True;seen=[]
    def post(url,payload,headers,timeout):
      seen.append(payload)
      if len(seen)==1:raise failure
      return response(answer="尚未形成方案。")
    with patch.dict(os.environ,{"LLM_MAX_CALLS":"2"}),patch.object(agent,"post_json",side_effect=post):
      _,trace=agent.run(t(),"plan",{},mode="live")
    self.assertTrue(seen[0]["tools"]);self.assertEqual(seen[1]["tools"],[])
    self.assertEqual(trace["model_calls"],2);self.assertEqual(len(trace["retries"]),1)
 def test_large_parallel_tool_batch_is_split_without_failing_turn(self):
    calls=[{"id":"check-"+str(i),"type":"function","function":{"name":"check_plan","arguments":"{}"}} for i in range(9)]
    first={"choices":[{"message":{"role":"assistant","content":None,"tool_calls":calls},"finish_reason":"tool_calls"}],
      "usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2,"prompt_cache_hit_tokens":0,"prompt_cache_miss_tokens":1}}
    with patch.dict(os.environ,{"LLM_MAX_CALLS":"2"}),patch.object(agent,"post_json",side_effect=[first,response(answer="Done.")]):
      task,trace=agent.run(t(),"Check the current plan.",{},mode="live")
    self.assertEqual(task["messages"][-1]["content"],"Done.")
    self.assertEqual(trace["tool_calls"],8)
    self.assertEqual(len(trace["events"]),9)
    self.assertEqual(trace["events"][-1]["status"],"skipped")
    self.assertEqual(trace["events"][-1]["model_result"]["error_code"],"tool_batch_limit")
 def test_insufficient_case_budget_does_not_call_model(self):
    case={"id":"TEST","name":"two turns","split":"development","messages":["one","two"],"expected":{}}
    with patch.object(agent,"run") as run:
      row=evaluate_live.evaluate_case(case,"live-bc-review",lambda:5)
    run.assert_not_called();self.assertTrue(row["resource_limited"]);self.assertEqual(row["traces"],[])
 def test_historical_state_gap_is_real_and_score_not_rewritten(self):
    r=json.loads((core.ROOT/"reports/live-eval-1788880562625025900.json").read_text(encoding="utf-8"))["rows"]["live-improved"][0]
    self.assertTrue(r["passed"]);self.assertEqual(r["result"]["owned"],[]);self.assertEqual(r["result"]["excluded"],[])
 def test_evidence_links_and_historical_hashes_resolve(self):
    import hashlib
    r=json.loads((core.ROOT/"reports/badcases.json").read_text(encoding="utf-8"))
    self.assertEqual(len(r["cases"]),8)
    for c in r["cases"]:
      for evidence in c["refs"]:
        path=core.ROOT/"reports"/(evidence["artifact"]+".json")
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),evidence["sha256"])
        body,_=maintenance.artifact(evidence["artifact"]);self.assertTrue(body)
