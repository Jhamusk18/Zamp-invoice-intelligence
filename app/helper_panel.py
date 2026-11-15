"""'Chat with Zamp Assistant' widget (Upload page side panel, Review page popover).
Explains stored results only - never approves, rejects or changes anything."""
import html
import re

import streamlit as st

from core import helper, queries as q

BOT = ("<svg viewBox='0 0 24 24' width='22' height='22' fill='none' stroke='#fff' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'>"
       "<rect x='4' y='7' width='16' height='12' rx='4'/><path d='M12 3v4'/><circle cx='9' cy='13' r='1.2' fill='#fff'/>"
       "<circle cx='15' cy='13' r='1.2' fill='#fff'/><path d='M9.5 16.5h5'/></svg>")
TEASER_QS = ["Why is it held?", "What should I do?", "Compare with order"]


def _html(md):
    """Tiny markdown -> HTML for chat bubbles (bold, line breaks)."""
    t = html.escape(md)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    return t.replace("\n", "<br>")


def _header(sub):
    st.markdown(f"""<div class='zc-head'><div class='zc-av'>{BOT}<i></i></div>
      <div><div class='zc-pre'>Chat with</div><div class='zc-name'>Zamp Assistant</div><div class='zc-sub'>{sub}</div></div></div>""",
                unsafe_allow_html=True)


def _teaser(msg):
    with st.container(key="ask_idle"):
        _header("Ask me about your invoice")
        pills = "".join(f"<span class='zc-pill off'>{t}</span>" for t in TEASER_QS)
        st.markdown(f"<div class='zc-body'><div class='zc-msg bot'>{msg}</div><div class='zc-pills'>{pills}</div></div>",
                    unsafe_allow_html=True)


def render(conn, iid, key_prefix="h", height=380):
    inv = q.invoice(conn, iid) if iid else None
    if not inv:
        _teaser("Hi! 👋 Upload an invoice and I'll explain the result here.")
        return
    if inv["run_state"] in ("QUEUED", "RUNNING"):
        _teaser("Checking your invoice… I'll be ready in a moment ⏳")
        return
    if inv["run_state"] == "ERROR":
        _teaser("I couldn't read this invoice. Please press Retry first.")
        return

    first_time = not st.session_state.get(f"glowed_{key_prefix}_{iid}")
    st.session_state[f"glowed_{key_prefix}_{iid}"] = True
    helper.ensure_started(conn, iid)
    with st.container(key="ask_glow" if first_time else "ask_calm"):
        _header("Ask me about this invoice")
        msgs = q.chat(conn, iid)
        with st.container(height=height, border=False, autoscroll=True, key=f"zcmsgs_{key_prefix}"):
            st.markdown("".join(f"<div class='zc-msg {'bot' if m['role'] == 'assistant' else 'me'}'>{_html(m['content'])}</div>"
                                for m in msgs[-14:]), unsafe_allow_html=True)
        with st.container(horizontal=True, key=f"zcpills_{key_prefix}", gap="small"):
            for k, label in helper.menu_items(conn, iid):
                if st.button(label, key=f"{key_prefix}_q_{k}_{iid}"):
                    helper.ask(conn, iid, key=k)
                    st.rerun()
            if len(msgs) > 1 and st.button("↺ Start over", key=f"{key_prefix}_start_{iid}", type="tertiary"):
                helper.ask(conn, iid, key="start")
                st.rerun()
        with st.form(f"{key_prefix}_form_{iid}", clear_on_submit=True, border=False):
            with st.container(horizontal=True, key=f"zcinput_{key_prefix}", vertical_alignment="center"):
                txt = st.text_input("Your question", placeholder="Enter your message…", label_visibility="collapsed")
                if st.form_submit_button("➤", type="primary") and txt.strip():
                    helper.ask(conn, iid, text=txt.strip())
                    st.rerun()
