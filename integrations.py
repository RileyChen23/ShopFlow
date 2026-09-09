"""Small, explicit integration commands. Never performs real payments."""
import argparse, datetime as dt, json, os, re, time
from pathlib import Path
import core, agent, store

def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["check","model-smoke","import-catalog","shopify-import"])
    p.add_argument("--file")
    args=p.parse_args()
    if args.command=="check":
        print(json.dumps({"model":bool(os.getenv("LLM_API_KEY") and os.getenv("LLM_MODEL")),
                          "shopify":bool(os.getenv("SHOPIFY_STORE") and os.getenv("SHOPIFY_STOREFRONT_TOKEN")),
                          "test_ack":os.getenv("SHOPIFY_TEST_STORE_ACK")=="1",
                          "catalog":core.catalog()["version"]},indent=2));return
    if args.command=="import-catalog":
        if not args.file:raise SystemExit("--file required")
        data=core.load_catalog(args.file)
        target=core.ROOT/"data/catalog.json"
        target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        print("Validated catalog imported. Restart server to activate.");return
    if args.command=="model-smoke":
        if not os.getenv("LLM_API_KEY") or not os.getenv("LLM_MODEL"):
            print("BLOCKED: set LLM_API_KEY, LLM_MODEL, LLM_BASE_URL in .env locally.");return
        store.init()
        t=core.fresh_task("smoke");t["messages"]=[{"role":"user","content":"查找一个 300 元内的键盘，先读取依据再给方案。"}]
        updated,trace=agent.run(t,t["messages"][-1]["content"],{},mode="live")
        # No private credential values or headers appear in the saved trace.
        (core.ROOT/("reports/model-smoke-"+str(time.time_ns())+".json")).write_text(json.dumps(trace,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({"model_calls":trace["model_calls"],"tool_calls":trace["tool_calls"],
                          "items":len(updated["items"]),"tool_calling_verified":bool(trace["tool_calls"])},indent=2));return
    host=os.getenv("SHOPIFY_STORE","");token=os.getenv("SHOPIFY_STOREFRONT_TOKEN","")
    ids=os.getenv("SHOPIFY_TEST_VARIANT_IDS","").split(",")
    if not token or not re.fullmatch(r"[a-z0-9-]+\.myshopify\.com",host) or os.getenv("SHOPIFY_TEST_STORE_ACK")!="1":
        raise SystemExit("BLOCKED: configure a TEST store and acknowledge it in .env.")
    if not 1<=len(ids)<=2 or any(not re.fullmatch(r"gid://shopify/ProductVariant/\d+",x) for x in ids):
        raise SystemExit("Set SHOPIFY_TEST_VARIANT_IDS to 1-2 exact ProductVariant GIDs.")
    query="""query($ids:[ID!]!){nodes(ids:$ids){... on ProductVariant{id title sku availableForSale selectedOptions{name value} price{amount currencyCode} product{id title onlineStoreUrl productType} image{url altText}}}}"""
    data=agent.post_json("https://"+host+"/api/"+os.getenv("SHOPIFY_API_VERSION","2026-07")+"/graphql.json",
             {"query":query,"variables":{"ids":ids}},{"X-Shopify-Storefront-Access-Token":token},20)
    if data.get("errors"):raise SystemExit("Shopify query failed; no data imported.")
    nodes=data.get("data",{}).get("nodes",[])
    if len(nodes)!=len(ids) or any(not n for n in nodes):raise SystemExit("Variant missing; no data imported.")
    c=core.load_catalog();from decimal import Decimal
    stamp=core.now();expiry=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).isoformat()
    imported=[]
    for n in nodes:
        if not n["sku"].startswith("TEST-") or n["price"]["currencyCode"]!="CNY":
            raise SystemExit("Only TEST- SKU and CNY price are allowed.")
        cat=n["product"]["productType"]
        if cat not in agent.CATS:raise SystemExit("Set productType to supported Chinese category in store.")
        pid="shopify-"+n["product"]["id"].split("/")[-1]
        vid="shopify-v-"+n["id"].split("/")[-1];oid="shopify-o-"+n["id"].split("/")[-1]
        source=n["product"]["onlineStoreUrl"] or "https://"+host
        p={"id":pid,"kind":"shopify_test","brand":"测试店铺","name":n["product"]["title"],"category":cat,
           "attributes":{"variant":n["title"]},"limitations":["测试商品不销售、不履约；参数仅为店铺测试资料"],
           "image":n["image"]["url"] if n.get("image") else None,"image_source":source,
           "evidence":[{"fields":["name","attributes"],"url":source,"excerpt":"Shopify Storefront API 返回的测试商品记录","checked_at":stamp}]}
        v={"id":vid,"product_id":pid,"sku":n["sku"],"spec":" / ".join(x["name"]+": "+x["value"] for x in n["selectedOptions"]),"shopify_id":n["id"]}
        o={"id":oid,"variant_id":vid,"merchant":host,"price_minor":int(Decimal(n["price"]["amount"])*100),"currency":"CNY","shipping_minor":None,
           "stock":"available" if n["availableForSale"] else "out","price_kind":"test_store","captured_at":stamp,"valid_until":expiry,
           "url":n["product"]["onlineStoreUrl"],"purchase":"shopify_test","conditions":"采集时测试价格；有效期一小时。运费待测试结算核实。"}
        for key,value in [("products",p),("variants",v),("offers",o)]:
            c[key]=[x for x in c[key] if x["id"]!=value["id"]]+[value]
        imported.append(oid)
    c["version"]="catalog-shopify-"+stamp
    temp=core.ROOT/"runtime/catalog-import.json";temp.parent.mkdir(exist_ok=True)
    temp.write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding="utf-8");core.load_catalog(temp)
    (core.ROOT/"data/catalog.json").write_text(temp.read_text(encoding="utf-8"),encoding="utf-8")
    print("Imported test offers: "+", ".join(imported)+". Restart server; confirm in UI to create cart.")
if __name__=="__main__":main()
