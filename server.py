"""Local-first full stack app; deploy behind TLS reverse proxy with persistent SQLite volume."""
import copy, http.cookies, json, mimetypes, os, re, secrets, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import core, store, agent, checkout, maintenance, provider, provenance
from core import ROOT, AppError, now

class Handler(BaseHTTPRequestHandler):
    server_version="Caimai/0.1"
    def log_message(self,*args):pass  # Avoid URLs/secrets appearing in access logs.
    def json_response(self,value,status=200):
        self.respond(json.dumps(value,ensure_ascii=False).encode(),status,"application/json; charset=utf-8")
    def respond(self,data,status=200,ctype="text/html; charset=utf-8",download=None):
        self.send_response(status)
        self.send_header("Content-Type",ctype);self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store")
        if download:self.send_header("Content-Disposition", 'attachment; filename="'+download+'"')
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Content-Security-Policy","default-src 'self'; img-src 'self' https: data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if getattr(self,"new_session",False):
            secure="; Secure" if os.getenv("COOKIE_SECURE")=="1" else ""
            self.send_header("Set-Cookie",f"sid={self.session['id']}; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000"+secure)
        self.end_headers();self.wfile.write(data)
    def setup_session(self):
        cookie=http.cookies.SimpleCookie()
        try:cookie.load(self.headers.get("Cookie",""))
        except http.cookies.CookieError:pass
        sid=cookie["sid"].value if "sid" in cookie else None
        self.session,self.new_session=store.session(sid)
        self.owner=self.session["id"]
    def do_GET(self):
        try:
            self.setup_session();p=urlparse(self.path).path
            if p=="/api/bootstrap":
                tasks=store.list_tasks(self.owner)
                return self.json_response({"csrf":self.session["csrf"],"tasks":[core.public_task(t) for t in tasks],
                    "preferences":store.preferences(self.owner),"mode":os.getenv("AGENT_MODE","offline"),
                    "test_lab":os.getenv("ENABLE_TEST_LAB")=="1",
                    "integrations":{"model_configured":provider.configured(),"shopify_configured":bool(os.getenv("SHOPIFY_STORE") and os.getenv("SHOPIFY_STOREFRONT_TOKEN") and os.getenv("SHOPIFY_TEST_STORE_ACK")=="1")},
                    "catalog_version":core.catalog()["version"],"catalog_counts":{"verified":sum(p["kind"]=="verified" for p in core.catalog()["products"]),"fixtures":sum(p["kind"]=="fixture" for p in core.catalog()["products"])}})
            if p=="/api/catalog":return self.json_response({"demo":core.search("demo"),"real":core.search("real")})
            if p=="/api/runs":return self.json_response(store.runs(self.owner))
            if p=="/api/maintenance":return self.json_response(maintenance.bundle())
            if p.startswith("/api/run/"):
                return self.json_response(maintenance.run(self.owner,p.split("/")[-1]))
            if p.startswith("/downloads/run/"):
                r=maintenance.run(self.owner,p.split("/")[-1])
                return self.respond(json.dumps(r,ensure_ascii=False,indent=2).encode(),ctype="application/json; charset=utf-8",download="run.json")
            if p.startswith("/files/"):
                data,name=maintenance.artifact(p.split("/")[-1])
                return self.respond(data,ctype="application/octet-stream",download=name)

            if p=="/api/evaluation":
                f=ROOT/"reports/evaluation.json"
                return self.json_response(store.redact(json.loads(f.read_text(encoding="utf-8"))) if f.exists() else {"status":"未运行","live_status":"未运行"})
            if p.startswith("/api/cart/"):return self.json_response(store.get_cart(self.owner,p.split("/")[-1]))
            if p.startswith("/api/task/"):return self.json_response(core.public_task(store.get_task(self.owner,p.split("/")[-1])))
            if p in ("/","/runs","/evaluation","/preferences","/lab") or p.startswith(("/checkout/","/runs/","/evaluation/")):f=ROOT/"web/index.html"
            elif p in ("/app.js","/style.css","/maintenance.js","/maintenance-data.js"):f=ROOT/"web"/p[1:]
            else:raise AppError("页面不存在",404)
            self.respond(f.read_bytes(),ctype=mimetypes.guess_type(str(f))[0]+("; charset=utf-8" if f.suffix in (".html",".js",".css") else ""))
        except AppError as e:self.json_response({"error":str(e),"category":e.category},e.status)
        except Exception:self.json_response({"error":"服务端读取异常"},500)
    def do_POST(self):
        try:
            self.setup_session()
            if self.headers.get("Origin") and self.headers["Origin"]!="http://"+self.headers.get("Host") and self.headers["Origin"]!=os.getenv("PUBLIC_ORIGIN"):
                raise AppError("来源校验失败",403)
            if not secrets.compare_digest(self.headers.get("X-CSRF-Token",""),self.session["csrf"]):raise AppError("会话校验失败，请刷新页面",403)
            n=int(self.headers.get("Content-Length","0"))
            if n>32000:raise AppError("请求过大",413)
            if not self.headers.get("Content-Type","").startswith("application/json"):raise AppError("需要 JSON 请求")
            try:b=json.loads(self.rfile.read(n))
            except (ValueError,UnicodeError):raise AppError("JSON 格式无效")
            if not isinstance(b,dict):raise AppError("请求应为对象")
            self.json_response(self.post(urlparse(self.path).path,b))
        except AppError as e:self.json_response({"error":str(e),"category":e.category},e.status)
        except (KeyError,TypeError,ValueError):self.json_response({"error":"请求字段无效"},400)
        except Exception:self.json_response({"error":"服务暂时不可用；已保存任务不会丢失"},500)

    def post(self,path,b):
        if path=="/api/preferences":
            core.validate(b,{"type":"object","properties":{"owned":agent.STRS,"text":{"type":"string","maxLength":1000}},"required":["owned","text"],"additionalProperties":False})
            return store.preferences(self.owner,{**b,"scope":"self","source":"用户明确保存","updated":now()})
        if path=="/api/tasks":
            scope=b.get("scope","real")
            if scope not in ("demo","real"):raise AppError("未知资料范围")
            t=core.fresh_task(self.owner,scope,store.preferences(self.owner))
            t["currency"]=b.get("currency","CNY")
            if t["currency"] not in ("CNY","GBP"):raise AppError("未知规划币种")
            return core.public_task(store.create_task(t))
        if path=="/api/demo-finish":return checkout.simulated_finish(self.owner,b["cart_id"])
        if path=="/api/jump":
            c=store.get_cart(self.owner,b["cart_id"])
            idx=core.integer(b["index"],0,99);entry=c["body"]["entries"][idx]
            t=store.get_task(self.owner,c["task_id"])
            if t["revision"]!=c["revision"]:raise AppError("购买入口对应旧版本，请重新确认",409,"结算")
            if not entry["url"]:raise AppError("没有购买入口",400,"结算")
            store.run_log(self.owner,t["id"],{**provenance.operation("purchase_jump",t["revision"]),"ended_at":now(),"status":"已跳转","payment":"未知，点击不证明成交","merchant":entry["merchant"],"revision":t["revision"]})
            return {"url":entry["url"],"status":"已跳转，不代表已付款"}
        t=store.get_task(self.owner,b["task_id"])
        expected=core.integer(b["revision"])
        if t["revision"]!=expected:raise AppError("方案已更新，请刷新后重试",409)
        if path=="/api/chat" or path=="/api/lab/chat":
            text=b["text"].strip()
            if not text or len(text)>2000:raise AppError("请输入 1—2000 字")
            fault=None
            if path.startswith("/api/lab/"):
                if os.getenv("ENABLE_TEST_LAB")!="1":raise AppError("测试入口未启用",403)
                fault=b.get("fault")
                if fault not in ("search","model"):raise AppError("未知故障")
            t["messages"].append({"role":"user","content":text})
            if t["title"]=="新的采购任务":t["title"]=text[:32]
            # Persist user input first. CAS at the end rejects any intervening edit.
            pending=store.save_task(t,expected)
            trace=None
            try:
                updated,trace=agent.run(pending,text,store.preferences(self.owner),fault=fault)
                saved=store.save_task(updated,pending["revision"])
                trace["committed_revision"]=saved["revision"];trace["result"]=core.public_task(saved)
                store.run_log(self.owner,t["id"],trace)
                return core.public_task(saved)
            except AppError as e:
                trace=getattr(e,"trace",None) or trace or {"status":"failed","error":str(e),"category":e.category,"input":text}
                trace["committed_revision"]=None
                trace.pop("result",None)
                trace["status"]="failed";trace["category"]=e.category;trace["error"]=str(e)
                store.run_log(self.owner,t["id"],trace)
                raise
        if path=="/api/edit":
            action=b["action"];t["confirmation"]=None;t["status"]="规划中"
            if action=="budget":
                t["budget_minor"]=core.integer(b["budget_minor"]);core.repair_budget(t,os.getenv("STRATEGY_VERSION","v2"))
            elif action=="refresh":
                t["items"]=core.make_items(t,[{k:i[k] for k in ("offer_id","quantity","required","reason")} for i in t["items"]])
            elif action=="plan":
                core.validate({"items":b["items"]},agent.SCHEMAS["set_plan"])
                core.set_plan(t,b["items"])
            else:raise AppError("未知修改操作")
            saved=store.save_task(t,expected)
            return core.public_task(saved)
        if path=="/api/confirm":
            if not t["items"]:raise AppError("请先添加商品")
            if core.totals(t)["over_budget"]:raise AppError("方案超预算")
            if b.get("acknowledge_unknown") is not True:raise AppError("需要明确知悉未知费用与测试性质")
            for i in t["items"]:
                if i["snapshot"]!=core.snapshot(i["offer_id"]):raise AppError("报价已变化，请先刷新报价",409)
            t["revision"]=expected+1
            t["confirmation"]={"fingerprint":core.fingerprint(t),"at":now(),"acknowledge_unknown":True}
            t["status"]="已确认，尚未购买"
            return core.public_task(store.save_task(t,expected))
        if path in ("/api/checkout","/api/lab/checkout"):
            fault=None
            if path.startswith("/api/lab/"):
                if os.getenv("ENABLE_TEST_LAB")!="1":raise AppError("测试入口未启用",403)
                fault="checkout"
            started=time.monotonic();operation=provenance.operation("checkout",t["revision"])
            try:
                result=checkout.prepare(self.owner,t,fault)
                store.run_log(self.owner,t["id"],{**operation,"ended_at":now(),"status":"success","revision":t["revision"],"entries":[{"merchant":e["merchant"],"kind":e["kind"]} for e in result["entries"]],"latency_ms":round((time.monotonic()-started)*1000,2)})
                return result
            except AppError as e:
                store.run_log(self.owner,t["id"],{**operation,"ended_at":now(),"status":"failed","category":"结算","error":str(e),"revision":t["revision"],"latency_ms":round((time.monotonic()-started)*1000,2)})
                raise
        if path=="/api/mark-purchased":
            if b.get("explicit") is not True:raise AppError("需要明确手动标记")
            t["status"]="已购买（用户标记，未验证付款）";t["confirmation"]=None
            return core.public_task(store.save_task(t,expected))
        raise AppError("接口不存在",404)

def main():
    store.init()
    host=os.getenv("HOST","127.0.0.1");port=int(os.getenv("PORT","8765"))
    print(f"Caimai ready: http://{host}:{port} | mode={os.getenv('AGENT_MODE','offline')}",flush=True)
    ThreadingHTTPServer((host,port),Handler).serve_forever()
if __name__=="__main__":main()
