"""Pluggable external product search providers.

Providers return web results only. Normalization into ShopFlow's product / variant /
offer / evidence schema happens here so the rest of the planning chain is unchanged.
"""
from decimal import Decimal, InvalidOperation
import hashlib, json, os, socket, urllib.request
from urllib.parse import urlencode, urlparse
import core

class SearchProvider:
    name="base"
    def search(self,query,max_results=5,currency="CNY"):raise NotImplementedError

class RainforestSearchProvider(SearchProvider):
    name="rainforest"
    def __init__(self,key=None,base_url=None,amazon_domain=None,timeout=None):
        self.key=key if key is not None else os.getenv("RAINFOREST_API_KEY","")
        self.base_url=base_url or os.getenv("RAINFOREST_BASE_URL","https://api.rainforestapi.com/request")
        self.amazon_domain=amazon_domain or os.getenv("RAINFOREST_AMAZON_DOMAIN","amazon.com")
        self.timeout=min(float(timeout or os.getenv("SEARCH_TIMEOUT_SECONDS","20")),30)
    def search(self,query,max_results=5,currency="CNY"):
        if not self.key:raise core.AppError("Rainforest product search is not configured.",503,"配置")
        count=min(max(int(max_results),1),5)
        amazon_domain="amazon.co.uk" if currency.upper()=="GBP" else self.amazon_domain
        params={"api_key":self.key,"type":"search","amazon_domain":amazon_domain,
            "search_term":query.strip(),"number_of_results":count,"exclude_sponsored":"true",
            "currency":currency.lower(),"output":"json"}
        location=os.getenv("RAINFOREST_CUSTOMER_LOCATION","").strip()
        if location:params["customer_location"]=location
        data=_request(self.base_url,params,self.timeout)
        info=data.get("request_info") or {}
        if info.get("success") is False:raise core.AppError("Rainforest could not complete the product search.",502,"检索")
        rows=data.get("search_results")
        if not isinstance(rows,list):raise core.AppError("Rainforest returned an invalid search response.",502,"检索")
        metadata=data.get("request_metadata") or {}
        return {"provider":self.name,"request_id":metadata.get("id"),"query":query,
            "amazon_domain":amazon_domain,"credits":None,"account_credits_used":info.get("credits_used"),
            "account_credits_remaining":info.get("credits_remaining"),"results":rows[:count],"max_results":count}

def get():
    name=os.getenv("SEARCH_PROVIDER","rainforest").lower()
    if name=="rainforest":return RainforestSearchProvider()
    raise core.AppError("未知商品搜索 Provider："+name,503,"配置")

def configured():return os.getenv("SEARCH_PROVIDER","rainforest").lower()=="rainforest" and bool(os.getenv("RAINFOREST_API_KEY"))

def _request(url,params,timeout):
    core.safe_link(url)
    host=urlparse(url).hostname
    try:
        addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        import ipaddress
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise core.AppError("搜索接口解析到非公开地址",400,"检索")
    except socket.gaierror:raise core.AppError("搜索接口域名解析失败",502,"检索") from None
    request_url=url+("&" if "?" in url else "?")+urlencode(params)
    req=urllib.request.Request(request_url,headers={"Accept":"application/json"},method="GET")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    try:
        with urllib.request.build_opener(NoRedirect).open(req,timeout=timeout) as response:
            raw=response.read(2_000_001)
            if len(raw)>2_000_000:raise core.AppError("搜索响应超过体积限制",502,"检索")
            return json.loads(raw)
    except core.AppError:raise
    except Exception as error:
        status=getattr(error,"code",None)
        raise core.AppError("Rainforest product search failed"+(f" (HTTP {status})." if status else "."),502,"检索") from None

def _minor_units(price):
    if not isinstance(price,dict) or price.get("value") is None:return None
    try:return int((Decimal(str(price["value"]))*100).quantize(Decimal("1")))
    except (InvalidOperation,ValueError,TypeError):return None

def _rainforest_excerpt(row):
    parts=[str(row.get("title") or "").strip()]
    price=row.get("price") or {}
    if price.get("raw"):parts.append("Price: "+str(price["raw"]))
    if row.get("rating") is not None:
        rating="Rating: "+str(row["rating"])+"/5"
        if row.get("ratings_total") is not None:rating+=" ("+str(row["ratings_total"])+" ratings)"
        parts.append(rating)
    availability=row.get("availability") or {}
    if isinstance(availability,dict) and availability.get("raw"):parts.append(str(availability["raw"]))
    return ". ".join(part for part in parts if part)[:1200]

