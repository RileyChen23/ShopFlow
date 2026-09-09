"""Independent current checks; offline tests never spend model budget."""
import os,io,json,unittest,subprocess,re,hashlib
from pathlib import Path
os.environ["AGENT_MODE"]="offline"
import core,provenance
def main():
 start=core.now();buf=io.StringIO()
 result=unittest.TextTestRunner(stream=buf,verbosity=2).run(unittest.defaultTestLoader.discover(str(core.ROOT/"tests")))
 system_end=core.now()
 js_start=core.now();js=subprocess.run(["node","--test","--test-reporter=tap","tests/maintenance-data.test.cjs"],cwd=core.ROOT,capture_output=True,text=True,encoding="utf-8");js_end=core.now()
 def count(key):
  m=re.search(r"^# "+key+r" (\d+)",js.stdout,re.M);return int(m.group(1)) if m else None
 stamp=__import__("time").time_ns()
 system_path=f"reports/current-system-{stamp}.txt";js_path=f"reports/current-presentation-{stamp}.txt"
 (core.ROOT/system_path).write_text(buf.getvalue(),encoding="utf-8");(core.ROOT/js_path).write_text(js.stdout+js.stderr,encoding="utf-8")
 r={"started_at":start,"ended_at":core.now(),"commit":provenance.commit(),"mode":"offline-system-and-presentation","system":{"started_at":start,"ended_at":system_end,"total":result.testsRun,"passed":result.testsRun-len(result.failures)-len(result.errors),"log":system_path},"presentation":{"started_at":js_start,"ended_at":js_end,"total":count("tests"),"passed":count("pass"),"exit_code":js.returncode,"log":js_path},"files_sha256":{str(p):provenance.sha(p) for p in [*core.ROOT.glob("*.py"),*(core.ROOT/"web").glob("*.js"),*(core.ROOT/"tests").glob("*.*")]},"limitations":"真实模型评测与浏览器证据分别保存；系统通过不代表采购任务完成率。"}
 (core.ROOT/"reports/live-verification.json").write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps({"system":r["system"],"presentation":r["presentation"]},ensure_ascii=True))
 if not result.wasSuccessful() or js.returncode:raise SystemExit(1)
if __name__=="__main__":main()
