import time
from datetime import datetime

import streamlit as st

from app import helper_panel, ui
from core import llm, pipeline, queries as q, seed
from core.document import TechnicalError

conn = ui.conn()
ui.header("Upload & Verify Invoice", "Upload a vendor invoice and let Zamp validate it against your company's data and policies.")

left, right = st.columns([1.35, 1], gap="large")

with left:
    if not llm.available():
        st.warning("AI extraction isn't configured yet (no GEMINI_API_KEY). Uploads will stop at **Text Extracted** with a clear "
                   "error. History and Review still work with the sample data.", icon="🔑")
    with st.container(border=True):
        f = st.file_uploader("Drop your invoice here, or click to upload a PDF", type=["pdf"],
                             help="Supports PDF (including scans), up to 10 MB.", key=f"uploader_{st.session_state.get('upl_n', 0)}")
        st.caption("Accepts PDF invoices, freight bills or scanned documents (up to 10 MB).")
        if f is not None:
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"📄 **{f.name}** · {f.size / 1024:.0f} KB")
            if c2.button("Verify invoice", type="primary", use_container_width=True, icon=":material/arrow_forward:"):
                try:
                    iid, seen = pipeline.submit(conn, f.getvalue(), f.name)
                    st.session_state.current_id = iid
                    st.session_state.seen_msg = seen
                    st.session_state.upl_n = st.session_state.get("upl_n", 0) + 1  # clear the picker
                    st.rerun()
                except TechnicalError as e:
                    st.error(f"Couldn't accept this file: {e}", icon="🚫")

    # ---- Try a sample invoice (the prepared demo set: 1 happy path + edge cases)
    samples = [s for s in seed.specs() if s["role"] == "demo"]
    st.markdown("<div class='z-muted' style='margin:6px 0 4px'>Try a sample invoice</div>", unsafe_allow_html=True)
    cols = st.columns(4)
    for n, s in enumerate(samples):
        if cols[n % 4].button(s.get("title", s["key"]), key=f"sample_{s['key']}", help=s.get("story"), use_container_width=True,
                              type="secondary"):
            try:
                iid, seen = pipeline.submit(conn, (seed.PDF_DIR / f"{s['key']}.pdf").read_bytes(), f"{s['key']}.pdf")
                st.session_state.current_id, st.session_state.seen_msg = iid, seen
                st.rerun()
            except TechnicalError as e:
                st.error(str(e))
    st.caption("Hover a sample to see what it tests. Each runs through the real pipeline, exactly like an upload.")

    iid = st.session_state.get("current_id")
    if iid and st.session_state.pop("seen_msg", False):
        inv0 = q.invoice(conn, iid)
        st.info(f"This exact file was already processed ({datetime.fromtimestamp(inv0['uploaded_at']):%d %b %Y, %H:%M}). "
                "Showing the earlier result instead of processing it twice.", icon="🔁")

    inv = q.invoice(conn, iid) if iid else None
    running = bool(inv and inv["run_state"] in ("QUEUED", "RUNNING"))

    @st.fragment(run_every=0.5 if running else None)
    def progress():
        cur = q.invoice(conn, iid) if iid else None
        with st.container(border=True):
            h1, h2 = st.columns([3, 2])
            h1.markdown("### Processing Overview")
            if not cur:
                h1.caption("Track the validation steps for your invoice.")
                ui.tracker([{"stage_no": i + 1, "stage": s, "status": "PENDING", "started_at": None, "ended_at": None}
                            for i, s in enumerate(pipeline.STAGES)], time.time())
                st.markdown("<div class='z-muted'>Nothing processed yet in this session. Upload an invoice above, or pick one in "
                            "a <b>sample</b> below the upload box.</div>", unsafe_allow_html=True)
                return
            stg = q.stages(conn, iid)
            t0 = min((s["started_at"] for s in stg if s["started_at"]), default=None)
            t1 = max((s["ended_at"] for s in stg if s["ended_at"]), default=None)
            if cur["run_state"] == "DONE":
                h2.success(f"Completed in {t1 - t0:.1f} s" if t0 and t1 else "Completed", icon="✅")
            elif cur["run_state"] == "ERROR":
                h2.error("Stopped: technical error", icon="❌")
            else:
                h2.info(f"Running… {time.time() - t0:.1f} s" if t0 else "Queued…", icon="⏳")
            h1.caption(f"{cur['filename']}")
            ui.tracker(stg, time.time())
            with st.expander("What happened at each step", expanded=cur["run_state"] != "DONE"):
                for s in stg:
                    st.markdown(f"**{s['stage']}** · `{s['status'].lower()}` - {s['finding'] or '…'}")
            if cur["run_state"] in ("DONE", "ERROR"):
                ui.verdict(cur)
                b1, b2 = st.columns([1, 1])
                if cur["run_state"] == "DONE":
                    if b1.button("Review", type="primary", icon=":material/fact_check:", key="vd"):
                        st.switch_page(st.session_state.pages["review"], query_params={"id": str(iid)})
                else:
                    if b1.button("Retry processing", icon=":material/refresh:", key="retry"):
                        pipeline.retry(conn, iid)
                        st.rerun()
                if running:  # the run just finished while we were polling: redraw the whole page once (verdict + helper)
                    st.rerun(scope="app")

    progress()

with right:
    with st.container(border=True):
        helper_panel.render(conn, iid, "up")
