import time
from datetime import datetime

import streamlit as st

from app import helper_panel, ui
from core import helper, llm, pipeline, queries as q
from core.document import TechnicalError

conn = ui.conn()
ui.header("Upload & Verify Invoice", "Drop a vendor invoice. Zamp reads it, checks it against your vendors, purchase orders and rules, and tells you what to do.")


def open_review(iid):
    st.switch_page(st.session_state.pages["review"], query_params={"id": str(iid)})


def upload_another():
    st.session_state.pop("current_id", None)
    st.session_state.pop("seen_id", None)
    st.session_state.upl_n = st.session_state.get("upl_n", 0) + 1


iid = st.session_state.get("current_id")
inv = q.invoice(conn, iid) if iid else None
running = bool(inv and inv["run_state"] in ("QUEUED", "RUNNING"))
finished = bool(inv and inv["run_state"] in ("DONE", "ERROR"))

left, right = st.columns([1.55, 1], gap="large")

with left:
    if not llm.available():
        st.warning("AI reading isn't set up on this server yet: add **GEMINI_API_KEY** (and optionally **GROQ_API_KEY** as a backup) in the app's **Settings → Secrets**. Until then, new uploads stop at **Text Extracted**.", icon="🔑")

    # ---- "already processed" -> neutral banner with a way to the earlier result
    if st.session_state.get("seen_id") == iid and inv:
        with st.container(key="card_seen"):
            c = st.columns([4, 1.4])
            c[0].markdown(f"ℹ️ **This exact file was checked before** ({datetime.fromtimestamp(inv['uploaded_at']):%d %b %Y, %H:%M}). "
                          "Showing that result instead of processing it twice.")
            if c[1].button("Open earlier result", key="seen_open", use_container_width=True):
                open_review(iid)

    # ---- before upload (or after "Upload another"): one obvious action
    if not inv:
        f = st.file_uploader("Drop your invoice PDF here, or click to browse", type=["pdf"], key=f"uploader_{st.session_state.get('upl_n', 0)}",
                             help="PDF invoices, freight bills or scanned documents - up to 10 MB.")
        st.markdown("<div class='z-muted' style='text-align:center;margin-top:-4px'>PDF · text or scanned · up to 10 MB</div>", unsafe_allow_html=True)
        if f is not None:
            c = st.columns([3, 1.3])
            c[0].markdown(f"<div style='padding-top:8px'>📄 <b>{f.name}</b> <span class='z-muted'>· {f.size / 1024:.0f} KB</span></div>", unsafe_allow_html=True)
            if c[1].button("Check invoice", type="primary", use_container_width=True, icon=":material/arrow_forward:"):
                try:
                    new_id, seen = pipeline.submit(conn, f.getvalue(), f.name)
                    st.session_state.current_id = new_id
                    st.session_state.seen_id = new_id if seen else None
                    st.rerun()
                except TechnicalError as e:
                    st.error(f"Couldn't accept this file: {e}", icon="🚫")

    # ---- after the run: the result first, big
    if finished:
        ui.verdict(inv, helper.next_step(conn, iid))
        b = st.columns([1.4, 1.2, 2])
        if inv["run_state"] == "DONE":
            if b[0].button("Open full review", type="primary", icon=":material/fact_check:", use_container_width=True):
                open_review(iid)
        else:
            if b[0].button("Retry", type="primary", icon=":material/refresh:", use_container_width=True):
                pipeline.retry(conn, iid)
                st.rerun()
        if b[1].button("Upload another", icon=":material/upload_file:", use_container_width=True):
            upload_another()
            st.rerun()
        st.write("")

    # ---- the live steps
    @st.fragment(run_every=0.5 if running else None)
    def steps():
        cur = q.invoice(conn, iid) if iid else None
        if not cur:
            return
        stg = q.stages(conn, iid)
        with st.container(key="card_steps"):
            t0 = min((s["started_at"] for s in stg if s["started_at"]), default=None)
            t1 = max((s["ended_at"] for s in stg if s["ended_at"]), default=None)
            h = st.columns([3, 2])
            h[0].markdown(f"**Processing steps** <span class='z-muted'>· {cur['filename']}</span>", unsafe_allow_html=True)
            if cur["run_state"] == "DONE":
                h[1].markdown(f"<div style='text-align:right' class='z-muted'>✅ finished in {ui.secs(t1 - t0) if t0 and t1 else '—'}</div>", unsafe_allow_html=True)
            elif cur["run_state"] == "ERROR":
                h[1].markdown("<div style='text-align:right;color:#B91C1C'>stopped - technical error</div>", unsafe_allow_html=True)
            else:
                h[1].markdown(f"<div style='text-align:right;color:#2F5BEA'>⏳ running · {ui.secs(time.time() - t0) if t0 else 'queued'}</div>", unsafe_allow_html=True)
            ui.stepper(stg, time.time())
            if cur["run_state"] != "QUEUED":
                with st.expander("Full details of each step", expanded=cur["run_state"] == "ERROR"):
                    for s in stg:
                        st.markdown(f"**{s['stage']}** · {s['finding'] or s['status'].lower()}")
        if running and cur["run_state"] in ("DONE", "ERROR"):
            st.rerun(scope="app")  # finished while we were watching: redraw once so the result card + helper appear

    if inv:
        steps()

with right:
    helper_panel.render(conn, iid, "up")
