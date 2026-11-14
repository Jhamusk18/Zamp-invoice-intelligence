"""'Ask about this invoice' panel (Upload page side panel, Review page popover).
Explains stored results only - never approves, rejects or changes anything."""
import json

import streamlit as st

from core import helper, queries as q

TEASER_QS = ["Why was this held?", "What should I do next?", "Compare with our order"]


def _teaser(msg):
    with st.container(key="ask_idle"):
        st.markdown("#### 💬 Ask about this invoice")
        st.markdown(f"<div class='z-muted' style='margin-bottom:8px'>{msg}</div>", unsafe_allow_html=True)
        for t in TEASER_QS:
            st.markdown(f"<div class='z-teaser-q'>{t}</div>", unsafe_allow_html=True)


def render(conn, iid, key_prefix="h", height=380):
    inv = q.invoice(conn, iid) if iid else None
    if not inv:
        _teaser("After your invoice is checked, ask about it here.")
        return
    if inv["run_state"] in ("QUEUED", "RUNNING"):
        _teaser("Checking your invoice… questions will open here as soon as it's done.")
        return
    if inv["run_state"] == "ERROR":
        _teaser("This invoice couldn't be processed, so there's nothing to explain yet. Retry it first.")
        return

    first_time = not st.session_state.get(f"glowed_{key_prefix}_{iid}")
    st.session_state[f"glowed_{key_prefix}_{iid}"] = True
    helper.ensure_started(conn, iid)
    with st.container(key="ask_glow" if first_time else "ask_calm"):
        st.markdown("#### 💬 Ask about this invoice")
        st.markdown("<div class='z-muted' style='margin-top:-6px;margin-bottom:6px'>Answers come from this invoice's stored checks. "
                    "It explains only - it never approves or changes anything.</div>", unsafe_allow_html=True)
        msgs = q.chat(conn, iid)
        box = st.container(height=height, border=False, autoscroll=True)
        with box:
            for m in msgs[-14:]:
                with st.chat_message(m["role"], avatar="🔷" if m["role"] == "assistant" else "🧑"):
                    st.markdown(m["content"])
        items = helper.menu_items(conn, iid)
        cols = st.columns(2)
        for n, (k, label) in enumerate(items):
            if cols[n % 2].button(label, key=f"{key_prefix}_q_{k}_{iid}", use_container_width=True):
                helper.ask(conn, iid, key=k)
                st.rerun()
        with st.form(f"{key_prefix}_form_{iid}", clear_on_submit=True, border=False):
            c = st.columns([6, 1.2])
            txt = c[0].text_input("Your question", placeholder="Or type a question about this invoice…", label_visibility="collapsed")
            if c[1].form_submit_button("Ask", use_container_width=True) and txt.strip():
                helper.ask(conn, iid, text=txt.strip())
                st.rerun()
        if len(msgs) > 1 and st.button("↺ Start over", key=f"{key_prefix}_start_{iid}", type="tertiary"):
            helper.ask(conn, iid, key="start")
            st.rerun()
        if inv["email_draft"] and msgs and msgs[-1]["role"] == "assistant" and "email draft is ready" in msgs[-1]["content"]:
            e = json.loads(inv["email_draft"])
            with st.expander("📧 Vendor email draft (copy - nothing is sent)", expanded=True):
                st.caption(f"To: {e['to']} · Subject: {e['subject']}")
                st.code(e["body"], language=None, wrap_lines=True)
