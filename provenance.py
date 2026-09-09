"""New-run provenance only; never fills historical gaps."""
import hashlib,subprocess
from pathlib import Path
import core
def commit():
    try:
        r=subprocess.run(["git","rev-parse","HEAD"],cwd=core.ROOT,capture_output=True,text=True,timeout=2)
        return r.stdout.strip() if r.returncode==0 else "unknown"
    except (OSError,subprocess.TimeoutExpired):return "unknown"
def sha(path):
    p=Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
def operation(kind,revision):
    return {"type":kind,"mode":"deterministic","started_at":core.now(),"commit":commit(),"catalog_version":core.catalog()["version"],"catalog_sha256":sha(core.ROOT/"data/catalog.json"),"revision":revision,"model_calls":0,"model_events":[],"retries":[],"fallback":None}
