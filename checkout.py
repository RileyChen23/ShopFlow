"""Confirmation-gated checkout adapters. Local demo is never a Shopify integration."""
import json, os, re
import core, store
from core import AppError, now

def verify(t):
    c=t.get("confirmation")
    if not c or c["fingerprint"]!=core.fingerprint(t):raise AppError("请先明确确认当前版本的商品与费用",409,"结算")
    if not t["items"]:raise AppError("方案为空",400,"结算")
    if core.totals(t)["over_budget"]:raise AppError("方案超预算",400,"结算")
    for i in t["items"]:
        if core.snapshot(i["offer_id"])!=i["snapshot"]:
            raise AppError("商品资料或价格已变化，请刷新报价并重新确认",409,"结算")
        until=i["snapshot"]["offer"].get("valid_until")
        if until and until<now():raise AppError("报价已过期，请先更新报价",409,"结算")

def prepare(owner,t,fault=None):
    verify(t)
    c,new=store.claim_cart(owner,t)
    if not new:
        if c["state"]=="ready":return json.loads(c["body"])
        raise AppError("本版本结算处理中或结果不确定；为避免重复提交，不自动重试。请核查运行记录。",409,"结算")
    try:
        if fault=="checkout":raise AppError("测试注入：结算失败，未创建购买入口；方案仍已保存。",503,"结算")
        groups={}
        for i in t["items"]:groups.setdefault(i["snapshot"]["offer"]["merchant"],[]).append(i)
        entries=[]
        for merchant,items in groups.items():
            kinds={i["snapshot"]["offer"]["purchase"] for i in items}
            if kinds=={"local_demo"}:
                entries.append({"merchant":merchant,"kind":"local_demo","label":"进入本地结算演练","url":"/checkout/"+c["id"]})
            elif kinds=={"shopify_test"}:
                entries.append(shopify(items,merchant))
            else:
                for i in items:
                    o=i["snapshot"]["offer"]
                    if o["purchase"]=="external" and o["url"]:
                        entries.append({"merchant":merchant,"kind":"external","label":"前往购买","url":core.safe_link(o["url"]),"offer_id":o["id"]})
                    else:entries.append({"merchant":merchant,"kind":"reference","label":"仅有资料，尚无购买入口","url":None,"offer_id":o["id"]})
        body={"id":c["id"],"task_id":t["id"],"revision":t["revision"],"entries":entries,"snapshot":core.public_task(t),"created":now(),
              "status":"已准备购买入口；不代表已付款","test_payment":False}
        store.finish_cart(c["id"],"ready",body)
        return body
    except Exception as e:
        store.finish_cart(c["id"],"uncertain",{"error":str(e) if isinstance(e,AppError) else "外部结算异常","created":now()})
        if isinstance(e,AppError):raise
        raise AppError("结算结果不确定，请核查商家后再操作；原方案已保存",502,"结算") from None

def shopify(items,merchant):
    from agent import post_json
    host=os.getenv("SHOPIFY_STORE","")
    token=os.getenv("SHOPIFY_STOREFRONT_TOKEN","")
    if os.getenv("SHOPIFY_TEST_STORE_ACK")!="1" or not re.fullmatch(r"[a-z0-9-]+\.myshopify\.com",host) or not token:
        raise AppError("测试店铺未配置：需要店铺域名、Storefront token，以及测试店铺确认",503,"结算")
    lines=[]
    for i in items:
        v=i["snapshot"]["variant"]
        if not v["sku"].startswith("TEST-") or not re.fullmatch(r"gid://shopify/ProductVariant/\d+",v.get("shopify_id","")):
            raise AppError("仅允许已导入的 TEST- SKU",400,"结算")
        lines.append({"merchandiseId":v["shopify_id"],"quantity":i["quantity"]})
    query="""mutation($input:CartInput!){cartCreate(input:$input){cart{id checkoutUrl lines(first:50){nodes{quantity merchandise{... on ProductVariant{id}}}} cost{subtotalAmount{amount currencyCode} totalAmount{amount currencyCode}}} userErrors{field message}}}"""
    r=post_json("https://"+host+"/api/"+os.getenv("SHOPIFY_API_VERSION","2026-07")+"/graphql.json",
                {"query":query,"variables":{"input":{"lines":lines}}},
                {"X-Shopify-Storefront-Access-Token":token},int(os.getenv("SHOPIFY_TIMEOUT_SECONDS","20")))
    payload=r.get("data",{}).get("cartCreate") or {}
    cart=payload.get("cart")
    if r.get("errors") or payload.get("userErrors") or not cart:raise AppError("Shopify 拒绝创建测试购物车",502,"结算")
    url=core.safe_link(cart["checkoutUrl"])
    from urllib.parse import urlparse
    if urlparse(url).hostname!=host:raise AppError("结算 URL 与配置店铺不一致，需人工核实",502,"结算")
    actual={n["merchandise"]["id"]:n["quantity"] for n in cart["lines"]["nodes"]}
    if actual!={x["merchandiseId"]:x["quantity"] for x in lines}:raise AppError("商家返回的购物车条目不一致",502,"结算")
    from decimal import Decimal
    subtotal=cart["cost"]["subtotalAmount"]
    expected=sum(i["snapshot"]["offer"]["price_minor"]*i["quantity"] for i in items)
    if subtotal["currencyCode"]!="CNY" or int(Decimal(subtotal["amount"])*100)!=expected:
        raise AppError("商家价格或币种已变化，需要重新导入报价并确认；不交接旧价格入口",409,"结算")
    # Keep cart secret on server; it is deliberately not included in return/logs.
    return {"merchant":merchant,"kind":"shopify_test","label":"进入测试店铺结算（不履约）","url":url,"cost":cart["cost"]}

def simulated_finish(owner,cid):
    c=store.get_cart(owner,cid)
    if c["state"]!="ready" or not any(e["kind"]=="local_demo" for e in c["body"].get("entries",[])):
        raise AppError("此购物车不是本地演练",400,"结算")
    t=store.get_task(owner,c["task_id"])
    if t["revision"]!=c["revision"]:raise AppError("原方案已变化，请重新确认创建演练购物车",409,"结算")
    c["body"]["status"]="本地演练完成；没有付款或真实订单"
    c["body"]["demo_completed_at"]=now()
    store.finish_cart(cid,"ready",c["body"])
    return c["body"]
