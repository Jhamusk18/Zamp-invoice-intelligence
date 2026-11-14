"""Zamp AP Assistant - Streamlit entry point.   Run:  streamlit run app/streamlit_app.py"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

st.set_page_config(page_title="Zamp AP Assistant", page_icon=str(Path(__file__).parent / "static" / "logo_icon.svg"),
                   layout="wide", initial_sidebar_state="collapsed")

from app import ui  # noqa: E402

ui.inject_css()
ui.conn()
st.logo(str(ui.STATIC / "logo.svg"), size="large")

V = Path(__file__).parent / "views"
home = st.Page(V / "home.py", title="Welcome", icon=":material/home:", default=True)
upload = st.Page(V / "upload.py", title="Upload", icon=":material/upload_file:", url_path="upload")
history = st.Page(V / "invoices.py", title="History", icon=":material/history:", url_path="history")
profile = st.Page(V / "profile.py", title="Profile", icon=":material/person:", url_path="profile")
review = st.Page(V / "review.py", title="Invoice Review", icon=":material/fact_check:", url_path="review", visibility="hidden")

st.session_state.pages = {"home": home, "upload": upload, "invoices": history, "history": history, "profile": profile, "review": review}
st.navigation([home, upload, history, profile, review], position="top").run()
