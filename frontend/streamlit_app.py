import os

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
CHAT_ENDPOINT = f"{BACKEND_URL}/api/chat"
REQUEST_TIMEOUT = 60

RABO_ORANGE = "#FF6200"
RABO_BLUE = "#000066"

SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "You are Rabobank's virtual customer-support assistant. Rabobank is a Dutch "
        "cooperative bank. Help customers with questions about payments, debit and credit "
        "cards, accounts, mortgages, online and mobile banking, and reporting fraud. "
        "Answer concisely and professionally. For anything that needs access to a "
        "customer's account or personal data, advise them to log in to the Rabo App or "
        "contact Rabobank directly, and never ask for passwords, PINs, or full card numbers."
    ),
}

SUGGESTED_QUESTIONS = [
    "How do I report fraud to Rabobank?",
    "What are the ways to contact Rabobank?",
    "How do I block or replace my debit card?",
    "How do I arrange a mortgage with Rabobank?",
]

st.set_page_config(page_title="Rabobank Assistant", layout="centered")

st.markdown(
    f"""
    <div style="background:{RABO_ORANGE};padding:16px 20px;border-radius:10px;
                margin-bottom:6px;display:flex;align-items:center;gap:12px;">
        <div style="background:white;color:{RABO_BLUE};font-weight:800;font-size:20px;
                    border-radius:6px;padding:4px 10px;">R</div>
        <div>
            <div style="color:white;font-size:22px;font-weight:700;line-height:1.1;">Rabobank</div>
            <div style="color:white;font-size:14px;opacity:0.95;">Virtual Customer Assistant</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption("Ask about payments, cards, mortgages, online banking, or reporting fraud.")

if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.subheader("Settings")
    temperature = st.slider("Response creativity", 0.0, 1.0, 0.3, 0.1)
    use_search = st.checkbox(
        "Search rabobank.nl",
        value=True,
        help="Ground answers in live rabobank.nl pages and cite the source links.",
    )
    if st.button("Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()


def request_reply(messages, creativity, search):
    response = None
    try:
        response = requests.post(
            CHAT_ENDPOINT,
            json={"messages": messages, "temperature": creativity, "use_search": search},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return data["reply"], data.get("sources", [])
    except requests.HTTPError:
        detail = "Unknown error"
        if response is not None and response.content:
            try:
                detail = response.json().get("detail", detail)
            except ValueError:
                pass
        return f"Sorry, something went wrong on the server: {detail}", []
    except requests.RequestException as exc:
        return f"Could not reach the assistant service at {BACKEND_URL}: {exc}", []


def render_sources(sources):
    if not sources:
        return
    links = "\n".join(f"- [{source['title']}]({source['url']})" for source in sources)
    st.markdown(f"**Sources from Rabobank:**\n{links}")


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            render_sources(message.get("sources"))

pending_question = None
if not st.session_state.messages:
    st.markdown("**Frequently asked questions**")
    columns = st.columns(2)
    for index, question in enumerate(SUGGESTED_QUESTIONS):
        if columns[index % 2].button(question, use_container_width=True, key=f"suggested_{index}"):
            pending_question = question

typed_question = st.chat_input("Type your question...")
user_question = typed_question or pending_question

if user_question:
    st.session_state.messages.append({"role": "user", "content": user_question})
    with st.spinner("Searching Rabobank..." if use_search else "Thinking..."):
        reply, sources = request_reply(
            [SYSTEM_PROMPT] + st.session_state.messages, temperature, use_search
        )
    st.session_state.messages.append(
        {"role": "assistant", "content": reply, "sources": sources}
    )
    st.rerun()
