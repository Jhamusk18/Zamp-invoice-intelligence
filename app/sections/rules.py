from datetime import datetime

import pandas as pd
import streamlit as st

from app import ui
from core import policy, whatif



def render():
    conn = ui.conn()
    ver, cur = policy.active(conn)
    hist = policy.history(conn)
    st.caption("Set the key values and validation rules used to check invoices.")
    st.markdown(f"<span class='z-pill APPROVED'><span class='dot'></span>Saved · policy v{ver}</span> <span class='z-muted'>last changed "
                f"{datetime.fromtimestamp(hist[0]['created_at']):%d %b %Y %H:%M} by {hist[0]['created_by']}</span>", unsafe_allow_html=True)
    st.write("")

    if "draft_policy" not in st.session_state or st.session_state.get("draft_base") != ver:
        st.session_state.draft_policy = dict(cur, rules=dict(cur["rules"]))
        st.session_state.draft_base = ver
    d = st.session_state.draft_policy

    left, right = st.columns([1.6, 1], gap="large")
    with left:
        with st.container(border=True):
            st.markdown("#### Key Settings")
            st.caption("Core policy values for automatic validation and approval. Amounts are compared before tax.")
            c = st.columns(3)
            d["tolerance_pct"] = c[0].number_input("Price tolerance (%)", 0.0, 20.0, float(d["tolerance_pct"]), 0.5,
                                                   help="A PO line priced within this % passes.")
            d["tolerance_cap"] = c[1].number_input("…but at most (₹ per line)", 0.0, 1e7, float(d["tolerance_cap"]), 1000.0,
                                                   help="So 2% of a very large line can't slip through.")
            d["reject_variance_pct"] = c[2].number_input("Block above (%)", 0.0, 50.0, float(d["reject_variance_pct"]), 0.5,
                                                         help="Prices more than this % above the PO are Rejected; between tolerance and this, Needs Attention.")
            c = st.columns(3)
            d["auto_approve_limit"] = c[0].number_input("Auto-approve limit (₹)", 0.0, 1e9, float(d["auto_approve_limit"]), 10000.0,
                                                        help="Invoices above this always need a person, even if every check passes.")
            d["qty_tolerance_pct"] = c[1].number_input("Quantity tolerance (%)", 0.0, 20.0, float(d["qty_tolerance_pct"]), 1.0,
                                                       help="How much billed quantity may exceed received quantity.")
            d["vendor_match"] = c[2].selectbox("Vendor name matching", ["strict", "medium", "flexible"],
                                               index=["strict", "medium", "flexible"].index(d["vendor_match"]),
                                               format_func=lambda x: {"strict": "Strict", "medium": "Medium (recommended)", "flexible": "Flexible"}[x],
                                               help="Flexible never skips the GSTIN or bank checks.")
        with st.container(border=True):
            st.markdown("#### Validation Rules")
            st.caption("Choose which checks run. 🔒 = required fraud controls, can't be turned off.")
            for key, (name, desc) in policy.RULE_INFO.items():
                r = st.columns([0.6, 6, 1.4])
                locked = key in policy.LOCKED_RULES
                r[1].markdown(f"**{name}**{' 🔒' if locked else ''}  \n<span class='z-muted'>{desc}</span>", unsafe_allow_html=True)
                d["rules"][key] = r[2].toggle("On", value=True if locked else d["rules"][key], disabled=locked, key=f"rule_{key}")

    with right:
        with st.container(border=True):
            st.markdown("#### See what would change")
            st.caption("Re-runs past invoices with these settings so you can see the impact before you save. "
                       "Simulation only - no invoice status changes.")
            changed = {k for k in d if d[k] != cur[k]}
            if st.button("Run Impact Analysis", type="primary", use_container_width=True, icon=":material/query_stats:"):
                try:
                    st.session_state.impact = (whatif.simulate(conn, policy.normalise(d)), dict(d, rules=dict(d["rules"])))
                except ValueError as e:
                    st.error(str(e))
            imp = st.session_state.get("impact")
            if imp:
                res, snap = imp
                if snap != d:
                    st.caption("⚠️ Settings changed since this analysis - run it again.")
                if not res:
                    st.success("No invoice would change status.")
                else:
                    up = sum(1 for r in res if r["direction"] < 0)
                    down = len(res) - up
                    st.markdown(f"**{len(res)} invoice(s) would change**  \n⬆️ {up} would become less strict · ⬇️ {down} would become stricter")
                    st.dataframe(pd.DataFrame(res).drop(columns=["id", "direction"]), hide_index=True, use_container_width=True,
                                 column_config={"Amount": st.column_config.NumberColumn(format="₹ %,.0f")})
                st.caption("Simplification: each invoice is re-checked against the invoices processed before it, with today's PO money state.")
        with st.container(border=True):
            st.markdown("#### Policy history")
            st.dataframe([{"Version": h["version"], "When": datetime.fromtimestamp(h["created_at"]).strftime("%d %b %H:%M"),
                           "By": h["created_by"], "Note": h["note"]} for h in hist], hide_index=True, use_container_width=True)
            st.caption("Each decision keeps the version it was made under. Saving never changes past decisions.")

    st.write("")
    b = st.columns([4, 1.2, 1.2])
    note = b[0].text_input("Change note", placeholder="Why are you changing the rules? (recorded in the audit trail)", label_visibility="collapsed")


    @st.dialog("Reset to defaults?")
    def confirm_default():
        st.write("This saves a new policy version with the default values. Past decisions keep the version they were made under.")
        if st.button("Yes, reset to defaults", type="primary"):
            policy.save(conn, policy.DEFAULT_POLICY, note="Reset to default")
            st.session_state.pop("draft_policy", None)
            st.session_state.pop("impact", None)
            st.rerun()


    if b[1].button("Reset to Default", use_container_width=True):
        confirm_default()
    if b[2].button("Save Changes", type="primary", use_container_width=True, disabled=not changed):
        try:
            v = policy.save(conn, d, note=note.strip() or "Updated from Approval Rules page")
            st.session_state.pop("impact", None)
            st.toast(f"Saved as policy v{v}. New invoices use it from now on.", icon="✅")
            st.rerun()
        except ValueError as e:
            st.error(str(e))
    if not changed:
        st.caption("No unsaved changes.")

