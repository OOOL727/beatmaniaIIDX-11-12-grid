import functools
import http.server
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
CONSENT = "lampgrid.analyticsConsent.v1"
MARKER = "PRIVATE_SCORE_MARKER_714"
CSV = (
    "タイトル,HYPER 難易度,HYPER クリアタイプ,HYPER ミスカウント,"
    "ANOTHER 難易度,ANOTHER クリアタイプ,ANOTHER ミスカウント\n"
    + MARKER + ",12,HARD CLEAR,27,12,CLEAR,31"
)
SCORE_KEYS = ["lampgrid.csv", "lampgrid.at", "lampgrid.snap", "lampgrid.opt"]
ASSETS = {
    "/", "/index.html", "/sw.js", "/manifest.webmanifest",
    "/analytics-config.js", "/analytics.js", "/demo.js", "/social-preview.png",
    "/icon-180.png", "/icon-192.png", "/icon-512.png", "/icon-512-maskable.png",
}


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
            "LAMPGRID_BROWSER_PATH",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
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
        self.contexts = []
        self.errors = []
        self.remote = []

    def tearDown(self):
        for context in self.contexts:
            context.close()
        self.assertEqual(self.errors, [], "Application JavaScript errors")

    def page(self, configured=False, consent=None, seed=None, fail_tag=False,
             query="", mobile=False, service_worker=False, block_helper=False):
        context = self.browser.new_context(
            service_workers="allow" if service_worker else "block",
            viewport={"width": 390, "height": 844} if mobile else {"width": 1280, "height": 900},
        )
        self.contexts.append(context)
        values = dict(seed or {})
        if consent is not None:
            values[CONSENT] = consent
        if values:
            context.add_init_script(
                "(() => {const values=" + json.dumps(values)
                + "; for(const [k,v] of Object.entries(values))"
                + " if(localStorage.getItem(k)===null) localStorage.setItem(k,v);})();"
            )

        def route(request_route):
            request = request_route.request
            url = urlsplit(request.url)
            if url.netloc == urlsplit(self.base).netloc:
                if block_helper and url.path == "/analytics.js":
                    request_route.abort()
                elif configured and url.path == "/analytics-config.js":
                    request_route.fulfill(
                        content_type="application/javascript",
                        body="window.LAMPGRID_ANALYTICS_CONFIG=" + json.dumps({
                            "enabled": True, "measurementId": "G-TEST123",
                            "allowedOrigins": [self.base.rstrip("/")],
                        }) + ";",
                    )
                else:
                    request_route.continue_()
                return
            self.remote.append((request.url, request.post_data, request.headers))
            if url.hostname == "www.googletagmanager.com" and not fail_tag:
                request_route.fulfill(
                    content_type="application/javascript",
                    body='document.cookie="lampgrid_ga=stub; path=/; SameSite=Lax";',
                )
            else:
                request_route.abort()

        context.route("**/*", route)
        page = context.new_page()
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        page.goto(self.base + query, wait_until="domcontentloaded")
        page.wait_for_function("typeof enterDemo==='function' && window.LampGridDemo")
        return page

    def events(self, page):
        return page.evaluate(
            "() => (window.dataLayer || []).filter(x => x[0]==='event')"
            ".map(x => ({name:x[1],params:x[2]}))"
        )

    def storage(self, page):
        return page.evaluate(
            "(keys) => Object.fromEntries(keys.map(k=>[k,localStorage.getItem(k)]))", SCORE_KEYS
        )

    def grant(self, page):
        page.locator("#analyticsChoice [data-analytics-choice='granted']").click()
        page.wait_for_function(
            "() => (window.dataLayer||[]).some(x=>x[0]==='event'&&x[1]==='page_view')"
        )

    def test_default_disabled_and_refusal_make_no_google_requests(self):
        page = self.page()
        page.locator("#demoStart").click()
        page.locator(".tab[data-lv='10']").click()
        page.locator(".tab[data-mode='hard']").click()
        self.assertEqual(self.remote, [])
        self.assertEqual(self.events(page), [])
        page.locator("#demoExit").click()
        page.locator("footer [data-open-privacy]").click()
        self.assertIn("未設定", page.locator("#analyticsStatus").inner_text())
        self.assertTrue(page.locator("#privacyDialog [data-analytics-choice='granted']").is_disabled())
        for consent in [None, "denied"]:
            with self.subTest(consent=consent):
                other = self.page(configured=True, consent=consent)
                other.locator("#demoStart").click()
                other.locator("#q").fill(MARKER)
                if consent is None:
                    other.locator("#analyticsChoice [data-analytics-choice='denied']").click()
                    other.reload(wait_until="domcontentloaded")
                self.assertEqual(self.events(other), [])
                self.assertEqual(other.context.cookies(), [])
        self.assertEqual(self.remote, [])

    def test_public_origin_configuration_is_also_disabled(self):
        context = self.browser.new_context(service_workers="block")
        self.contexts.append(context)
        public = "https://oool727.github.io/beatmaniaIIDX-11-12-grid/"

        def route(request_route):
            url = urlsplit(request_route.request.url)
            if request_route.request.url.startswith(public):
                path = "/" + unquote(url.path[len("/beatmaniaIIDX-11-12-grid/"):])
                if path in ASSETS:
                    file = ROOT / (path.lstrip("/") or "index.html")
                    request_route.fulfill(
                        content_type=mimetypes.guess_type(str(file))[0] or "application/octet-stream",
                        body=file.read_bytes(),
                    )
                    return
            self.remote.append((request_route.request.url, None, {}))
            request_route.abort()

        context.route("**/*", route)
        page = context.new_page()
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        page.goto(public, wait_until="domcontentloaded")
        page.locator("#demoStart").click()
        self.assertTrue(page.locator("#demoBanner").is_visible())
        self.assertFalse(page.locator("#analyticsChoice").is_visible())
        self.assertEqual(self.remote, [])
        self.assertEqual(self.events(page), [])
        self.assertEqual(context.cookies(), [])

    def test_unrecognized_campaign_and_referrer_are_omitted(self):
        page = self.page(configured=True)
        page.goto(self.base + "?utm_source=x&utm_medium=social&utm_campaign=" + MARKER,
                  referer="https://" + MARKER.lower() + ".example/private?q=" + MARKER,
                  wait_until="domcontentloaded")
        self.grant(page)
        config = page.evaluate("() => Array.from(dataLayer.find(x=>x[0]==='config'))[2]")
        self.assertNotIn("campaign_name", config)
        self.assertEqual(config["page_referrer"], "")
        self.assertNotIn(MARKER.lower(), page.evaluate("() => JSON.stringify(dataLayer)").lower())

    def test_consent_allowlist_no_replay_and_safe_attribution(self):
        page = self.page(
            configured=True,
            query="?utm_source=x&utm_medium=social&utm_campaign=launch&q=" + MARKER + "#" + MARKER,
        )
        page.locator("#demoStart").click()
        page.locator("#q").fill(MARKER)
        self.assertEqual(self.remote, [])
        self.grant(page)
        self.assertEqual([x["name"] for x in self.events(page)], ["page_view"])
        page.locator("#q").fill(MARKER + "_SECOND")
        page.locator("#q").fill(MARKER + "_THIRD")
        page.locator(".tab[data-lv='10']").click()
        page.locator(".tab[data-mode='hard']").click()
        page.locator("#source10Button").click()
        page.locator("#source10Menu button").filter(has_text="胡椒").click()
        before = self.events(page)
        page.evaluate("render(); render()")
        page.locator(".tab[data-mode='hard']").click()
        self.assertEqual(self.events(page), before)
        self.assertEqual(sum(x["name"] == "search_use" for x in before), 1)
        self.assertEqual(sum(x["name"] == "table_change" for x in before), 3)
        self.assertEqual(before[-1]["params"], {
            "level": "10", "mode": "hard", "source": "kosho", "context": "demo",
        })
        self.assertFalse(page.evaluate(
            "() => LampGridAnalytics.track('table_change',{level:'10',mode:'hard',"
            "source:'kosho',context:'demo',query:'" + MARKER + "'})"
        ))
        self.assertFalse(page.evaluate("() => LampGridAnalytics.track('toString',{})"))
        layer = page.evaluate("() => JSON.stringify(window.dataLayer)")
        self.assertNotIn(MARKER, layer)
        config = page.evaluate("() => Array.from(dataLayer.find(x=>x[0]==='config'))[2]")
        self.assertEqual(config["campaign_name"], "launch")
        self.assertEqual(config["page_location"], "https://oool727.github.io/beatmaniaIIDX-11-12-grid/")
        self.assertFalse(config["send_page_view"])
        self.assertFalse(config["allow_google_signals"])
        self.assertEqual(config["cookie_prefix"], "lampgrid")
        self.assertEqual(len(self.remote), 1)
        self.assertNotIn("referer", self.remote[0][2])
        self.assertNotIn(MARKER, json.dumps(self.remote))

    def test_manual_import_failure_and_restore_are_separate(self):
        page = self.page(configured=True)
        self.grant(page)
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
        page.locator("#pastearea").fill(CSV)
        page.locator("#doPaste").click()
        page.evaluate("() => { File.prototype.text=()=>Promise.reject(new Error('" + MARKER + "')); }")
        page.locator("#f2").set_input_files({
            "name": MARKER + "_unreadable.csv", "mimeType": "text/csv", "buffer": b"synthetic",
        })
        page.wait_for_function("err.textContent.includes('ファイルを読み込めません')")
        events = self.events(page)
        self.assertEqual(sum(x["name"] == "demo_start" for x in events), 1)
        self.assertEqual([x["params"]["method"] for x in events if x["name"] == "score_import_success"], ["csv", "paste"])
        self.assertEqual([x["params"]["reason"] for x in events if x["name"] == "score_import_failure"], ["invalid_input", "empty_input", "read_error"])
        self.assertNotIn(MARKER, page.evaluate("() => JSON.stringify(dataLayer)"))
        self.assertNotIn(MARKER, json.dumps(self.remote))
        page.reload(wait_until="domcontentloaded")
        page.wait_for_function("Object.keys(SCORE).length===2")
        page.wait_for_function("(dataLayer||[]).some(x=>x[1]==='saved_data_restore')")
        self.assertEqual([x["name"] for x in self.events(page)], ["page_view", "saved_data_restore"])

    def test_demo_preserves_all_real_storage_and_view_state(self):
        page = self.page()
        page.evaluate("(csv)=>start(csv)", CSV)
        page.locator(".tab[data-lv='10']").click()
        page.locator(".tab[data-mode='hard']").click()
        page.locator("#q").fill("ORIGINAL_SEARCH")
        page.locator("#names").check()
        page.wait_for_timeout(150)
        before = self.storage(page)
        original = page.evaluate("() => ({score:JSON.stringify(SCORE),lv:LV,mode:MODE,q:q.value,open:[...OPEN]})")
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
                page.locator("#source10Button").click()
                page.locator("#source10Menu button").filter(has_text="胡椒").click()
        page.locator("#onlyun").check()
        page.locator("#scrweak").check()
        page.locator("#q").fill(MARKER)
        page.evaluate("OPEN.add('test-tier'); saveOpt()")
        self.assertEqual(self.storage(page), before)
        page.locator("#clear").click()
        self.assertEqual(self.storage(page), before)
        restored = page.evaluate("() => ({score:JSON.stringify(SCORE),lv:LV,mode:MODE,q:q.value,open:[...OPEN]})")
        self.assertEqual(restored, original)
        self.assertFalse(page.locator("#demoBanner").is_visible())
        page.locator("#demoAgain").click()
        page.locator("#demoExit").click()
        self.assertEqual(self.storage(page), before)

    def test_failed_import_during_demo_keeps_real_data(self):
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

    def test_revocation_in_another_tab_stops_both_tabs(self):
        page = self.page(configured=True)
        self.grant(page)
        other = page.context.new_page()
        other.on("pageerror", lambda error: self.errors.append(str(error)))
        other.goto(self.base, wait_until="domcontentloaded")
        other.wait_for_function("(dataLayer||[]).some(x=>x[1]==='page_view')")
        other.locator("footer [data-open-privacy]").click()
        with page.expect_navigation(wait_until="domcontentloaded"), other.expect_navigation(wait_until="domcontentloaded"):
            other.locator("#privacyDialog [data-analytics-choice='denied']").click()
        requests = len(self.remote)
        for tab in [page, other]:
            tab.locator("#demoStart").click()
            self.assertEqual(self.events(tab), [])
        self.assertEqual(len(self.remote), requests)

    def test_revoke_stops_tracking_and_removes_only_app_cookies(self):
        page = self.page(configured=True, seed={"lampgrid.csv": CSV, "lampgrid.at": "1700000000000"})
        self.grant(page)
        page.evaluate("document.cookie='other_app=keep; path=/'")
        before = self.storage(page)
        page.locator("footer [data-open-privacy]").click()
        with page.expect_navigation(wait_until="domcontentloaded"):
            page.locator("#privacyDialog [data-analytics-choice='denied']").click()
        requests = len(self.remote)
        page.locator("#q").fill(MARKER)
        self.assertEqual(len(self.remote), requests)
        self.assertEqual(self.events(page), [])
        self.assertEqual(self.storage(page), before)
        cookies = {cookie["name"]: cookie["value"] for cookie in page.context.cookies()}
        self.assertEqual(cookies, {"other_app": "keep"})
        self.assertEqual(page.evaluate("(k)=>localStorage.getItem(k)", CONSENT), "denied")

    def test_storage_failure_revocation_does_not_reload_into_old_grant(self):
        page = self.page(configured=True, consent="granted")
        page.wait_for_function("(dataLayer||[]).some(x=>x[1]==='page_view')")
        page.evaluate("""() => {
          const original=Storage.prototype.setItem;
          Storage.prototype.setItem=function(k,v){
            if(k==='lampgrid.analyticsConsent.v1') throw new DOMException('blocked','SecurityError');
            return original.call(this,k,v);
          };
        }""")
        page.locator("footer [data-open-privacy]").click()
        page.locator("#privacyDialog [data-analytics-choice='denied']").click()
        before = self.events(page)
        page.evaluate("LampGridAnalytics.track('demo_start',{entry:'welcome'})")
        self.assertEqual(self.events(page), before)
        self.assertTrue(page.evaluate("window['ga-disable-G-TEST123']"))
        self.assertTrue(page.locator("#privacyDialog").is_visible())
        self.assertIn("保持は保証できない", page.locator("#analyticsStatus").inner_text())
        self.assertEqual(page.context.cookies(), [])

    def test_mobile_choice_is_equal_and_does_not_gate_app(self):
        page = self.page(configured=True, mobile=True)
        page.locator("#demoStart").click()
        self.assertTrue(page.locator("#demoBanner").is_visible())
        styles = page.locator("#analyticsChoice").evaluate("""el => {
          const buttons=[...el.querySelectorAll('button[data-analytics-choice]')];
          return buttons.map(b=>{
            const s=getComputedStyle(b);
            return [s.backgroundColor,s.color,s.borderColor,s.fontWeight,b.getBoundingClientRect().height];
          });
        }""")
        self.assertEqual(styles[0], styles[1])
        self.assertGreaterEqual(styles[0][-1], 44)
        page.locator("#analyticsChoice [data-open-privacy]").click()
        self.assertTrue(page.locator("#privacyDialog").is_visible())
        page.keyboard.press("Escape")
        self.assertFalse(page.locator("#privacyDialog").is_visible())
        self.assertEqual(self.remote, [])

    def test_blocked_analytics_does_not_break_demo(self):
        page = self.page(configured=True, fail_tag=True)
        page.locator("#analyticsChoice [data-analytics-choice='granted']").click()
        page.locator("#demoStart").click()
        page.locator(".tab[data-lv='10']").click()
        page.locator(".tab[data-mode='hard']").click()
        page.locator("footer [data-open-privacy]").click()
        page.wait_for_function("analyticsStatus.textContent.includes('接続できません')")
        self.assertGreater(page.evaluate("rowsFor(LV).length"), 0)
        self.assertEqual(self.events(page), [])

    def test_blocked_local_helper_preserves_feedback_and_privacy_ui(self):
        page = self.page(configured=True, block_helper=True)
        page.locator("#demoStart").click()
        page.locator("[data-open-feedback='toolbar']").click()
        self.assertTrue(page.locator("#feedbackDialog").is_visible())
        page.keyboard.press("Escape")
        page.locator("footer [data-open-privacy]").click()
        self.assertIn("読み込めません", page.locator("#analyticsStatus").inner_text())
        self.assertTrue(page.locator("#privacyDialog [data-analytics-choice='granted']").is_disabled())
        self.assertEqual(self.remote, [])

    def test_feedback_and_sharing_contain_no_user_data(self):
        page = self.page(configured=True)
        self.grant(page)
        page.evaluate("(csv)=>start(csv)", CSV)
        page.locator("#q").fill(MARKER)
        page.locator("[data-open-feedback='header']").click()
        self.assertIn("公開", page.locator("#feedbackDialog").inner_text())
        for kind, filename in [
            ("bug", "bug_report.yml"), ("feature", "feature_request.yml"), ("feedback", "feedback.yml")
        ]:
            link = page.locator(f"[data-feedback-kind='{kind}']")
            parsed = urlsplit(link.get_attribute("href"))
            self.assertEqual(parsed.netloc, "github.com")
            self.assertEqual(parse_qs(parsed.query), {"template": [filename]})
            link.evaluate("el=>el.addEventListener('click',e=>e.preventDefault(),{once:true})")
            link.click()
            form = yaml.safe_load((ROOT / ".github" / "ISSUE_TEMPLATE" / filename).read_text(encoding="utf-8"))
            self.assertNotIn("labels", form)
            self.assertIn("公開", form["body"][0]["attributes"]["value"])
        page.keyboard.press("Escape")
        link = page.locator("[data-share-entry='header']")
        share = urlsplit(link.get_attribute("href"))
        self.assertEqual(share.netloc, "x.com")
        self.assertEqual(parse_qs(urlsplit(parse_qs(share.query)["url"][0]).query), {
            "utm_source": ["x"], "utm_medium": ["social"], "utm_campaign": ["share"],
        })
        link.evaluate("el=>el.addEventListener('click',e=>e.preventDefault(),{once:true})")
        link.click()
        self.assertEqual(sum(x["name"] == "feedback_open" for x in self.events(page)), 3)
        self.assertEqual(sum(x["name"] == "share_open" for x in self.events(page)), 1)
        self.assertNotIn(MARKER, page.evaluate("() => JSON.stringify(dataLayer)"))
        self.assertNotIn(MARKER, json.dumps(self.remote))

    def test_offline_assets_and_service_worker_boundaries(self):
        page = self.page(service_worker=True, fail_tag=True)
        page.evaluate("() => navigator.serviceWorker.ready")
        page.wait_for_function("navigator.serviceWorker.controller")
        page.evaluate("() => caches.open('another-app-v1').then(c=>c.put('/unrelated',new Response('keep')))")
        cached = page.evaluate(
            "() => caches.open('lampgrid-v20').then(c=>c.keys()).then(rs=>rs.map(r=>r.url))"
        )
        self.assertTrue(any(url.endswith("/demo.js") for url in cached))
        self.assertTrue(all(url.startswith(self.base) for url in cached))
        page.context.set_offline(True)
        page.reload(wait_until="domcontentloaded")
        page.locator("#demoStart").click()
        page.locator(".tab[data-lv='10']").click()
        self.assertGreater(page.evaluate("rowsFor(LV).length"), 0)
        self.assertTrue(page.evaluate("() => caches.has('another-app-v1')"))
        results = page.evaluate("""async () => {
          const failed=[];
          for(const url of ['https://www.googletagmanager.com/gtag/js?id=G-TEST123','missing-script.js']){
            try {const response=await fetch(url); failed.push(!response.ok);}
            catch {failed.push(true);}
          }
          return failed;
        }""")
        self.assertEqual(results, [True, True])
        page.context.set_offline(False)

    def test_preview_metadata_and_image(self):
        page = self.page()
        url = page.locator("meta[property='og:image']").get_attribute("content")
        self.assertEqual(url, "https://oool727.github.io/beatmaniaIIDX-11-12-grid/social-preview.png")
        self.assertEqual(page.locator("meta[name='twitter:card']").get_attribute("content"), "summary_large_image")
        image = page.request.get(self.base + "social-preview.png")
        self.assertTrue(image.ok)
        body = image.body()
        self.assertEqual(body[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", body[16:24]), (1200, 630))


if __name__ == "__main__":
    unittest.main()
