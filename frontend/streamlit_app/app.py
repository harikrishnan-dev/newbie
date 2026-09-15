"""Streamlit chat frontend for the Retrieval Agent.

Lets the user pick a role in the sidebar (employee / CEO / HR) and chat
in the main panel. Messages are sent to the backend API (`frontend/backend`),
which forwards them to the retrieval agent graph.
"""

import os

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

ROLE_INTRO = {
    "Employee": (
        "You're chatting as an **Employee**. Ask about company policies, "
        "benefits, onboarding, or anything else in the handbook."
    ),
    "CEO": (
        "You're chatting as the **CEO**. Ask about company-wide strategy, "
        "policies, or org-level information."
    ),
    "HR": (
        "You're chatting as **HR**. Ask about policies, compliance, or "
        "employee-related processes."
    ),
}

st.set_page_config(page_title="Retrieval Agent", page_icon="💬")

with st.sidebar:
    st.header("Role")
    role = st.radio("Select your role", list(ROLE_INTRO.keys()))
    st.markdown(ROLE_INTRO[role])

    if st.button("Clear chat"):
        st.session_state.pop("messages", None)

st.title("Retrieval Agent")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_role" not in st.session_state:
    st.session_state.last_role = role
elif st.session_state.last_role != role:
    st.session_state.last_role = role
    st.session_state.messages = []

def render_citations(citations: list[str]) -> None:
    if citations:
        st.caption("Sources: " + ", ".join(citations))


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        render_citations(message.get("citations", []))

if prompt := st.chat_input("Ask a question..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        citations = []
        try:
            response = requests.post(
                f"{BACKEND_URL}/chat",
                json={"role": role, "message": prompt},
                timeout=30,
            )
            response.raise_for_status()
            body = response.json()
            answer = body["answer"]
            citations = body.get("citations", [])
        except requests.RequestException as exc:
            answer = f"Could not reach the backend API: {exc}"
        st.markdown(answer)
        render_citations(citations)

    st.session_state.messages.append({"role": "assistant", "content": answer, "citations": citations})
