"""Invoice Helper panel (used on Upload and Review pages)."""
import json

import streamlit as st

from core import helper, queries as q


def render(conn, iid, key_prefix="h"):
    inv = q.invoice(conn, iid) if iid else None
    top = st.columns([6, 1])
    top[0].markdown("#### ✨ Invoice Helper")
    mkey = f"{key_prefix}_min"
    if top[1].button("—" if not st.session_state.get(mkey) else "+", key=f"{key_prefix}_mbtn", help="Minimise / expand"):
        st.session_state[mkey] = not st.session_state.get(mkey)
        st.rerun()
    st.caption("Resets when you open another invoice · explains only, never approves or changes anything")
    if st.session_state.get(mkey):
        return
    if not inv or inv["run_state"] != "DONE":
        st.markdown("<div class='z-card z-muted'>Upload an invoice to get help with it.</div>" if not inv else
                    "<div class='z-card z-muted'>I'll be ready when processing finishes.</div>", unsafe_allow_html=True)
        return
    helper.ensure_started(conn, iid)
    box = st.container(height=470, border=True)
    with box:
        for m in q.chat(conn, iid)[-16:]:
            with st.chat_message(m["role"], avatar="🤖" if m["role"] == "assistant" else "🧑"):
                st.markdown(m["content"])
    items = helper.menu_items(conn, iid)
    choice = st.pills("Ask about this invoice", [v for _, v in items], key=f"{key_prefix}_pill_{iid}_{len(q.chat(conn, iid))}",
                      label_visibility="collapsed")
    if choice:
        k = next(k for k, v in items if v == choice)
        helper.ask(conn, iid, key=k)
        st.rerun()
    with st.form(f"{key_prefix}_form_{iid}", clear_on_submit=True, border=False):
        c = st.columns([6, 1])
        txt = c[0].text_input("Or type a question", placeholder="Or type a question about this invoice…", label_visibility="collapsed")
        if c[1].form_submit_button("➤", use_container_width=True) and txt.strip():
            helper.ask(conn, iid, text=txt.strip())
            st.rerun()
    if inv["email_draft"] and any(m["content"].startswith("**Recommended") or "email draft is ready" in m["content"] for m in q.chat(conn, iid)[-2:]):
        e = json.loads(inv["email_draft"])
        with st.expander("📧 Vendor email draft (copy - nothing is sent)", expanded=True):
            st.caption(f"To: {e['to']} · Subject: {e['subject']}")
            st.code(e["body"], language=None, wrap_lines=True)
