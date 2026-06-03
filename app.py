import streamlit as st
from src.rag_pipeline import chat, make_memory

st.set_page_config(page_title="RAG")
st.title("RAG Assignment")

if "memory" not in st.session_state:
    st.session_state.memory = make_memory()
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

user_input = st.chat_input("Ask something…")
if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            reply = chat(st.session_state.memory, user_input)
        st.write(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})
