"""Deterministic domain tools. All prices are integer minor units."""
import copy, datetime as dt, hashlib, json, os, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent

class AppError(Exception):
    def __init__(self, message, status=400, category="状态更新"):
        super().__init__(message)
        self.status, self.category = status, category

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def load_env():
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

load_env()

def integer(v, low=0, high=100000000):
    if type(v) is not int or not low <= v <= high:
        raise AppError(f"整数必须在 {low}—{high} 范围内", category="计算")
    return v

def validate(value, schema, path="$"):
    typ = schema.get("type")
    checks = {"object": lambda v:type(v) is dict, "array": lambda v:type(v) is list,
              "string":lambda v:type(v) is str, "integer":lambda v:type(v) is int,
              "boolean":lambda v:type(v) is bool, "null":lambda v:v is None}
    if typ and not any(checks[t](value) for t in (typ if isinstance(typ,list) else [typ])):
        raise AppError(f"{path}: 类型不符合工具 schema", category="需求理解")
    if "enum" in schema and value not in schema["enum"]:
        raise AppError(f"{path}: 值不在允许范围", category="需求理解")
    if isinstance(value, dict):
        for k in schema.get("required",[]):
            if k not in value: raise AppError(f"{path}: 缺少 {k}")
        for k,v in value.items():
            if k not in schema.get("properties",{}):
                if schema.get("additionalProperties") is False: raise AppError(f"{path}: 不接受字段 {k}")
            else: validate(v,schema["properties"][k],path+"."+k)
    if isinstance(value,list):
        if len(value)>schema.get("maxItems",100): raise AppError("列表过长")
        for i,v in enumerate(value): validate(v,schema.get("items",{}),f"{path}[{i}]")
    if isinstance(value,str) and len(value)>schema.get("maxLength",4000): raise AppError("文本过长")
    if type(value) is int:
        integer(value,schema.get("minimum",0),schema.get("maximum",100000000))

def safe_link(url):
    from urllib.parse import urlparse
    import ipaddress
    p=urlparse(url)
    if p.scheme!="https" or not p.hostname or p.username or p.password or p.port not in (None,443):
        raise AppError("仅接受公开 HTTPS 链接", category="检索")
    host=p.hostname.lower()
    if host=="localhost" or "." not in host or host.endswith((".local",".internal",".localhost")):
        raise AppError("禁止私网链接", category="检索")
    try:
        addr=ipaddress.ip_address(host)
        if not addr.is_global: raise AppError("禁止私网链接", category="检索")
    except ValueError: pass
    return url

def load_catalog(path=None):
    data=json.loads(Path(path or ROOT/"data/catalog.json").read_text(encoding="utf-8-sig"))
    ids=set()
    for p in data["products"]:
        if p["id"] in ids: raise AppError("商品 ID 重复")
        ids.add(p["id"])
        if p["kind"] not in ("verified","fixture","shopify_test"): raise AppError("数据类型错误")
        if not p.get("evidence"): raise AppError("商品缺少依据")
        for e in p["evidence"]:
            if e.get("url"): safe_link(e["url"])
    vids=set()
    for v in data["variants"]:
        if v["product_id"] not in ids or v["id"] in vids: raise AppError("规格身份错误")
        vids.add(v["id"])
    oids=set()
    for o in data["offers"]:
        if o["variant_id"] not in vids or o["id"] in oids: raise AppError("报价身份错误")
        oids.add(o["id"])
        if o["price_minor"] is not None: integer(o["price_minor"])
        if o["shipping_minor"] is not None: integer(o["shipping_minor"])
        if o["url"]: safe_link(o["url"])
        if o["currency"] not in ("CNY","GBP","USD"): raise AppError("币种不支持")
    return data

CATALOG=load_catalog() if (ROOT/"data/catalog.json").exists() else None

def catalog():
    global CATALOG
    if CATALOG is None: CATALOG=load_catalog()
    return CATALOG

def snapshot(offer_id, task=None):
    if task:
        cached=(task.get("search_cache") or {}).get(offer_id)
        if cached:return copy.deepcopy(cached)
    c=catalog()
    o=next((x for x in c["offers"] if x["id"]==offer_id),None)
    if not o: raise AppError("报价不存在",404,"检索")
    v=next(x for x in c["variants"] if x["id"]==o["variant_id"])
    p=next(x for x in c["products"] if x["id"]==v["product_id"])
    return copy.deepcopy({"product":p,"variant":v,"offer":o})

def search_text(value):
    text=json.dumps(value,ensure_ascii=False).lower() if not isinstance(value,str) else value.lower()
    text=text.replace("蓝牙","bluetooth").replace("罗技","logitech").replace("小米","xiaomi").replace("绿联","ugreen")
    text=re.sub(r"usb[\s－—-]*([ac])",r"usb\1",text)
    return text.replace("×","x").replace("–","-")

def search(scope, category="", query=""):
    rows=[]
    for o in catalog()["offers"]:
        s=snapshot(o["id"]); p=s["product"]
        if p["kind"] != {"demo":"fixture","real":"verified","shopify_test":"shopify_test"}.get(scope): continue
        if category and p["category"]!=category: continue
        if query and not all(w in search_text(s) for w in search_text(query).split()): continue
        rows.append(s)
    return rows

def fresh_task(owner,scope="demo",pref=None):
    import uuid
    return {"id":uuid.uuid4().hex,"owner":owner,"revision":0,"title":"新的采购任务","scope":scope,
            "budget_minor":None,"recipient":"self","owned":list((pref or {}).get("owned",[])),
            "excluded":[],"constraints":[],"items":[],"messages":[],"confirmation":None,
            "search_cache":{},"search_history":[],
            "status":"规划中","created":now()}

