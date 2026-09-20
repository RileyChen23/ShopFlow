import copy, json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import agent, core, evaluate_search, search_provider, tool_contracts

class FakeProvider:
    name="fake"
    def search(self,query,max_results=5):
        return {"provider":"fake","request_id":"request-1","credits":1,"query":query,"results":[
            {"title":"Logitech keyboard","url":"https://shop.example.com/kbd","content":"Wireless USB keyboard; price not verified."}]}

class FakeRainforest(search_provider.RainforestSearchProvider):
    def search(self,query,max_results=5,currency="USD"):
        return {"provider":"rainforest","amazon_domain":"amazon.com","results":[{
            "position":1,"asin":"B000USD001","title":"A5 Notebook 20 Pack",
            "link":"https://www.amazon.com/dp/B000USD001","image":"https://m.media-amazon.com/notebook.jpg",
            "price":{"value":17.84,"currency":"USD","raw":"$17.84"}}]}

class ExternalSearchTests(unittest.TestCase):
    def test_fallback_reply_matches_latest_user_language(self):
        task=core.fresh_task("language","real");ctx=agent.Context(task)
        self.assertIn("没有找到",agent.state_fallback(ctx,"我想买一个键盘"))
        self.assertIn("couldn't find",agent.state_fallback(ctx,"I need a keyboard"))

    def test_language_detection_does_not_depend_on_ui_locale(self):
        self.assertTrue(agent.prefers_chinese("预算 100 美元，想买键盘"))
        self.assertFalse(agent.prefers_chinese("A keyboard under $100"))

    def test_normalize_preserves_required_schema_and_unknown_price(self):
        rows=search_provider.normalize(FakeProvider().search("keyboard"),"键盘","CNY","2026-09-09T00:00:00+00:00")
        self.assertEqual(len(rows),1);row=rows[0]
        self.assertEqual(row["product"]["kind"],"external");self.assertIsNone(row["offer"]["price_minor"])
        self.assertEqual(row["offer"]["url"],row["product"]["evidence"][0]["url"])
        self.assertEqual(row["offer"]["captured_at"],"2026-09-09T00:00:00+00:00")
    def test_rainforest_result_keeps_asin_price_image_and_source(self):
        batch={"provider":"rainforest","amazon_domain":"amazon.com","max_results":5,"results":[{
            "position":1,"asin":"B000TEST01","title":"Logitech K120 Wired Keyboard",
            "link":"https://www.amazon.com/Logitech-Keyboard/dp/B000TEST01/ref=sr_1_1?keywords=keyboard","image":"https://m.media-amazon.com/test.jpg",
            "price":{"value":79.9,"currency":"CNY","raw":"CN¥79.90"},"rating":4.5,"ratings_total":1200}]}
        rows=search_provider.normalize(batch,"键盘","CNY","2026-09-19T00:00:00+00:00")
        self.assertEqual(len(rows),1);row=rows[0]
        self.assertEqual(row["variant"]["sku"],"B000TEST01")
        self.assertEqual(row["offer"]["price_minor"],7990)
        self.assertEqual(row["offer"]["currency"],"CNY")
        self.assertEqual(row["offer"]["url"],"https://www.amazon.com/dp/B000TEST01")
        self.assertEqual(row["product"]["image"],"https://m.media-amazon.com/test.jpg")
        self.assertEqual(row["product"]["evidence"][0]["url"],row["offer"]["url"])
    def test_real_search_caches_then_existing_evidence_and_plan_tools_work(self):
        task=core.fresh_task("external","real");ctx=agent.Context(task,searcher=FakeProvider())
        rows=ctx.execute("search_products",{"category":"键盘","query":"wireless keyboard China"})
        oid=rows[0]["offer"]["id"]
        self.assertIn(oid,task["search_cache"]);self.assertEqual(task["search_history"][-1]["request_id"],"request-1")
        cached=core.public_task(task)["cached_offers"][0]
        self.assertEqual(cached["name"],"Logitech keyboard");self.assertIn("price_minor",cached)
        self.assertEqual(cached["source_url"],"https://shop.example.com/kbd")
        evidence=ctx.execute("read_evidence",{"offer_id":oid});self.assertEqual(evidence["product"]["kind"],"external")
        result=ctx.execute("set_plan",{"items":[{"offer_id":oid,"quantity":1,"required":True,"reason":"test"}]})
        self.assertEqual(result["items"][0]["offer_id"],oid);self.assertTrue(any(x.startswith("商品价格未知") for x in result["totals"]["unknown"]))
    def test_ranked_search_can_recover_an_editable_draft(self):
        task=core.fresh_task("external","real");task["currency"]="CNY"
        ctx=agent.Context(task,searcher=FakeProvider())
        rows=ctx.execute("search_products",{"category":"键盘","query":"wired classroom keyboard"})
        self.assertTrue(agent.commit_ranked_draft(ctx,"先买 2 个键盘"))
        self.assertEqual(task["items"][0]["offer_id"],rows[0]["offer"]["id"])
        self.assertEqual(task["items"][0]["quantity"],2)
        self.assertTrue(ctx.plan_updated)
    def test_unbudgeted_empty_real_task_adopts_provider_currency(self):
        task=core.fresh_task("external","real");task["currency"]="CNY"
        ctx=agent.Context(task,searcher=FakeRainforest())
        ctx.execute("search_products",{"category":"","query":"A5 notebook 20 pack"})
        self.assertEqual(task["currency"],"USD")
        self.assertEqual(ctx.last_search["currency_adjusted_from"],"CNY")
        self.assertFalse(ctx.last_search["currency_mismatch"])
        wire=tool_contracts.result(ctx,"search_products",list(task["search_cache"].values()),{"category":"","query":"A5 notebook"})
        self.assertIn("offer_id",wire["items"][0]);self.assertNotIn("product",wire["items"][0])
        self.assertNotIn("source_url",wire["items"][0]);self.assertNotIn("spec",wire["items"][0])
        self.assertLess(len(json.dumps(wire)),3000)
        evidence=ctx.execute("read_evidence",{"offer_id":wire["items"][0]["offer_id"]})
        evidence_wire=tool_contracts.result(ctx,"read_evidence",evidence,{"offer_id":wire["items"][0]["offer_id"]})
        self.assertIn("source_url",evidence_wire);self.assertIn("spec",evidence_wire)
    def test_explicit_budget_keeps_currency_and_blocks_mixed_plan(self):
        task=core.fresh_task("external","real");task["currency"]="CNY";task["budget_minor"]=10000
        ctx=agent.Context(task,searcher=FakeRainforest())
        ctx.execute("search_products",{"category":"","query":"A5 notebook 20 pack"})
        self.assertEqual(task["currency"],"CNY")
        self.assertEqual(ctx.currency_blocked["offer_currencies"],["USD"])
    def test_real_mode_never_uses_local_catalog(self):
        task=core.fresh_task("external","real");ctx=agent.Context(task,searcher=FakeProvider())
        with patch.object(core,"search",side_effect=AssertionError("local catalog used")):
            self.assertTrue(ctx.execute("search_products",{"category":"键盘","query":"keyboard"}))
    def test_search_failure_rolls_back_cache(self):
        class Broken:
            def search(self,*args):raise core.AppError("provider down",502,"检索")
        task=core.fresh_task("external","real");before=copy.deepcopy(task)
        with self.assertRaises(core.AppError):agent.Context(task,searcher=Broken()).execute("search_products",{"category":"键盘","query":"keyboard"})
        self.assertEqual(task,before)
    def test_fixture_before_after_report_is_repeatable_and_labelled(self):
        cases=evaluate_search.load_cases(core.ROOT/"eval/search-cases.json")
        provider=evaluate_search.FixtureProvider(core.ROOT/"eval/search-provider-fixture.json")
        a=evaluate_search.evaluate(cases,provider);b=evaluate_search.evaluate(cases,provider)
        self.assertEqual(a,b);self.assertEqual(a["after"]["metrics"]["top5_valid_result_coverage_rate"],1)
        self.assertEqual(a["after"]["metrics"]["structured_field_completeness_rate"],1)
        self.assertEqual(a["after"]["metrics"]["agent_task_success_rate"],1)
        self.assertEqual(a["after"]["metrics"]["hard_constraint_satisfaction_rate"],1)
    def test_missing_provider_key_is_explicit(self):
        with patch.dict(os.environ,{"RAINFOREST_API_KEY":""}),self.assertRaises(core.AppError) as error:
            search_provider.RainforestSearchProvider().search("keyboard")
        self.assertEqual(error.exception.category,"配置")

if __name__=="__main__":unittest.main()
