"""Pluggable external product search providers.

Providers return web results only. Normalization into ShopFlow's product / variant /
offer / evidence schema happens here so the rest of the planning chain is unchanged.
"""
import hashlib, json, os, socket, time, urllib.error, urllib.request
from urllib.parse import urlparse
import core

class SearchProvider:
    name="base"
    def search(self,query,max_results=5):raise NotImplementedError

class TavilySearchProvider(SearchProvider):
    name="tavily"
    def __init__(self,key=None,base_url=None,timeout=None):
        self.key=key if key is not None else os.getenv("SEARCH_API_KEY","")
        self.base_url=base_url or os.getenv("SEARCH_BASE_URL","https://api.tavily.com/search")
        self.timeout=min(float(timeout or os.getenv("SEARCH_TIMEOUT_SECONDS","15")),30)
    def search(self,query,max_results=5):
        if not self.key:raise core.AppError("外部商品搜索未配置：请在服务端设置 SEARCH_API_KEY",503,"配置")
        payload={"query":query,"topic":"general","search_depth":"basic","max_results":max_results,
                 "include_answer":False,"include_raw_content":False,"include_images":False,
                 "exclude_domains":["taobao.com","tmall.com","jd.com"]}
        data=_request(self.base_url,payload,{"Authorization":"Bearer "+self.key},self.timeout)
        rows=data.get("results")
        if not isinstance(rows,list):raise core.AppError("搜索服务响应结构无效",502,"检索")
        return {"provider":self.name,"request_id":data.get("request_id"),"query":query,
                "credits":(data.get("usage") or {}).get("credits"),"results":rows[:max_results]}

def get():
    name=os.getenv("SEARCH_PROVIDER","tavily").lower()
    if name=="tavily":return TavilySearchProvider()
    raise core.AppError("未知商品搜索 Provider："+name,503,"配置")

def configured():return bool(os.getenv("SEARCH_PROVIDER","tavily") and os.getenv("SEARCH_API_KEY"))

def _request(url,payload,headers,timeout):
    core.safe_link(url)
    host=urlparse(url).hostname
    try:
        addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        import ipaddress
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise core.AppError("搜索接口解析到非公开地址",400,"检索")
    except socket.gaierror:raise core.AppError("搜索接口域名解析失败",502,"检索") from None
    req=urllib.request.Request(url,json.dumps(payload,ensure_ascii=False).encode("utf-8"),
        {"Content-Type":"application/json","Accept":"application/json",**headers},method="POST")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    try:
        with urllib.request.build_opener(NoRedirect).open(req,timeout=timeout) as response:
            raw=response.read(1_000_001)
            if len(raw)>1_000_000:raise core.AppError("搜索响应超过体积限制",502,"检索")
            return json.loads(raw)
    except core.AppError:raise
    except Exception as error:
        status=getattr(error,"code",None)
        raise core.AppError("外部商品搜索失败"+(f"（HTTP {status}）" if status else "（连接、超时或响应异常）"),502,"检索") from None

def normalize(batch,category,currency,collected_at=None):
    """Convert provider results into immutable snapshots used by existing tools."""
    collected_at=collected_at or core.now();out=[];seen=set()
    for row in batch.get("results",[]):
        if not isinstance(row,dict):continue
        title=str(row.get("title") or "").strip()[:300]
        excerpt=str(row.get("content") or "").strip()[:1200]
        url=row.get("url")
        if not title or not excerpt or not isinstance(url,str):continue
        try:url=core.safe_link(url)
        except core.AppError:continue
        key=hashlib.sha256(url.encode()).hexdigest()[:20]
        if key in seen:continue
        seen.add(key);host=urlparse(url).hostname.lower()
        pid="ext-p-"+key;vid="ext-v-"+key;oid="ext-o-"+key
        product={"id":pid,"kind":"external","brand":None,"name":title,"category":category or "其他",
            "attributes":{"search_summary":excerpt},"limitations":["规格来自搜索摘要，购买前请在来源页面复核。"],
            "image":None,"image_source":None,"evidence":[{"fields":["name","attributes","offer"],
            "url":url,"excerpt":excerpt,"checked_at":collected_at}]}
        variant={"id":vid,"product_id":pid,"sku":"WEB-"+key.upper(),"spec":"搜索结果，具体规格见来源页面","attributes":{}}
        offer={"id":oid,"variant_id":vid,"merchant":host,"currency":currency,"price_minor":None,
            "shipping_minor":None,"price_kind":"unknown","stock":"unknown","captured_at":collected_at,
            "valid_until":None,"conditions":"搜索摘要未提供可验证的结构化价格、库存和配送信息。",
            "url":url,"purchase":"external","source_provider":batch.get("provider")}
        out.append({"product":product,"variant":variant,"offer":offer})
    return out