def _normalize_rainforest(batch,category,task_currency,collected_at):
    out=[];seen=set()
    for row in batch.get("results",[]):
        if not isinstance(row,dict) or row.get("is_sponsored") is True:continue
        asin=str(row.get("asin") or "").strip().upper()
        title=str(row.get("title") or "").strip()[:300]
        url=row.get("link")
        if not asin or not title or not isinstance(url,str):continue
        try:url=core.safe_link(url)
        except core.AppError:continue
        key=hashlib.sha256((batch.get("amazon_domain","")+":"+asin).encode()).hexdigest()[:20]
        if key in seen:continue
        seen.add(key)
        price=row.get("price") if isinstance(row.get("price"),dict) else {}
        offer_currency=str(price.get("currency") or task_currency).upper()
        price_minor=_minor_units(price);image=row.get("image") if isinstance(row.get("image"),str) else None
        excerpt=_rainforest_excerpt(row)
        pid="ext-p-"+key;vid="ext-v-"+key;oid="ext-o-"+key
        product={"id":pid,"kind":"external","brand":row.get("brand"),"name":title,"category":category or "其他",
            "attributes":{"asin":asin,"rating":row.get("rating"),"ratings_total":row.get("ratings_total"),
                "position":row.get("position"),"search_summary":excerpt},
            "limitations":["价格、库存和配送信息可能在来源页面发生变化。"],
            "image":image,"image_source":url if image else None,
            "evidence":[{"fields":["name","attributes","offer"],"url":url,"excerpt":excerpt,"checked_at":collected_at}]}
        variant={"id":vid,"product_id":pid,"sku":asin,"spec":title,"attributes":{"asin":asin}}
        offer={"id":oid,"variant_id":vid,"merchant":batch.get("amazon_domain","Amazon"),"currency":offer_currency,
            "price_minor":price_minor,"shipping_minor":None,"price_kind":"market_offer" if price_minor is not None else "unknown",
            "stock":"unknown","captured_at":collected_at,"valid_until":None,
            "conditions":"采集时商品页报价；配送与库存请在来源页面确认。","url":url,"purchase":"external","source_provider":"rainforest"}
        out.append({"product":product,"variant":variant,"offer":offer})
    return out

def _normalize_fixture(batch,category,currency,collected_at):
    """Adapter retained for deterministic tests and saved evaluation fixtures."""
    out=[];seen=set()
    for row in batch.get("results",[]):
        if not isinstance(row,dict):continue
        title=str(row.get("title") or "").strip()[:300];excerpt=str(row.get("content") or "").strip()[:1200];url=row.get("url")
        if not title or not excerpt or not isinstance(url,str):continue
        try:url=core.safe_link(url)
        except core.AppError:continue
        key=hashlib.sha256(url.encode()).hexdigest()[:20]
        if key in seen:continue
        seen.add(key);pid="ext-p-"+key;vid="ext-v-"+key;oid="ext-o-"+key
        product={"id":pid,"kind":"external","brand":None,"name":title,"category":category or "其他",
            "attributes":{"search_summary":excerpt},"limitations":["请在来源页面复核。"],"image":None,"image_source":None,
            "evidence":[{"fields":["name","attributes","offer"],"url":url,"excerpt":excerpt,"checked_at":collected_at}]}
        variant={"id":vid,"product_id":pid,"sku":"WEB-"+key.upper(),"spec":excerpt[:300],"attributes":{}}
        offer={"id":oid,"variant_id":vid,"merchant":urlparse(url).hostname.lower(),"currency":currency,"price_minor":None,
            "shipping_minor":None,"price_kind":"unknown","stock":"unknown","captured_at":collected_at,"valid_until":None,
            "conditions":"固定评测结果未提供可验证价格。","url":url,"purchase":"external","source_provider":batch.get("provider")}
        out.append({"product":product,"variant":variant,"offer":offer})
    return out

def normalize(batch,category,currency,collected_at=None):
    """Convert provider results into immutable snapshots used by existing tools."""
    collected_at=collected_at or core.now()
    if batch.get("provider")=="rainforest":return _normalize_rainforest(batch,category,currency,collected_at)
    return _normalize_fixture(batch,category,currency,collected_at)
