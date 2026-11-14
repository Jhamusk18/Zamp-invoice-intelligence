"""Zamp AP Assistant - Streamlit entry point.   Run:  streamlit run app/streamlit_app.py"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

st.set_page_config(page_title="Zamp AP Assistant", page_icon="🟪", layout="wide", initial_sidebar_state="expanded")

from app import ui  # noqa: E402
from core import seed  # noqa: E402

ui.inject_css()
ui.conn()

V = Path(__file__).parent / "views"
home = st.Page(V / "home.py", title="Welcome", icon=":material/home:", default=True)
upload = st.Page(V / "upload.py", title="Upload", icon=":material/upload_file:", url_path="upload")
history = st.Page(V / "invoices.py", title="History", icon=":material/history:", url_path="history")
profile = st.Page(V / "profile.py", title="Profile", icon=":material/person:", url_path="profile")
review = st.Page(V / "review.py", title="Invoice Review", icon=":material/fact_check:", url_path="review", visibility="hidden")

st.session_state.pages = {"home": home, "upload": upload, "invoices": history, "history": history, "profile": profile, "review": review}

nav = st.navigation([home, upload, history, profile, review])

with st.sidebar:
    st.markdown("### 🟪 Zamp AP Assistant\n<span class='z-muted'>Accounts Payable Automation</span>", unsafe_allow_html=True)


@st.dialog("Reset demo data?")
def confirm_reset():
    st.write("This deletes every uploaded invoice, decision, audit entry, chat and saved rule change, and rebuilds the "
             "sample company and its invoice history. Cached AI answers are deleted too.")
    c1, c2 = st.columns(2)
    if c1.button("Yes, reset", type="primary", use_container_width=True):
        try:
            st.session_state.conn.close()
        except Exception:
            pass
        with st.spinner("Rebuilding sample data…"):
            seed.reset()
        for k in list(st.session_state.keys()):
            if k != "pages":
                del st.session_state[k]
        st.toast("Demo data reset.", icon="✅")
        st.rerun()
    if c2.button("Cancel", use_container_width=True):
        st.rerun()


with st.sidebar:
    st.divider()
    if st.button("Reset Demo Data", icon=":material/restart_alt:", use_container_width=True):
        confirm_reset()
    ui.demo_note()

nav.run()
