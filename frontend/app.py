"""
Streamlit frontend — internal IT chatbot UI.
Calls the FastAPI backend at /chat and renders answers with citations.
"""
from __future__ import annotations

import os
import uuid

import httpx
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
USER_ID = str(uuid.uuid4())   # session-scoped; swap for SSO identity in production

st.set_page_config(
    page_title="IT Knowledge Base",
    page_icon="💻",
    layout="centered",
)

st.title("IT Knowledge Base")
st.caption("Ask any IT question — password resets, VPN, software access, policies, and more.")

# -----------------------------------------------------------------------
# Session state
# -----------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []


# -----------------------------------------------------------------------
# Chat history display
# -----------------------------------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("citations"):
            with st.expander("Sources", expanded=False):
                for cit in msg["citations"]:
                    url = cit.get("source_url", "")
                    title = cit.get("document_title", "Unknown")
                    system = cit.get("source_system", "")
                    updated = cit.get("last_updated", "")
                    line = f"**[{cit['index']}] {title}**"
                    if url:
                        line += f" — [{url}]({url})"
                    if system:
                        line += f"  \n*{system}*"
                    if updated:
                        line += f", last updated: {updated}"
                    st.markdown(line)
        if msg.get("disclaimer"):
            st.warning(msg["disclaimer"])
        if msg.get("ticket_draft"):
            st.error("Low confidence — a support ticket draft has been prepared.")
            with st.expander("Review ticket draft before submitting"):
                draft = msg["ticket_draft"]
                st.markdown(f"**Subject:** {draft.get('subject', '')}")
                st.text_area(
                    "Description",
                    value=draft.get("description", ""),
                    height=200,
                    key=f"ticket_{msg.get('ts', '')}",
                    disabled=True,
                )
                st.caption(
                    "Copy this draft into your ticketing system. "
                    "The bot does not submit tickets automatically."
                )


# -----------------------------------------------------------------------
# Query input
# -----------------------------------------------------------------------
if prompt := st.chat_input("Ask an IT question..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Searching knowledge base..."):
            try:
                resp = httpx.post(
                    f"{API_BASE}/chat",
                    json={"query": prompt, "user_id": USER_ID},
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()

                answer = data.get("answer", "")
                citations = data.get("citations", [])
                disclaimer = data.get("disclaimer", "")
                ticket_draft = data.get("ticket_draft")
                ts = data.get("timestamp", "")

                st.markdown(answer)

                if citations:
                    with st.expander("Sources", expanded=True):
                        for cit in citations:
                            url = cit.get("source_url", "")
                            title = cit.get("document_title", "Unknown")
                            system = cit.get("source_system", "")
                            updated = cit.get("last_updated", "")
                            line = f"**[{cit['index']}] {title}**"
                            if url:
                                line += f" — [{url}]({url})"
                            if system:
                                line += f"  \n*{system}*"
                            if updated:
                                line += f", last updated: {updated}"
                            st.markdown(line)

                if disclaimer:
                    st.warning(disclaimer)

                if ticket_draft:
                    st.error("I wasn't able to find a confident answer — here's a support ticket draft you can submit:")
                    with st.expander("Review ticket draft before submitting"):
                        st.markdown(f"**Subject:** {ticket_draft.get('subject', '')}")
                        st.text_area(
                            "Description",
                            value=ticket_draft.get("description", ""),
                            height=200,
                            key=f"ticket_new_{ts}",
                            disabled=True,
                        )
                        st.caption(
                            "Copy this draft into your ticketing system. "
                            "The bot does not submit tickets automatically."
                        )

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "citations": citations,
                    "disclaimer": disclaimer,
                    "ticket_draft": ticket_draft,
                    "ts": ts,
                })

            except httpx.HTTPError as exc:
                st.error(f"Backend error: {exc}")
