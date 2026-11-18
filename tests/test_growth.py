import functools
import csv
import http.server
import io
import json
import mimetypes
import os
from pathlib import Path
import struct
import threading
import unittest
from urllib.parse import parse_qs, unquote, urlsplit

from playwright.sync_api import sync_playwright
import yaml


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = "https://oool727.github.io/beatmaniaIIDX-11-12-grid/"
MARKER = "PRIVATE_SCORE_MARKER_714"
CSV = (
    "タイトル,HYPER 難易度,HYPER クリアタイプ,HYPER ミスカウント,"
    "ANOTHER 難易度,ANOTHER クリアタイプ,ANOTHER ミスカウント\n"
    + MARKER + ",12,HARD CLEAR,27,12,CLEAR,31"
)
SCORE_KEYS = ["lampgrid.csv", "lampgrid.at", "lampgrid.snap", "lampgrid.opt"]
ASSETS = {
    "/", "/index.html", "/sw.js", "/manifest.webmanifest", "/demo.js", "/social-preview.png",
    "/icon-180.png", "/icon-192.png", "/icon-512.png", "/icon-512-maskable.png",
}

def score_csv(charts):
    buffer=io.StringIO()
    writer=csv.writer(buffer,lineterminator="\n")
    names=["HYPER","ANOTHER","LEGGENDARIA"]
    writer.writerow(["タイトル",*[name+" "+field for name in names for field in ["難易度","クリアタイプ","ミスカウント"]]])
    for title,chart,level,lamp,bp in charts:
        row=[title]+[""]*9
        slot=["H","A","L"].index(chart)*3+1
        row[slot:slot+3]=[level,lamp,bp]
        writer.writerow(row)
    return buffer.getvalue()


class AssetHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if unquote(urlsplit(self.path).path) not in ASSETS:
            self.send_error(404)
            return
        super().do_GET()

    def log_message(self, *_):
        pass


class AssetServer(http.server.ThreadingHTTPServer):
    request_queue_size = 32


class GrowthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = AssetServer(
            ("127.0.0.1", 0), functools.partial(AssetHandler, directory=str(ROOT))
        )
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}/"
        cls.playwright = sync_playwright().start()
        chrome = os.environ.get(
            "LAMPGRID_BROWSER_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        )
        options = {"executable_path": chrome} if Path(chrome).is_file() else {}
        cls.browser = cls.playwright.chromium.launch(**options)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join()

    def setUp(self):
        self.contexts, self.errors, self.remote = [], [], []

    def tearDown(self):
        for context in self.contexts:
            context.close()
        self.assertEqual(self.errors, [], "Application JavaScript errors")

    def page(self, seed=None, query="", mobile=False, service_worker=False, public_origin=False):
        context = self.browser.new_context(
            service_workers="allow" if service_worker else "block",
            viewport={"width": 390, "height": 844} if mobile else {"width": 1280, "height": 900},
        )
        self.contexts.append(context)
        if seed:
            context.add_init_script(
                "(() => {const values=" + json.dumps(seed)
                + "; for(const [k,v] of Object.entries(values))"
                + " if(localStorage.getItem(k)===null) localStorage.setItem(k,v);})();"
            )
        base = PUBLIC if public_origin else self.base

        def route(request_route):
            request = request_route.request
            if request.url.startswith(base):
                if public_origin:
                    path = "/" + unquote(urlsplit(request.url).path[len(urlsplit(base).path):])
                    if path not in ASSETS:
                        request_route.fulfill(status=404)
                    else:
                        file = ROOT / (path.lstrip("/") or "index.html")
                        request_route.fulfill(
                            content_type=mimetypes.guess_type(str(file))[0] or "application/octet-stream",
                            body=file.read_bytes(),
                        )
                else:
                    request_route.continue_()
            else:
                self.remote.append(request.url)
                request_route.abort()

        context.route("**/*", route)
        page = context.new_page()
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        page.goto(base + query, wait_until="domcontentloaded")
        page.wait_for_function("typeof enterDemo==='function' && window.LampGridDemo")
        return page

    def storage(self, page):
        return page.evaluate(
            "(keys)=>Object.fromEntries(keys.map(k=>[k,localStorage.getItem(k)]))", SCORE_KEYS
        )

    def test_no_analytics_with_legacy_consent_on_public_origin(self):
        page = self.page(
            public_origin=True,
            seed={"lampgrid.analyticsConsent.v1": "granted"},
            query="?utm_source=x&utm_campaign=" + MARKER + "#" + MARKER,
        )
        page.locator("#demoStart").click()
        page.locator("#q").fill(MARKER)
        page.locator(".tab[data-lv='10']").click()
        page.locator(".tab[data-mode='hard']").click()
        page.evaluate("render(); render()")
        self.assertTrue(page.evaluate(
            "typeof window.gtag==='undefined' && typeof window.dataLayer==='undefined'"
            " && typeof window.LampGridAnalytics==='undefined'"
        ))
        self.assertEqual(page.locator("[data-analytics-choice], #analyticsChoice").count(), 0)
        self.assertEqual(page.locator("script[src*='analytics']").count(), 0)
        self.assertEqual(page.context.cookies(), [])
        self.assertEqual(self.remote, [])

    def test_demo_preserves_all_real_storage_and_view_state(self):
        page = self.page()
        page.evaluate("(csv)=>start(csv)", CSV)
        page.locator(".tab[data-lv='10']").click()
        page.locator(".tab[data-mode='hard']").click()
        page.locator("#q").fill("ORIGINAL_SEARCH")
        page.locator("#names").check()
        before = self.storage(page)
        original = page.evaluate(
            "()=>({score:JSON.stringify(SCORE),lv:LV,mode:MODE,q:q.value,open:[...OPEN]})"
        )
        page.locator("#demoAgain").click()
        self.assertIn("架空", page.locator("#loadedat").inner_text())
        self.assertTrue(page.evaluate("DIFFTEXT===null"))
        for level in ["9", "10", "11", "12"]:
            page.locator(f".tab[data-lv='{level}']").click()
            if level != "9":
                for mode in ["hard", "normal"]:
                    page.locator(f".tab[data-mode='{mode}']").click()
                    self.assertGreater(page.evaluate("rowsFor(LV).length"), 0)
            if level == "10":
                for author in ["胡椒", "NASK"]:
                    page.locator("#source10Button").click()
                    page.locator("#source10Menu button").filter(has_text=author).click()
        page.locator("#onlyun").check()
        page.locator("#scrweak").check()
        page.locator("#q").fill(MARKER)
        page.evaluate("OPEN.add('test-tier'); saveOpt()")
        self.assertEqual(self.storage(page), before)
        page.locator("#clear").click()
        self.assertEqual(self.storage(page), before)
        restored = page.evaluate(
            "()=>({score:JSON.stringify(SCORE),lv:LV,mode:MODE,q:q.value,open:[...OPEN]})"
        )
        self.assertEqual(restored, original)
        self.assertEqual(self.remote, [])

    def test_manual_import_failure_and_restore_stay_local(self):
        page = self.page()
        page.locator("#demoStart").click()
        page.locator("#f2").set_input_files({
            "name": MARKER + ".csv", "mimeType": "text/csv", "buffer": CSV.encode("utf-8"),
        })
        page.wait_for_function("!IS_DEMO && Object.keys(SCORE).length===2")
        page.locator("#q").fill(MARKER)
        page.locator("#topaste2").click()
        page.locator("#pastearea").fill(MARKER + "_RAW_ERROR")
        page.locator("#doPaste").click()
        self.assertIn(MARKER, page.locator("#err").inner_text())
        page.locator("#pastearea").fill("")
        page.locator("#doPaste").click()
        self.assertIn("空", page.locator("#err").inner_text())
        page.locator("#pastearea").fill(CSV)
        page.locator("#doPaste").click()
        page.evaluate("()=>{File.prototype.text=()=>Promise.reject(new Error('" + MARKER + "'));}")
        page.locator("#f2").set_input_files({
            "name": MARKER + "_unreadable.csv", "mimeType": "text/csv", "buffer": b"synthetic",
        })
        page.wait_for_function("err.textContent.includes('ファイルを読み込めません')")
        self.assertEqual(page.evaluate("(key)=>localStorage.getItem(key)", SCORE_KEYS[0]), CSV)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_function("Object.keys(SCORE).length===2")
        self.assertTrue(page.locator("#app").is_visible())
        self.assertEqual(self.remote, [])
        self.assertEqual(page.context.cookies(), [])

    def test_failed_import_during_demo_can_exit_without_changing_data(self):
        page = self.page(seed={
            "lampgrid.csv": CSV, "lampgrid.at": "1700000000000",
            "lampgrid.snap": '{"preserve":5}', "lampgrid.opt": '{"lv":"11","mode":"hard"}',
        })
        before = self.storage(page)
        page.locator("#demoAgain").click()
        page.locator("#topaste2").click()
        page.locator("#pastearea").fill(MARKER)
        page.locator("#doPaste").click()
        self.assertTrue(page.evaluate("IS_DEMO"))
        self.assertEqual(self.storage(page), before)
        page.locator("#demoExit").click()
        self.assertEqual(page.evaluate("LV"), "11")
        self.assertEqual(self.storage(page), before)

    def test_real_score_deletion_requires_confirmation_and_clears_snapshot(self):
        page = self.page()
        page.evaluate("(csv)=>start(csv)", CSV)
        page.evaluate("saveOpt()")
        before = self.storage(page)
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.locator("#clear").click()
        self.assertEqual(self.storage(page), before)
        page.once("dialog", lambda dialog: dialog.accept())
        with page.expect_navigation(wait_until="domcontentloaded"):
            page.locator("#clear").click()
        self.assertEqual(self.storage(page), {
            "lampgrid.csv": None, "lampgrid.at": None, "lampgrid.snap": None,
            "lampgrid.opt": before["lampgrid.opt"],
        })
        self.assertTrue(page.locator("#intro").is_visible())

    def test_mobile_privacy_feedback_and_share_without_tracking(self):
        page = self.page(mobile=True)
        page.locator("footer [data-open-privacy]").click()
        self.assertIn("アクセス解析・広告タグは組み込んでいません", page.locator("#privacyDialog").inner_text())
        self.assertEqual(page.locator("#privacyDialog button").count(), 1)
        page.keyboard.press("Escape")
        page.locator("[data-open-feedback='header']").click()
        self.assertIn("公開", page.locator("#feedbackDialog").inner_text())
        page.keyboard.press("Escape")
        page.locator("#demoStart").click()
        page.locator("[data-open-feedback='toolbar']").click()
        for kind, filename in [
            ("bug", "bug_report.yml"), ("feature", "feature_request.yml"), ("feedback", "feedback.yml")
        ]:
            link = page.locator(f"[data-feedback-kind='{kind}']")
            parsed = urlsplit(link.get_attribute("href"))
            self.assertEqual(parsed.netloc, "github.com")
            self.assertEqual(parse_qs(parsed.query), {"template": [filename]})
            form = yaml.safe_load((ROOT / ".github" / "ISSUE_TEMPLATE" / filename).read_text(encoding="utf-8"))
            self.assertNotIn("labels", form)
            self.assertIn("公開", form["body"][0]["attributes"]["value"])
        page.keyboard.press("Escape")
        page.locator("#demoExit").click()
        page.evaluate("(csv)=>start(csv)", CSV)
        page.locator("#q").fill(MARKER)
        share = urlsplit(page.locator("a[href^='https://x.com/intent/post']").get_attribute("href"))
        self.assertEqual(parse_qs(share.query)["url"], [PUBLIC])
        self.assertIn("#IIDX",parse_qs(share.query)["text"][0])
        self.assertIn("#LAMPGRID",parse_qs(share.query)["text"][0])
        self.assertNotIn(MARKER, share.query)
        self.assertEqual(self.remote, [])
        self.assertEqual(page.context.cookies(), [])

    def test_offline_cache_excludes_removed_scripts_and_preserves_other_apps(self):
        page = self.page(service_worker=True)
        page.evaluate("()=>navigator.serviceWorker.ready")
        page.wait_for_function("navigator.serviceWorker.controller")
        page.evaluate("()=>caches.open('another-app-v1').then(c=>c.put('/unrelated',new Response('keep')))")
        cached = page.evaluate(
            "()=>caches.open('lampgrid-v22').then(c=>c.keys()).then(rs=>rs.map(r=>r.url))"
        )
        self.assertTrue(any(url.endswith("/demo.js") for url in cached))
        self.assertTrue(all(url.startswith(self.base) and "analytics" not in url for url in cached))
        self.assertEqual(self.remote, [])
        page.context.set_offline(True)
        page.reload(wait_until="domcontentloaded")
        page.locator("#demoStart").click()
        page.locator(".tab[data-lv='10']").click()
        page.locator(".tab[data-mode='hard']").click()
        self.assertEqual(page.evaluate("rowsFor(LV).length"), 1018)
        self.assertTrue(page.evaluate("()=>caches.has('another-app-v1')"))
        results = page.evaluate("""async ()=>{
          const failed=[];
          for(const url of ['analytics.js','analytics-config.js','https://www.googletagmanager.com/gtag/js?id=G-TEST123']){
            try {const response=await fetch(url); failed.push(!response.ok);}
            catch {failed.push(true);}
          }
          return failed;
        }""")
        self.assertEqual(results, [True, True, True])
        page.context.set_offline(False)

    def test_preview_metadata_and_image(self):
        page = self.page()
        self.assertEqual(page.locator("meta[property='og:image']").get_attribute("content"), PUBLIC + "social-preview.png")
        self.assertEqual(page.locator("meta[name='twitter:card']").get_attribute("content"), "summary_large_image")
        image = page.request.get(self.base + "social-preview.png")
        self.assertTrue(image.ok)
        body = image.body()
        self.assertEqual(body[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", body[16:24]), (1200, 630))

    def test_unlisted_distinguishes_source_chart_and_unrated_rows(self):
        page=self.page()
        entries=page.evaluate("""()=>{
          const naskKeys=new Set(TABLES.t10.map(r=>keyOf(r[2]).join('|')));
          const koshoOnly=KOSHO10.find(r=>!naskKeys.has(keyOf(r[2]).join('|')));
          const blank=TABLES.t10.find(r=>r[0]&&!r[1]);
          const unrated=TABLES.t10.find(r=>r[1]==='未定');
          const another=TABLES.t10.find(r=>keyOf(r[2])[1]==='A'&&!naskKeys.has(keyOf(r[2])[0]+'|H'));
          return [koshoOnly,blank,unrated,another].map(r=>({
            title:r[2].replace(/\\((H|L)\\)\\s*$/,''),chart:keyOf(r[2])[1]
          }));
        }""")
        charts=[(entry["title"],entry["chart"],10,"EX HARD CLEAR",12) for entry in entries]
        charts.extend([
            (entries[-1]["title"],"H",10,"FAILED",70),
            ("__TEST_UNKNOWN","A",10,"NO PLAY",""),
            ("__TEST_UNKNOWN","L",11,"CLEAR",10),
        ])
        page.evaluate("(text)=>start(text)",score_csv(charts))
        page.locator(".tab[data-lv='10']").click()
        page.locator("#unlistedCharts summary").click()
        self.assertEqual(page.locator("#unlistedRows tr").count(),3)
        rows=page.locator("#unlistedRows").inner_text()
        self.assertIn(entries[0]["title"],rows)
        self.assertIn("__TEST_UNKNOWN",rows)
        self.assertNotIn(entries[1]["title"],rows)
        self.assertNotIn(entries[2]["title"],rows)
        for mode in ["hard","normal"]:
            page.locator(f".tab[data-mode='{mode}']").click()
            self.assertEqual(page.locator("#unlistedRows tr").count(),3)
        chart=entries[-1]
        self.assertEqual(page.evaluate("(title)=>rowsFor('10').find(r=>r.title===title).rank",chart["title"]),6)
        page.locator("#source10Button").click()
        page.locator("#source10Menu button").filter(has_text="胡椒").click()
        self.assertNotIn(entries[0]["title"],page.locator("#unlistedRows").inner_text())
        page.locator(".tab[data-lv='11']").click()
        self.assertEqual(page.locator("#unlistedCount").inner_text(),"1")
        self.assertIn("__TEST_UNKNOWN",page.locator("#unlistedRows").inner_text())

    def test_unlisted_safe_text_filters_pagination_and_unchanged_metrics(self):
        page=self.page()
        base=page.evaluate("""()=>LampGridDemo.createCsv([
          {level:9,table:KOSHO9},{level:10,table:TABLES.t10},
          {level:10,table:KOSHO10},{level:11,table:TABLES.t11},{level:12,table:TABLES.t12}
        ],keyOf)""")
        page.evaluate("(text)=>start(text)",base)
        before=page.evaluate("""()=>({
          sum:sum.innerHTML,dist:dist.innerHTML,verdict:verdict.innerHTML,
          reco:reco.innerHTML,next:next.innerHTML,rating:calculateSkillRating().rating
        })""")
        unsafe='<img src=x onerror="window.__csvExecuted=true">'
        charts=[(f"__TEST_EXTRA_{i:02}","A",12,"NO PLAY" if i%2 else "CLEAR",i) for i in range(30)]
        charts.append((unsafe,"L",12,"HARD CLEAR",0))
        extra=score_csv(charts).split("\n",1)[1]
        page.evaluate("(text)=>start(text)",base+"\n"+extra)
        after=page.evaluate("""()=>({
          sum:sum.innerHTML,dist:dist.innerHTML,verdict:verdict.innerHTML,
          reco:reco.innerHTML,next:next.innerHTML,rating:calculateSkillRating().rating
        })""")
        self.assertEqual(after,before)
        page.locator("#unlistedCharts summary").click()
        self.assertEqual(page.locator("#unlistedRows tr").count(),25)
        page.locator("#unlistedMore button").click()
        self.assertEqual(page.locator("#unlistedRows tr").count(),31)
        self.assertIn(unsafe,page.locator("#unlistedRows").inner_text())
        self.assertEqual(page.locator("#unlistedRows img").count(),0)
        self.assertTrue(page.evaluate("typeof window.__csvExecuted==='undefined'"))
        page.locator("#q").fill("__TEST_EXTRA_")
        page.wait_for_function("unlistedStatus.textContent.includes('一致 30譜面')")
        self.assertEqual(page.locator("#unlistedRows tr").count(),25)
        page.locator("#onlyun").check()
        self.assertEqual(page.locator("#unlistedRows tr").count(),15)
        page.evaluate("LIMIT_UNLISTED=50; unlistedCharts.open=true")
        saved=self.storage(page)
        page.locator("#demoAgain").click()
        page.locator(".tab[data-lv='10']").click()
        page.locator("#demoExit").click()
        self.assertTrue(page.evaluate("LIMIT_UNLISTED===50 && unlistedCharts.open"))
        self.assertEqual(self.storage(page),saved)
        self.assertEqual(self.remote,[])

    def rating_fixture(self,page,counts,ranks=None):
        return page.evaluate("""({counts,ranks})=>{
          const fixture={};
          for(const [lv,count] of Object.entries(counts)){
            fixture[lv]=Array.from({length:count},(_,i)=>({
              tier:'F',title:'Fixture '+lv+' '+i+(i%3===0?'(H)':i%3===1?'(L)':''),
              rank:ranks?.[lv]?.[i]??7
            }));
          }
          skillBandsFor=()=>['F','E','D','C','B','B+','A','A+'];
          skillRowsFor=lv=>fixture[lv]||[];
          const result=calculateSkillRating();
          document.getElementById('overallSkill').innerHTML=ratingBreakdownHtml(result);
          return result;
        }""",{"counts":counts,"ranks":ranks})

    def test_rating_actual_pools_caps_ties_and_chart_display(self):
        page=self.page()
        page.locator("#demoStart").click()
        result=self.rating_fixture(page,{12:45,11:20,10:8,9:10})
        self.assertEqual((result["rating"],result["baseRating"],result["totalBonus"]),(1225,1200,25))
        self.assertEqual([r["title"] for r in result["top"]],[f"Fixture 12 {i}"+("(H)" if i%3==0 else "(L)" if i%3==1 else "") for i in range(40)])
        self.assertEqual(len(result["bonusByLevel"]["11"]["rows"]),15)
        self.assertEqual(len(result["bonusByLevel"]["10"]["rows"]),5)
        self.assertNotIn("9",result["bonusByLevel"])
        page.locator("#ratingBreakdown summary").click()
        self.assertEqual(page.locator("[data-rating-role='base'] tbody tr").count(),40)
        for lv in ["11","10"]:
            actual=page.locator(f"[data-rating-role='bonus'][data-rating-level='{lv}'] tbody tr td:nth-child(2)").all_text_contents()
            self.assertEqual(actual,[r["title"] for r in result["bonusByLevel"][lv]["rows"]])
        self.assertEqual(page.locator("[data-rating-role='base'] tbody tr td:nth-child(3)").all_text_contents()[:3],["H","L","A"])
        self.assertIn("画面で選択中の出典",page.locator("#ratingBreakdown").inner_text())

    def test_rating_partial_pools_zero_excess_and_rounding(self):
        page=self.page()
        result=self.rating_fixture(page,{12:1,11:3,10:3},{12:[2],11:[7,2,2],10:[7,2,2]})
        self.assertEqual((result["baseRating"],result["totalBonus"],result["rating"]),(1000,8.4,1008))
        self.assertEqual(result["bonusByLevel"]["11"]["bonus"],6.7)
        self.assertEqual(result["bonusByLevel"]["10"]["bonus"],1.7)
        self.assertEqual(result["bonusByLevel"]["11"]["totalExcess"],100)
        self.assertEqual([r["excess"] for r in result["bonusByLevel"]["11"]["rows"]],[100,0,0])
        self.assertEqual(page.locator("[data-rating-role='base'] tbody tr").count(),1)
        self.assertIn("0（加算0）",page.locator("#ratingBreakdown").text_content())
        result=self.rating_fixture(page,{12:1,11:1,10:1},{12:[2],11:[5],10:[6]})
        self.assertEqual((result["totalBonus"],result["rating"]),(0,1000))
        result=self.rating_fixture(page,{9:1},{9:[2]})
        self.assertEqual(result["rating"],400)
        self.assertIn("Bonus対象はありません",page.locator("#ratingBreakdown").text_content())
        result=self.rating_fixture(page,{9:1},{9:[1]})
        self.assertIsNone(result["rating"])
        self.assertIn("未判定",page.locator("#ratingBreakdown").text_content())

    def test_rating_basis_is_independent_of_selected_table(self):
        page=self.page(mobile=True)
        page.locator("#demoStart").click()
        before=page.evaluate("calculateSkillRating()")
        for source in ["kosho","nask"]:
            for mode in ["normal","hard"]:
                page.evaluate("({source,mode})=>{LV='10';SOURCE10=source;MODE=mode;render()}",{"source":source,"mode":mode})
                self.assertEqual(page.evaluate("calculateSkillRating()"),before)
        page.locator("#ratingBreakdown summary").click()
        page.locator("#unlistedCharts summary").click()
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"),390)


if __name__ == "__main__":
    unittest.main()
