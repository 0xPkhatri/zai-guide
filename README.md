# Software Savings Notes

The existing Streamlit app is now a management preview and static export interface.
Python and Jinja2 generate the public website from shared content and templates.

## Run locally

The existing `.venv` already includes Python, Streamlit and Jinja2:

```sh
source .venv/bin/activate
python site_builder.py --base-url http://localhost:8000 --preview
python serve.py
```

Open http://localhost:8000/offers/zai-discount/ . Stop with Ctrl+C.
Run `streamlit run app.py` separately for the clean Streamlit article.
To show the optional management/export sidebar, use `streamlit run app.py -- --manage`.
Edit `content/offers.json` in your editor; this management interface does not yet
provide a content editor. Do not expose management controls as public admin access.

Fresh environment: `python3 -m venv .venv`, then
`.venv/bin/python -m pip install -r requirements.txt`.
Static builds alone need only `requirements-static.txt`.

## Architecture and modified files

- `app.py`: retained Streamlit entry point, shared article preview and export controls.
- `content/offers.json`: reusable product/category, title/H1, evergreen slug,
  description, offer/percentage, invitation ID/URL, eligibility, status, sources,
  publication/verification dates, FAQs, related guides and disclosure.
- `site_builder.py`: validates content and origins; builds escaped HTML, sitemap,
  robots.txt, optional host headers and a generated-file manifest.
- `templates/article.html`, `templates/page.html`: semantic content, navigation,
  metadata, canonical/OG URLs and Article JSON-LD. No executable JavaScript.
- `assets/styles.css`: white editorial layout, 740px maximum article content width,
  system fonts, keyboard focus outlines, mobile breakpoints and print styles.
- `serve.py`: loopback-only local preview, real 404s and directory slash redirects.
- `tests/test_site.py`: HTML, canonical, links, sitemap, content and schema tests.
- `verify_export.py`: pre-upload guard for real public origins, matching SEO URLs and crawler access.
- `requirements.txt`, `requirements-static.txt`, `.gitignore`: dependencies and generated files.

Output routes: `/`, `/offers/`, `/offers/zai-discount/`, `/about/`,
`/affiliate-disclosure/`, `/privacy-policy/`. No empty guides, comparisons or pricing
pages are generated. Related guides must point to real pages.

The inspected local Streamlit 1.67 HTTP response contained a generic title, empty
React root and JavaScript bundles, without the article. The static response
contains the entire guide and its metadata before any JavaScript executes.
No published Streamlit URL was supplied or changed.

## Production deployment

1. Choose the real public HTTPS origin; it has not been supplied yet.
2. If an old published page exists, preserve its URL or implement an HTTP 301/308
   redirect at that host before moving. Canonical tags do not replace redirects.
3. Build with the real origin, replacing the uppercase placeholder:

   ```sh
   python site_builder.py --base-url https://YOUR-REAL-DOMAIN
   ```

4. Run `.venv/bin/python verify_export.py dist`, then upload the contents of
   `dist/` to static hosting at the origin root. The check refuses preview builds
   and rejects local URLs in canonical, Open Graph, sitemap and structured data.
   Streamlit Community Cloud cannot serve this export as its public HTML page.
   The static host needs no Python or Streamlit server.
5. Enable directory index serving. Return HTTP 200 for existing pages, a permanent
   redirect for slashless directory URLs, and HTTP 404 for unknown routes using
   `404.html`. Disable SPA fallback rewrites that return 200 for everything.
   `_headers` works on some hosts; configure equivalent headers elsewhere.
6. Confirm canonical and OG URLs, sitemap, robots and response headers publicly.
   Ensure the host adds no noindex header, login requirement or crawler blocking.
   The wildcard robots allow rule includes Googlebot, Bingbot and OAI-SearchBot.
7. On first public publication, set `publication_date` to the actual launch date
   and set `publicly_published` to true. No creation or development notices appear publicly.
   Article `datePublished` is omitted until publication is confirmed. Rebuild after editing.
   Never advance `last_verified_date` without checking the sources again.
8. Review desktop/mobile layouts and JavaScript-disabled reading on the live host.
   Verify site ownership and submit sitemap.xml in Google Search Console and Bing
   Webmaster Tools. Indexing, rankings and AI search citations are not guaranteed.

Preview artifacts use localhost canonicals in the separate `preview/` directory
and must never be deployed. Production output remains in `dist/`; preview builds
cannot overwrite that directory. Production mode rejects localhost (including
subdomains, mixed case and trailing dots), loopback/private IPs and common placeholder
origins. Both output directories are generated and ignored.
Hosting status codes and external visitor access must be verified after deployment.

## Validation

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Twelve tests cover the full initial article HTML and all FAQs without JavaScript,
unique metadata, canonical/OG/schema origins, real HTTP 200/404 and permanent slash
redirects, internal links, sitemap, all three requested crawlers, semantic landmarks,
skip links, labelled sections and sponsored attributes on both discount links.
The existing Streamlit AppTest is checked separately for runtime exceptions.

JSON-LD is parsed and checked against article content; Google’s hosted Rich Results
Test was not run. No fake reviews, ratings, Product/Offer or FAQ rich results are
claimed. The article has exactly one H1, four H2s and eight FAQ H3s.

Browser access is unavailable and the native Chrome connection timed out, so
desktop/mobile visual QA is still pending.
Responsive CSS is implemented but not claimed as visually verified. Official source
links were fetched successfully; the web tool could not fetch the signed-in Z.ai
subscription destination. Manually check that checkout and account eligibility.
The static article is approximately 8KB HTML plus a local stylesheet. No measured
load-time or Core Web Vitals result is claimed; measure the deployed website.

## Editorial maintenance

Checked on November 24, 2026:

- https://docs.z.ai/devpack/credit-campaign-rules
- https://docs.z.ai/devpack/overview

The 72-hour payment requirement is stated in its original context: inviter reward
eligibility, not an invented buyer coupon expiry. Minimum US$0.50 payment,
first-order eligibility and exclusions are visible. Full checkout pricing was not
verified, so no pricing table is shown. The ID is not labelled as a tested coupon.

Keep disclosure visible and sponsored attributes on commercial links. Update the
privacy page if adding forms, analytics, advertising, cookies or other processing.
Add verified author/contact details when supplied; none are fabricated.
