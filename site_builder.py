"""Render the existing offer as static HTML; no runtime web framework required."""
import argparse
from datetime import date
import json
import ipaddress
from pathlib import Path
import re
from urllib.parse import urlsplit
from xml.etree.ElementTree import Element, SubElement, tostring

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent
SITE_NAME = "Software Savings Notes"
PAGES = {
    "/": ("Software Savings Notes", "Independent software discount guides, with sources and clear eligibility details.", "home"),
    "/offers/": ("Software Discount Offers", "Browse documented software subscription offers and eligibility guides.", "offers"),
    "/about/": ("About Software Savings Notes", "How this independent software savings guide checks and explains offers.", "about"),
    "/affiliate-disclosure/": ("Affiliate and Referral Disclosure", "How referral links and Z.ai credits support this independent guide.", "disclosure"),
    "/privacy-policy/": ("Privacy Policy", "How this static website handles visitor data and external links.", "privacy"),
}


def load_offers():
    offers = json.loads((ROOT / "content/offers.json").read_text())
    slugs = set()
    for offer in offers:
        for field in ("product_name", "category", "page_title", "heading", "button_label", "section_headings", "slug", "meta_description",
                      "offer_description", "discount_percentage", "invitation_id", "offer_url",
                      "eligibility_summary", "offer_status", "publication_date", "last_verified_date",
                      "affiliate_disclosure", "steps", "eligibility_conditions", "pricing_notes",
                      "faqs", "official_sources", "related_guides"):
            if field not in offer:
                raise ValueError(f"Missing content field: {field}")
        slug = offer["slug"]
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) or slug in slugs:
            raise ValueError("Offer slugs must be unique, lowercase URL segments")
        slugs.add(slug)
        published = date.fromisoformat(offer["publication_date"])
        verified = date.fromisoformat(offer["last_verified_date"])
        if published > date.today() or verified > date.today():
            raise ValueError("Content dates must not be in the future")
        if urlsplit(offer["offer_url"]).scheme != "https":
            raise ValueError("Offer links must use HTTPS")
        offer["path"] = f"/offers/{slug}/"
    valid_paths = set(PAGES) | {o["path"] for o in offers}
    for offer in offers:
        if any(g["path"] not in valid_paths for g in offer["related_guides"]):
            raise ValueError("Related guides must link to an existing page")
    return offers


def normalize_url(value, preview=False):
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username is not None or parsed.password is not None:
        raise ValueError("Use an origin such as https://your-domain.com, without a path")
    hostname = parsed.hostname.lower().rstrip(".")
    # Accessing port also validates malformed or out-of-range port numbers.
    port = parsed.port
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    local = (hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal"))
             or (address is not None and not address.is_global)
             or (address is None and ("." not in hostname or re.fullmatch(r"[0-9.]+", hostname))))
    placeholder = hostname in {"example.com", "example.org", "example.net"} or hostname.endswith((".example", ".example.com", ".example.org", ".example.net"))
    if not preview and (parsed.scheme != "https" or local or placeholder):
        raise ValueError("Production requires the real public HTTPS origin; use --preview for localhost")
    host = f"[{hostname}]" if ":" in hostname else hostname
    return f"{parsed.scheme}://{host}" + (f":{port}" if port is not None else "")


def template_environment():
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html", "xml"]))
    env.filters["readable_date"] = lambda value: date.fromisoformat(value).strftime("%B %d, %Y").replace(" 0", " ")
    return env


def render_article(offer, internal_links=True, include_heading=True):
    return template_environment().get_template("article.html").render(
        offer=offer, internal_links=internal_links, include_heading=include_heading)


def build_site(base_url, output=None, preview=False):
    base_url = normalize_url(base_url, preview)
    offers = load_offers()
    env = template_environment()
    output = Path(output if output is not None else ROOT / ("preview" if preview else "dist")).resolve()
    if preview and output == (ROOT / "dist").resolve():
        raise ValueError("Preview builds must not overwrite the production dist directory")
    # Do not erase arbitrary folders or leave old generated routes in place.
    manifest = output / "build-manifest.json"
    if manifest.exists():
        for previous in json.loads(manifest.read_text())["files"]:
            path = (output / previous).resolve()
            if path.is_relative_to(output) and path.is_file():
                path.unlink()
    output.mkdir(parents=True, exist_ok=True)
    written = []

    def write(relative, content):
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(relative)

    routes = dict(PAGES)
    for offer in offers:
        routes[offer["path"]] = (offer["page_title"], offer["meta_description"], "article")
    for path, (title, description, kind) in routes.items():
        offer = next((o for o in offers if o["path"] == path), None)
        canonical = base_url + path
        schema = None
        if offer:
            schema = {"@context": "https://schema.org", "@type": "Article",
                      "headline": offer["heading"], "description": description,
                      "dateCreated": offer["publication_date"],
                      "dateModified": offer["last_verified_date"],
                      "mainEntityOfPage": canonical, "url": canonical,
                      "about": {"@type": "Thing", "name": offer["product_name"]}}
            if offer.get("publicly_published"):
                schema["datePublished"] = offer["publication_date"]
        html = env.get_template("page.html").render(
            title=title, description=description, canonical=canonical, kind=kind,
            site_name=SITE_NAME, offer=offer, offers=offers, schema=schema, not_found=False)
        write("index.html" if path == "/" else path.strip("/") + "/index.html", html)
    write("404.html", env.get_template("page.html").render(
        title="Page not found", description="This page does not exist.", canonical=None,
        kind="404", site_name=SITE_NAME, offers=offers, schema=None, not_found=True))
    write("styles.css", (ROOT / "assets/styles.css").read_text())
    # Google requires these files unchanged at the property's root URL.
    for verification in ROOT.glob("google*.html"):
        if not re.fullmatch(r"google[a-f0-9]+\.html", verification.name):
            continue
        content = verification.read_text()
        if content.strip() != f"google-site-verification: {verification.name}":
            raise ValueError(f"Unexpected Google verification content: {verification.name}")
        write(verification.name, content)
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {base_url}/sitemap.xml\n")
    xml = Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for path in routes:
        entry = SubElement(xml, "url")
        SubElement(entry, "loc").text = base_url + path
        offer = next((o for o in offers if o["path"] == path), None)
        if offer:
            SubElement(entry, "lastmod").text = offer["last_verified_date"]
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(xml, encoding="unicode"))
    write("_headers", "/styles.css\n  Cache-Control: public, max-age=3600\n/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n")
    manifest.write_text(json.dumps({"base_url": base_url, "preview": preview, "files": written}, indent=2))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path, help="Defaults to dist for production, preview for local builds")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    print(build_site(args.base_url, args.output, args.preview))