def cache_search(t,snapshots,query,provider,request_id=None,credits=None):
    cache=t.setdefault("search_cache",{})
    for row in snapshots:cache[row["offer"]["id"]]=copy.deepcopy(row)
    # Keep selected plan evidence and the newest external results, bounded per task.
    keep={i["offer_id"] for i in t.get("items",[])}
    for oid in list(cache)[:-30]:
        if oid not in keep:cache.pop(oid,None)
    t.setdefault("search_history",[]).append({"query":query,"provider":provider,"request_id":request_id,
        "credits":credits,"result_count":len(snapshots),"collected_at":now()})
    t["search_history"]=t["search_history"][-10:]
    return snapshots

def totals(t):
    subtotal=0; unknown=[]; shipping={}; currency=None
    for item in t["items"]:
        o=item["snapshot"]["offer"]; integer(item["quantity"],1,99)
        if currency and currency!=o["currency"]: raise AppError("不同币种不能合并计算",category="计算")
        currency=o["currency"]
        if o["price_minor"] is None: unknown.append("商品价格未知："+o["id"])
        else: subtotal+=integer(o["price_minor"])*item["quantity"]
        # Each offer's shipping is a separate known per-line delivery charge.
        shipping[o["id"]]=o["shipping_minor"]
        if o["shipping_minor"] is None: unknown.append("运费未知："+o["merchant"])
        if o["stock"]=="unknown": unknown.append("库存未知："+o["id"])
        if o["price_kind"]=="unknown": unknown.append("未获取实时售价")
        if o.get("valid_until") and o["valid_until"] < now(): unknown.append("报价已过期："+o["id"])
    known_shipping=sum(x for x in shipping.values() if x is not None)
    known=subtotal+known_shipping
    return {"subtotal_minor":subtotal,"shipping_known_minor":known_shipping,"known_total_minor":known,
            "currency":currency or t.get("currency","CNY"),"unknown":sorted(set(unknown)),
            "over_budget":t["budget_minor"] is not None and known>t["budget_minor"],
            "remaining_minor":None if t["budget_minor"] is None else t["budget_minor"]-known,
            "final_total_minor":None if any("价格" in x or "运费" in x or "售价" in x or "过期" in x for x in unknown) else known}

def compatibility(t):
    warnings=[]
    for i in t["items"]:
        p=i["snapshot"]["product"]
        if p["category"] in ("显示器","扩展坞"):
            warnings.append(p["name"]+"：主机型号与视频输出协议尚未核实；USB-C 外形不能证明 DP Alt Mode 或供电能力。")
        if p.get("requires_monitor"):
            warnings.append(p["name"]+"：仅适配符合安装厚度要求的桌面显示器，不建议夹在笔记本上。")
        warnings.extend(p.get("limitations",[]))
    return list(dict.fromkeys(warnings))

def make_items(t, lines):
    if len(lines)>12: raise AppError("最多 12 个条目")
    seen=set(); out=[]
    for row in lines:
        oid=row["offer_id"]
        if oid in seen: raise AppError("重复报价，请修改数量")
        seen.add(oid); s=snapshot(oid,t); p=s["product"]; o=s["offer"]
        if (t["scope"]=="demo")!=(p["kind"]=="fixture"): raise AppError("不能混入其他数据模式的商品")
        if t["scope"]=="real" and p["kind"] not in ("verified","external"): raise AppError("真实模式不包含测试商品")
        if o["currency"]!=t.get("currency","CNY"): raise AppError("报价币种与任务不同，不能混算",category="计算")
        if o["stock"]=="out": raise AppError("此报价已知缺货",category="推荐约束")
        if p["category"] in t["owned"]+t["excluded"]: raise AppError("与已有或排除物品重复",category="推荐约束")
        out.append({"offer_id":oid,"quantity":integer(row["quantity"],1,99),
                    "required":row.get("required",True),"reason":str(row.get("reason","手动选择，请核实用途"))[:500],
                    "snapshot":s})
    return out

def set_plan(t,lines):
    old=t["items"]; t["items"]=make_items(t,lines)
    try:
        if totals(t)["over_budget"]: raise AppError("方案已超预算，请减少数量或选择更低报价",category="推荐约束")
    except Exception:
        t["items"]=old; raise
    t["confirmation"]=None
    return {"items":t["items"],"totals":totals(t),"compatibility":compatibility(t)}

def repair_budget(t, version="v2"):
    if t["budget_minor"] is None:return
    rows=t["items"]
    if version=="v2": rows=sorted(rows,key=lambda i:not i["required"])
    kept=[]; removed=[]
    for item in rows:
        probe=copy.deepcopy(t); probe["items"]=kept+[item]
        if totals(probe)["over_budget"]: removed.append(item["snapshot"]["product"]["name"])
        else:kept.append(item)
    t["items"]=kept
    return removed

def fingerprint(t):
    payload={"revision":t["revision"],"items":t["items"],"budget":t["budget_minor"]}
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()

def public_task(t):
    out=copy.deepcopy(t); out.pop("owner",None)
    cache=out.pop("search_cache",{})
    out["cached_offers"]=[{"offer_id":oid,"name":s["product"]["name"],"category":s["product"]["category"],
        "image":s["product"].get("image"),"spec":s["variant"].get("spec"),
        "price_minor":s["offer"].get("price_minor"),"currency":s["offer"].get("currency"),
        "merchant":s["offer"].get("merchant"),"source_url":s["offer"]["url"],
        "collected_at":s["offer"]["captured_at"]} for oid,s in cache.items()]
    out["totals"]=totals(t); out["compatibility"]=compatibility(t)
    return out
