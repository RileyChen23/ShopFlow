import contextlib, copy, json, os, secrets, sqlite3, uuid
from core import ROOT, AppError, now
DB_PATH=PathValue=os.getenv("DATABASE_PATH",str(ROOT/"data/shopping.sqlite3"))

def connect():
    from pathlib import Path
    Path(DB_PATH).parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DB_PATH,timeout=10)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db

def init():
    with contextlib.closing(connect()) as db:
        db.executescript((ROOT/"migrations/001_initial.sql").read_text())
        db.commit()

def session(sid):
    with contextlib.closing(connect()) as db:
        row=db.execute("SELECT * FROM sessions WHERE id=?",(sid or "",)).fetchone()
        if row:return dict(row),False
        s={"id":secrets.token_urlsafe(32),"csrf":secrets.token_urlsafe(32),"created":now()}
        db.execute("INSERT INTO sessions VALUES (:id,:csrf,:created)",s); db.commit()
        return s,True

def get_task(owner,tid):
    with contextlib.closing(connect()) as db:
        row=db.execute("SELECT body FROM tasks WHERE id=? AND owner=?",(tid,owner)).fetchone()
        if not row:raise AppError("任务不存在或不可访问",404)
        return json.loads(row["body"])

def list_tasks(owner):
    with contextlib.closing(connect()) as db:
        return [json.loads(r[0]) for r in db.execute("SELECT body FROM tasks WHERE owner=? ORDER BY updated DESC",(owner,))]

def create_task(t):
    with contextlib.closing(connect()) as db:
        db.execute("INSERT INTO tasks VALUES (?,?,?,?,?)",(t["id"],t["owner"],t["revision"],json.dumps(t,ensure_ascii=False),now())); db.commit()
    return t

def save_task(t,expected):
    with contextlib.closing(connect()) as db:
        t=copy.deepcopy(t); t["revision"]=expected+1
        row=db.execute("UPDATE tasks SET revision=?,body=?,updated=? WHERE id=? AND owner=? AND revision=?",
                       (t["revision"],json.dumps(t,ensure_ascii=False),now(),t["id"],t["owner"],expected))
        if row.rowcount!=1:raise AppError("方案已在另一操作中更新，请载入最新版本后重试",409)
        db.commit()
    return t

def preferences(owner,value=None):
    with contextlib.closing(connect()) as db:
        if value is not None:
            db.execute("INSERT INTO preferences VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET body=excluded.body",
                       (owner,json.dumps(value,ensure_ascii=False)));db.commit()
        row=db.execute("SELECT body FROM preferences WHERE owner=?",(owner,)).fetchone()
        return json.loads(row[0]) if row else {"owned":[],"text":"","scope":"self","source":"用户明确保存","updated":None}

def redact(value):
    import re
    if isinstance(value,dict):
        return {k:("[REDACTED]" if any(word in k.lower() for word in ("authorization","api_key","access_token","password","reasoning_content","chain_of_thought","private_reasoning")) else redact(v)) for k,v in value.items()}
    if isinstance(value,list):return [redact(x) for x in value]
    if isinstance(value,str):
        for key in ("LLM_API_KEY","SEARCH_API_KEY","SHOPIFY_STOREFRONT_TOKEN"):
            secret=os.getenv(key)
            if secret:value=value.replace(secret,"[REDACTED]")
        return re.sub(r"sk-[A-Za-z0-9_-]{16,}", "[REDACTED]", value)
    return value

def run_log(owner,tid,body):
    body=redact(body)
    body={**body,"id":body.get("id") or uuid.uuid4().hex,"created":now()}
    with contextlib.closing(connect()) as db:
        db.execute("INSERT INTO runs VALUES (?,?,?,?,?)",(body["id"],owner,tid,json.dumps(body,ensure_ascii=False),now()));db.commit()
    return body

def runs(owner):
    with contextlib.closing(connect()) as db:
        return [redact({**json.loads(r["body"]),"task_id":r["task_id"]}) for r in db.execute("SELECT body,task_id FROM runs WHERE owner=? ORDER BY created DESC LIMIT 100",(owner,))]

def reserve_call():
    budget_id=os.getenv("LLM_BUDGET_ID")
    if budget_id:
        with contextlib.closing(sqlite3.connect(str(ROOT/"data/model-budget.sqlite3"),timeout=10)) as db:
            db.execute("CREATE TABLE IF NOT EXISTS budgets(id TEXT PRIMARY KEY,cap INTEGER NOT NULL,used INTEGER NOT NULL)")
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("UPDATE budgets SET used=used+1 WHERE id=? AND used<cap",(budget_id,))
            if row.rowcount!=1:raise AppError("本次已授权模型调用预算耗尽，未发送请求",429,"调用预算")
            db.commit()
    day=now()[:10]
    with contextlib.closing(connect()) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT OR IGNORE INTO usage_budget VALUES (?,0)",(day,))
        limit=int(os.getenv("LLM_DAILY_CALL_LIMIT","50"))
        row=db.execute("UPDATE usage_budget SET calls=calls+1 WHERE day=? AND calls<?",(day,limit))
        if row.rowcount!=1:raise AppError("已达到今日模型调用预算上限",429,"依赖故障")
        db.commit()

def claim_cart(owner,t):
    with contextlib.closing(connect()) as db:
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT revision,body FROM tasks WHERE id=? AND owner=?",(t["id"],owner)).fetchone()
        if not row or row["revision"]!=t["revision"]:raise AppError("方案版本已变化",409)
        saved=json.loads(row["body"])
        if saved["confirmation"]!=t["confirmation"]:raise AppError("确认状态已变化",409)
        old=db.execute("SELECT * FROM carts WHERE task_id=? AND revision=?",(t["id"],t["revision"])).fetchone()
        if old:return dict(old),False
        c={"id":uuid.uuid4().hex,"owner":owner,"task_id":t["id"],"revision":t["revision"],"state":"pending","body":"{}"}
        db.execute("INSERT INTO carts VALUES (:id,:owner,:task_id,:revision,:state,:body)",c);db.commit()
        return c,True

def finish_cart(cid,state,body):
    with contextlib.closing(connect()) as db:
        db.execute("UPDATE carts SET state=?,body=? WHERE id=?",(state,json.dumps(body,ensure_ascii=False),cid));db.commit()

def get_cart(owner,cid):
    with contextlib.closing(connect()) as db:
        r=db.execute("SELECT * FROM carts WHERE id=? AND owner=?",(cid,owner)).fetchone()
        if not r:raise AppError("演练购物车不存在",404)
        c=dict(r);c.pop("owner",None);c["body"]=json.loads(c["body"]);return c
