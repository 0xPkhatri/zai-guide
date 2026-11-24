"""Refuse preview artifacts or local SEO URLs before a public upload."""
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib import robotparser
from urllib.parse import urlsplit
from xml.etree import ElementTree

from site_builder import ROOT, normalize_url


class Tags(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.items = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.items.append((tag, dict(attrs)))


def verify_export(directory=ROOT / "dist"):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "build-manifest.json").read_text())
    if manifest.get("preview") is not False:
        raise ValueError("Preview artifacts cannot be deployed; rebuild with the public HTTPS origin")
    origin = normalize_url(manifest["base_url"])
    for path in directory.rglob("*.html"):
        html = path.read_text()
        tags = Tags(html).items
        for url in re.findall(r'https?://[^\s<>"\\]+', html):
            # External official sources and referral destinations remain allowed.
            normalize_url(f"{urlsplit(url).scheme}://{urlsplit(url).netloc}")
        if "noindex" in html.lower():
            raise ValueError(f"Unexpected noindex in {path}")
        if path.name == "404.html":
            continue
        route = "/" if path.parent == directory else "/" + path.parent.relative_to(directory).as_posix() + "/"
        expected = origin + route
        canonical = [a.get("href") for t, a in tags if t == "link" and a.get("rel") == "canonical"]
        og = [a.get("content") for t, a in tags if t == "meta" and a.get("property") == "og:url"]
        if canonical != [expected] or og != [expected]:
            raise ValueError(f"Canonical or Open Graph origin mismatch in {path}")
        scripts = re.findall(re.escape('<script type="application/ld+json">') + r'(.*?)</script>', html, re.S)
        if any(tag == "article" for tag, _ in tags) and len(scripts) != 1:
            raise ValueError(f"Article must have exactly one structured data block in {path}")
        for script in scripts:
            schema = json.loads(script)
            if schema.get("url") != expected or schema.get("mainEntityOfPage") != expected:
                raise ValueError(f"Structured data URL mismatch in {path}")
    sitemap = ElementTree.parse(directory / "sitemap.xml")
    for node in sitemap.findall(".//{*}loc"):
        if not node.text.startswith(origin + "/"):
            raise ValueError("Sitemap URL uses the wrong origin")
        route = directory / urlsplit(node.text).path.lstrip("/") / "index.html"
        if not route.is_file():
            raise ValueError("Sitemap points to a missing page")
    robots = robotparser.RobotFileParser()
    robots.parse((directory / "robots.txt").read_text().splitlines())
    for bot in ("Googlebot", "Bingbot", "OAI-SearchBot"):
        if not robots.can_fetch(bot, origin + "/offers/zai-discount/"):
            raise ValueError(f"{bot} is blocked")
    if robots.site_maps() != [origin + "/sitemap.xml"]:
        raise ValueError("Robots sitemap URL mismatch")
    return origin


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    print(f"Production export checks passed: {verify_export(args.directory)}")
