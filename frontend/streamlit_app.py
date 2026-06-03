import os

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
CHAT_ENDPOINT = f"{BACKEND_URL}/api/chat"
REQUEST_TIMEOUT = 60

SYSTEM_PROMPT = {
    "role": "system",
    "content": "You are a helpful, concise assistant.",
}

st.set_page_config(page_title="Azure GPT-4o-mini Chatbot", layout="centered")
st.title("Azure GPT-4o-mini Chatbot")
st.caption("FastAPI backend + Streamlit frontend, powered by Azure OpenAI.")

if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.subheader("Settings")
    temperature = st.slider("Temperature", 0.0, 1.0, 0.7, 0.1)
    if st.button("Clear conversation"):
        st.session_state.messages = []
        st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Ask me anything...")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = requests.post(
                    CHAT_ENDPOINT,
                    json={
                        "messages": [SYSTEM_PROMPT] + st.session_state.messages,
                        "temperature": temperature,
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                reply = response.json()["reply"]
            except requests.HTTPError:
                detail = response.json().get("detail", "Unknown error") if response.content else "Unknown error"
                reply = f"Backend error: {detail}"
            except requests.RequestException as exc:
                reply = f"Could not reach the backend at {BACKEND_URL}: {exc}"

        st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})
