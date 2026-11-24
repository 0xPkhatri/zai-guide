import json
from functools import partial
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest
from urllib import robotparser
from urllib.error import HTTPError
from urllib.request import urlopen
from urllib.parse import urlsplit
from xml.etree import ElementTree

from site_builder import build_site, load_offers, normalize_url, render_article
from serve import StaticHandler
from verify_export import verify_export


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class StaticSiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = build_site("https://savings.test", Path(self.temp.name))

    def test_all_pages_have_unique_metadata_and_resolving_links(self):
        titles, descriptions = set(), set()
        for page in self.root.rglob("*.html"):
            html = page.read_text()
            doc = Document(html)
            self.assertEqual(sum(t == "h1" for t, _ in doc.tags), 1)
            self.assertNotIn("noindex", html.lower())
            title = html.split("<title>")[1].split("</title>")[0]
            description = next(a["content"] for t, a in doc.tags if t == "meta" and a.get("name") == "description")
            self.assertNotIn(title, titles)
            self.assertNotIn(description, descriptions)
            titles.add(title)
            descriptions.add(description)
            for tag, attrs in doc.tags:
                link = attrs.get("href", "")
                if link.startswith("/"):
                    target = self.root / link.lstrip("/")
                    self.assertTrue(target.is_file() or (target / "index.html").is_file(), link)
                if tag == "script":
                    self.assertEqual(attrs.get("type"), "application/ld+json")
            if page.name != "404.html":
                canonical = next(a["href"] for t, a in doc.tags if t == "link" and a.get("rel") == "canonical")
                expected_path = "/" if page.parent == self.root else "/" + page.parent.relative_to(self.root).as_posix() + "/"
                self.assertEqual(canonical, "https://savings.test" + expected_path)

    def test_article_and_structured_data_match_without_javascript(self):
        offer = load_offers()[0]
        html = (self.root / "offers/zai-discount/index.html").read_text()
        doc = Document(html)
        self.assertEqual(sum(t == "h2" for t, _ in doc.tags), 4)
        self.assertEqual(sum(t == "h3" for t, _ in doc.tags), 8)
        ctas = [a for t, a in doc.tags if t == "a" and a.get("class") == "button"]
        self.assertEqual(len(ctas), 1)
        self.assertEqual(ctas[0]["href"], offer["offer_url"])
        self.assertIn("sponsored", ctas[0]["rel"])
        schema = json.loads(html.split('<script type="application/ld+json">')[1].split("</script>")[0])
        self.assertEqual(schema["@type"], "Article")
        self.assertEqual(schema["headline"], offer["heading"])
        self.assertEqual(schema["dateModified"], offer["last_verified_date"])
        self.assertEqual(schema["url"], "https://savings.test/offers/zai-discount/")
        self.assertNotIn("aggregateRating", schema)
        self.assertNotIn("datePublished", schema)
        self.assertIn("72 hours", html)
        self.assertIn("US$0.50", html)
        self.assertNotIn("Created locally", html)
        self.assertNotIn("not yet confirmed as publicly published", html)
        self.assertIn("November 24, 2026", html)
        self.assertNotIn("price comparison has not been verified", html)
        self.assertNotIn("discount searches", html)
        self.assertNotIn("Searches for", html)
        referral_links = [a for t, a in doc.tags if t == "a" and a.get("href") == offer["offer_url"]]
        self.assertEqual(len(referral_links), 2)
        for link in referral_links:
            self.assertIn("sponsored", link["rel"].split())
        self.assertIn("Find the latest discount offer", html)

    def test_sitemap_and_crawler_rules(self):
        xml = ElementTree.parse(self.root / "sitemap.xml")
        urls = [node.text for node in xml.findall(".//{*}loc")]
        self.assertEqual(len(urls), 6)
        for url in urls:
            self.assertEqual(urlsplit(url).netloc, "savings.test")
            self.assertTrue((self.root / urlsplit(url).path.lstrip("/") / "index.html").exists())
        self.assertEqual((self.root / "robots.txt").read_text(), "User-agent: *\nAllow: /\n\nSitemap: https://savings.test/sitemap.xml\n")
        self.assertFalse((self.root / "guides").exists())

    def test_production_rejects_placeholder_origins(self):
        for url in ("http://localhost:8000", "https://example.com", "https://site.example", "https://real.test/path",
                    "https://LOCALHOST", "https://localhost.", "https://app.localhost", "https://127.0.0.2",
                    "https://[::1]", "https://[::]", "https://192.168.1.5", "https://0.0.0.0",
                    "https://2130706433", "https://127.1", "https://app.local", "https://user@real.test"):
            with self.assertRaises(ValueError):
                normalize_url(url)
        self.assertEqual(normalize_url("http://localhost:8000", preview=True), "http://localhost:8000")

    def test_rebuild_updates_generated_files(self):
        build_site("https://new.test", self.root)
        self.assertIn("https://new.test/", (self.root / "sitemap.xml").read_text())

    def test_production_export_guard(self):
        self.assertEqual(verify_export(self.root), "https://savings.test")
        article = self.root / "offers/zai-discount/index.html"
        article.write_text(article.read_text().replace("https://savings.test/offers/zai-discount/", "http://localhost:8000/offers/zai-discount/"))
        with self.assertRaises(ValueError):
            verify_export(self.root)

    def test_preview_artifacts_cannot_pass_deployment_check(self):
        build_site("http://localhost:8000", self.root, preview=True)
        with self.assertRaises(ValueError):
            verify_export(self.root)

    def test_schema_url_validation_cannot_be_skipped(self):
        article = self.root / "offers/zai-discount/index.html"
        html = article.read_text()
        script = html.split('<script type="application/ld+json">')[1].split("</script>")[0]
        schema = json.loads(script)
        schema["url"] = "https://wrong.test/offers/zai-discount/"
        article.write_text(html.replace(script, json.dumps(schema)))
        with self.assertRaisesRegex(ValueError, "Structured data URL mismatch"):
            verify_export(self.root)

    def test_streamlit_article_omits_static_only_navigation(self):
        html = render_article(load_offers()[0], internal_links=False)
        self.assertFalse(any(a.get("href", "").startswith("/") for _, a in Document(html).tags))
        self.assertIn("The website owner may receive Z.ai credits", html)

    def test_crawlers_and_accessible_structure(self):
        robots = robotparser.RobotFileParser()
        robots.parse((self.root / "robots.txt").read_text().splitlines())
        for bot in ("Googlebot", "Bingbot", "OAI-SearchBot"):
            self.assertTrue(robots.can_fetch(bot, "https://savings.test/offers/zai-discount/"))
        doc = Document((self.root / "offers/zai-discount/index.html").read_text())
        ids = {a["id"] for _, a in doc.tags if "id" in a}
        self.assertTrue(any(t == "html" and a.get("lang") == "en" for t, a in doc.tags))
        self.assertTrue(any(t == "meta" and a.get("name") == "viewport" for t, a in doc.tags))
        self.assertTrue(any(t == "main" for t, _ in doc.tags))
        for _, attrs in doc.tags:
            if attrs.get("href", "").startswith("#"):
                self.assertIn(attrs["href"][1:], ids)
            if "aria-labelledby" in attrs:
                self.assertTrue(set(attrs["aria-labelledby"].split()) <= ids)

    def test_initial_http_response_and_status_codes(self):
        class QuietHandler(StaticHandler):
            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(self.root)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            origin = f"http://127.0.0.1:{server.server_port}"
            with urlopen(origin + "/offers/zai-discount/") as response:
                html = response.read().decode()
                self.assertEqual(response.status, 200)
                self.assertIsNone(response.headers.get("X-Robots-Tag"))
            offer = load_offers()[0]
            self.assertIn(offer["introduction"], html)
            for faq in offer["faqs"]:
                self.assertIn(faq["question"], html)
                self.assertIn(faq["answer"], html)
            for _, attrs in Document(html).tags:
                href = attrs.get("href", "")
                if href.startswith("/"):
                    with urlopen(origin + href) as internal:
                        self.assertEqual(internal.status, 200)
            with self.assertRaises(HTTPError) as error:
                urlopen(origin + "/missing-page/")
            self.assertEqual(error.exception.code, 404)
            error.exception.close()
            connection = HTTPConnection("127.0.0.1", server.server_port)
            try:
                connection.request("GET", "/offers/zai-discount")
                redirect = connection.getresponse()
                self.assertIn(redirect.status, (301, 308))
                self.assertEqual(redirect.getheader("Location"), "/offers/zai-discount/")
                redirect.read()
            finally:
                connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
