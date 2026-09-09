"""Local explicit call-budget administration. Raising cap is a user's spending decision."""
import argparse,sqlite3,contextlib,os
import core
def main():
 p=argparse.ArgumentParser();p.add_argument("--id",default=os.getenv("LLM_BUDGET_ID"));p.add_argument("--cap",type=int);a=p.parse_args()
 if not a.id:raise SystemExit("Set LLM_BUDGET_ID locally or pass --id.")
 if a.cap is not None and not 1<=a.cap<=10000:raise SystemExit("Cap must be 1..10000.")
 path=core.ROOT/"data/model-budget.sqlite3";path.parent.mkdir(exist_ok=True)
 with contextlib.closing(sqlite3.connect(path)) as db:
  db.execute("CREATE TABLE IF NOT EXISTS budgets(id TEXT PRIMARY KEY,cap INTEGER NOT NULL,used INTEGER NOT NULL)")
  if a.cap is not None:
   db.execute("INSERT INTO budgets VALUES (?,?,0) ON CONFLICT(id) DO UPDATE SET cap=excluded.cap",(a.id,a.cap));db.commit()
  r=db.execute("SELECT cap,used FROM budgets WHERE id=?",(a.id,)).fetchone()
  print({"budget_id":a.id,"cap":r[0] if r else None,"reserved_requests":r[1] if r else None,"remaining":max(0,r[0]-r[1]) if r else None})
if __name__=="__main__":main()
