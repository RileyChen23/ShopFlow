import json, unittest
import core, evaluate_agent

class AgentEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads((core.ROOT/"eval/agent-benchmark.json").read_text(encoding="utf-8"))
    def test_benchmark_has_40_unique_cases_and_required_fields(self):
        cases=self.data["cases"];self.assertEqual(len(cases),40);self.assertEqual(len({c["case_id"] for c in cases}),40)
        for case in cases:
            for field in ("case_id","scenario","messages","expected_behavior","hard_constraints","tool_rules"):self.assertIn(field,case)
            self.assertTrue(case["messages"])
    def test_all_requested_scenario_families_are_covered(self):
        names={c["scenario"] for c in self.data["cases"]}
        self.assertEqual(names,{"正常组合采购","预算及硬约束","动态修改","信息不足与必要追问","约束冲突","搜索与信息异常","购买确认边界"})
    def test_constraint_scoring_uses_state_not_answer_text(self):
        task=core.fresh_task("score","demo");task["budget_minor"]=20000
        checks=[evaluate_agent.check_constraint(x,task) for x in [{"type":"budget_state","value":20000},{"type":"count","min":0,"max":0},{"type":"within_budget"}]]
        self.assertTrue(all(x["passed"] for x in checks))
    def test_fixed_search_empty_failure_and_normal_are_distinct(self):
        self.assertEqual(evaluate_agent.FixedSearch("empty").search("x")["results"],[])
        with self.assertRaises(core.AppError):evaluate_agent.FixedSearch("failure").search("x")
        self.assertEqual(len(evaluate_agent.FixedSearch().search("x")["results"]),1)
    def test_dynamic_score_requires_new_hard_constraints(self):
        first=core.fresh_task("score","demo");last=core.fresh_task("score","demo");last["budget_minor"]=10000
        row={"states":[first,last],"hard_constraints_passed":False}
        result=evaluate_agent.dynamic_score({"dynamic":{"changed":True}},row)
        self.assertFalse(result["passed"])
        self.assertIn("new_requirements_satisfied",[c["rule"] for c in result["checks"] if not c["passed"]])

if __name__=="__main__":unittest.main()
