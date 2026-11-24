"""A lightweight Z.ai discount and coupon guide. No network calls on page render."""

import streamlit as st
import sys

from site_builder import ROOT, build_site, load_offers, render_article

offer = load_offers()[0]
st.set_page_config(page_title=offer["page_title"], page_icon="✳", layout="centered", initial_sidebar_state="collapsed")

st.html("""
<style>
  /* Leave room for Streamlit's fixed toolbar above the first content row. */
  .stMainBlockContainer {max-width: 790px; padding-top: 5rem; padding-bottom: 3rem;}
  h1 {font-size: clamp(1.85rem, 4.5vw, 2.5rem) !important;
      line-height: 1.3 !important;}
  h2 {letter-spacing: -.025em;}
  p, li {line-height: 1.75;}
  a {text-underline-offset: 4px;}
  .masthead {display: flex; justify-content: space-between; gap: 1rem;
      align-items: center; border-bottom: 1px solid #dce2e8; padding-bottom: 1.1rem;
      margin-bottom: .35rem; line-height: 1.5; font-size: .9rem; color: #536170;}
  .masthead strong {color: #172c3e; font-size: 1rem;}
  @media (max-width: 600px) {
    .stMainBlockContainer {padding-top: 4.5rem;}
    .masthead {align-items: flex-start; flex-direction: column; gap: .3rem;}
  }
</style>
<div class="masthead"><strong>✳ Software Savings Notes</strong>
<span>Independent savings guide</span></div>
""")

st.html("<style>" + (ROOT / "assets/styles.css").read_text() + "</style>")
st.html(render_article(offer, internal_links=False))

if "--manage" in sys.argv:
    with st.sidebar:
        st.header("Static website export")
        st.caption("Edit content/offers.json, then export. This Streamlit page is a management preview; public SEO metadata belongs to the static HTML export.")
        origin = st.text_input("Public HTTPS origin", placeholder="https://your-domain.com")
        if st.button("Build static website"):
            try:
                output = build_site(origin)
            except ValueError as error:
                st.error(str(error))
            else:
                st.success(f"Exported to {output}. Deploy that directory to your static host.")
