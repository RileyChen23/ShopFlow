"""Explicit model-facing contracts. Domain values and persisted snapshots stay unchanged."""
import copy
from decimal import Decimal
import core
VERSION="agent-workflow-contract-v3"
def offer_summary(snapshot,include_evidence=False,include_source=False):
    product=snapshot["product"];variant=snapshot["variant"];offer=snapshot["offer"]
    value={"offer_id":offer["id"],"name":str(product["name"])[:220],"category":product["category"],
        "price_minor":offer.get("price_minor"),"currency":offer.get("currency"),
        "merchant":offer.get("merchant"),"stock":offer.get("stock"),
        "rating":product.get("attributes",{}).get("rating"),
        "ratings_total":product.get("attributes",{}).get("ratings_total")}
    if include_source or include_evidence:
        value["source_url"]=offer.get("url")
    if include_evidence:
        value["spec"]=str(variant.get("spec") or "")[:280]
        value["captured_at"]=offer.get("captured_at")
        value["evidence"]=[{"fields":e.get("fields",[]),"url":e.get("url"),
            "excerpt":str(e.get("excerpt") or "")[:420],"checked_at":e.get("checked_at")}
            for e in product.get("evidence",[])[:1]]
        value["limitations"]=product.get("limitations",[])[:3]
    return value
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
    out["agent_workflow"]={"ordered_phases":["search","read_evidence","set_or_patch_plan","explain"],"current_plan_offer_ids":[i["offer_id"] for i in t["items"]],
        "state_patch":"Use update_item for quantity/removal and replace_item for atomic replacement. Preserve unrelated items.",
        "evidence_recovery":"If set_plan reports evidence_required, read every missing_offer_id; the controller will retry the staged plan once.",
        "purchase_boundary":"No model tool can confirm, order or pay."}
    return out
def result(ctx,name,value,args):
    value=copy.deepcopy(value)
    currency=ctx.t.get("currency","CNY")
    if name=="search_products" and isinstance(value,list):
        compact_items=[offer_summary(item,include_source=True) for item in value]
        category=args.get("category","")
        if ctx.t["scope"]=="real":
            history=(ctx.t.get("search_history") or [{}])[-1]
            totals=(None,None,None);version="external:"+str(history.get("provider","unknown"));matching="product-page relevance filter"
        else:
            all_scope=core.search("demo");pool=[s for s in all_scope if s["offer"]["currency"]==currency]
            category_pool=[s for s in pool if not category or s["product"]["category"]==category]
            totals=(len(all_scope),len(pool),len(category_pool));version=core.catalog()["version"];matching="fixture text match"
        value={"items":compact_items,"scope":ctx.t["scope"],"source":"external_search" if ctx.t["scope"]=="real" else "demo_fixture",
            "currency":currency,"count_unit":"offers","catalog_version":version,
            "scope_total":totals[0],"total":totals[1],"category_total":totals[2],"matched":len(value),"returned":len(value),"truncated":False,
            "filters":{"category":category,"query":args.get("query","")},"matching":matching,
            "received":getattr(ctx,"last_search",{}).get("received") if ctx.t["scope"]=="real" else len(value),
            "rejected":getattr(ctx,"last_search",{}).get("rejected") if ctx.t["scope"]=="real" else 0,
            "returned_currencies":getattr(ctx,"last_search",{}).get("currencies",[currency]),
            "currency_mismatch":bool(getattr(ctx,"last_search",{}).get("currency_mismatch")),
            "currency_adjusted_from":getattr(ctx,"last_search",{}).get("currency_adjusted_from"),
            "currency_adjusted_to":getattr(ctx,"last_search",{}).get("currency_adjusted_to"),
            "result_scope":"current_query_only",
            "evidence_required_before_plan":True,
            "offer_ids":[item["offer"]["id"] for item in value],
            "category_fallback":bool(getattr(ctx,"last_search",{}) and ctx.last_search.get("category_fallback"))}
    if name=="read_evidence" and isinstance(value,dict) and {"product","variant","offer"}<=set(value):
        value=offer_summary(value,include_evidence=True)
    if name=="get_task":return task_view(ctx.t)
    if name=="update_constraints" and isinstance(value,dict) and not value.get("error"):
        value["current_items"]=[{k:i[k] for k in ("offer_id","quantity","required")} for i in ctx.t["items"]]
        value["constraints_applied"]=True
    if isinstance(value,dict) and value.get("ok") is False:
        value.setdefault("error_code","tool_validation_failed");value.setdefault("allowed_fields",[])
        value["recovery"]="Correct only the reported fields or prerequisite, then retry once; state is unchanged."
    if name in ("set_plan","commit_pending_plan","update_item","replace_item") and isinstance(value,dict) and "totals" in value:
        value["items"]=[{"offer_id":item["offer_id"],"quantity":item["quantity"],"required":item["required"],
            "reason":item["reason"],"name":item["snapshot"]["product"]["name"],
            "price_minor":item["snapshot"]["offer"].get("price_minor"),
            "currency":item["snapshot"]["offer"].get("currency")} for item in value.get("items",[])]
        value["validation"]={"budget_checked":True,"compatibility_checked":True,"plan_staged":True,"committed":False,"purchase_confirmed":False}
    return money_view(value,currency)
