"""Explicit model-facing contracts. Domain values and persisted snapshots stay unchanged."""
import copy
from decimal import Decimal
import core
VERSION="badcase-contract-v1"
def money_view(value,currency="CNY"):
    if isinstance(value,list):return [money_view(x,currency) for x in value]
    if not isinstance(value,dict):return value
    currency=value.get("currency",currency)
    out={k:money_view(v,currency) for k,v in value.items()}
    amounts={}
    for key,amount in value.items():
        if key.endswith("_minor") and (amount is None or type(amount) is int):
            major=None if amount is None else format(Decimal(amount)/Decimal(100),".2f")
            amounts[key]={"minor_units":amount,"major_units":major,"currency":currency,"scale":100,"display":"未知" if major is None else currency+" "+major}
    if amounts:out["amounts"]=amounts
    return out
def task_view(t):
    out=money_view(core.public_task(t),t.get("currency","CNY"))
    out["execution_policy"]={"scope":t["scope"],"purpose":"local_simulation" if t["scope"]=="demo" else "real_catalog_planning","fixture_planning_allowed":t["scope"]=="demo","purchase_confirmation":"separate_explicit_user_action_only","unknown_price_is_zero":False}
    return out
def result(ctx,name,value,args):
    value=copy.deepcopy(value)
    currency=ctx.t.get("currency","CNY")
    if name=="search_products" and isinstance(value,list):
        all_scope=core.search(ctx.t["scope"])
        pool=[s for s in all_scope if s["offer"]["currency"]==currency]
        category=args.get("category","")
        category_pool=[s for s in pool if not category or s["product"]["category"]==category]
        value={"items":value,"scope":ctx.t["scope"],"currency":currency,"count_unit":"offers","catalog_version":core.catalog()["version"],
            "scope_total":len(all_scope),"total":len(pool),"category_total":len(category_pool),"matched":len(value),"returned":len(value),"truncated":False,
            "filters":{"category":category,"query":args.get("query","")},"matching":"whitespace-separated terms, all must match; not semantic search",
            "interpretation":"matched describes this filter only, not all catalog coverage. Empty match is not a service failure.",
            "evidence_required_before_plan":True}
    if name=="get_task":return task_view(ctx.t)
    if name=="update_constraints" and isinstance(value,dict) and not value.get("error"):
        value["current_items"]=[{k:i[k] for k in ("offer_id","quantity","required")} for i in ctx.t["items"]]
        value["side_effects"]="Owned/excluded filters and budget repair already applied; removed contains names, current_items contains remaining offer IDs."
    if name in ("set_plan","update_item") and isinstance(value,dict) and "totals" in value:
        value["validation"]={"budget_checked":True,"compatibility_checked":True,"plan_staged":True,"committed":False,"purchase_confirmed":False}
        value["next_action"]="Explain this validated result; check_plan is redundant unless state changes."
    return money_view(value,currency)
