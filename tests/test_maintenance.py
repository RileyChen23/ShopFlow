import json,tempfile,unittest,contextlib,threading,urllib.request,urllib.error,http.cookiejar
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import core,store,maintenance
from server import Handler
class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=patch.object(store,"DB_PATH",str(Path(self.tmp.name)/"test.sqlite"));self.db.start();store.init()
        self.owner=store.session(None)[0]["id"]
        t=store.create_task(core.fresh_task(self.owner))
        self.run=store.run_log(self.owner,t["id"],{"status":"success","input":"x","authorization":"secret","reasoning_content":"private"})
        self.http=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.url="http://127.0.0.1:"+str(self.http.server_port)
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();self.db.stop();self.tmp.cleanup()
    def get(self,path,owner=None):
        req=urllib.request.Request(self.url+path,headers={"Cookie":"sid="+(owner or self.owner)})
        return urllib.request.urlopen(req)
    def test_owner_scoped_details_and_download(self):
        for prefix in ["/api/run/","/downloads/run/"]:
            with self.get(prefix+self.run["id"]) as r:
                data=json.load(r);self.assertEqual(data["authorization"],"[REDACTED]");self.assertNotIn("private",str(data))
            other=store.session(None)[0]["id"]
            with self.assertRaises(urllib.error.HTTPError) as e:self.get(prefix+self.run["id"],other)
            self.assertEqual(e.exception.code,404)
    def test_raw_download_headers_and_whitelist(self):
        with self.get("/files/report") as r:self.assertIn("attachment",r.headers["Content-Disposition"])
        for path in ["/files/.env","/files/../../.env","/files/%2e%2e%2f.env"]:
            with self.assertRaises(urllib.error.HTTPError) as e:self.get(path)
            self.assertEqual(e.exception.code,404)
    def test_missing_report_is_explicit(self):
        with patch.object(maintenance,"ROOT",Path(self.tmp.name)):
            self.assertIsNone(maintenance.bundle()["report"])
            self.assertEqual(maintenance.bundle()["cases"],[])
    def test_changed_dataset_does_not_supply_expected_context(self):
        with patch.object(maintenance,"read_json",side_effect=lambda path: {"test_set_sha256":"changed"} if str(path)==maintenance.FILES["report"] else {"cases":[{"id":"fake"}]} if str(path)==maintenance.FILES["cases"] else None):
            b=maintenance.bundle();self.assertEqual(b["cases"],[]);self.assertFalse(b["metadata"]["cases_match"])
    def test_history_hash_matches_and_empty_owner_list(self):
        b=maintenance.bundle();self.assertTrue(b["metadata"]["cases_match"]);self.assertEqual(b["metadata"]["catalog_match"], __import__("hashlib").sha256((core.ROOT/"data/catalog.json").read_bytes()).hexdigest()==b["report"]["catalog_sha256"])
        self.assertEqual(store.runs("different-owner"),[])
        self.assertFalse(b["metadata"]["current_code_verified_by_historical_report"])
    def test_workspace_has_safe_markdown_tables_links_and_recent_tasks(self):
        app=(core.ROOT/"web/app.js").read_text(encoding="utf-8")
        self.assertIn("function markdown(value)",app)
        self.assertIn('class="message-table"',app)
        self.assertIn('class="budget-groups"',app)
        self.assertIn('rel="noopener"',app)
        self.assertIn("Recent shopping",app)
        self.assertIn("Add from results",app)
        self.assertIn("const optimistic = {...task",app)
        self.assertIn("messages: [...task.messages",app)
