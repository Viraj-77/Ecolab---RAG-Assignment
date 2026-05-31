import streamlit as st
from src.rag_pipeline import chat, SYSTEM_PROMPT, LOCAL_SYSTEM_PROMPT, TOOLS_ENABLED
SYSTEM_PROMPT = SYSTEM_PROMPT if TOOLS_ENABLED else LOCAL_SYSTEM_PROMPT
from src.conversational_memory import ConversationMemory

st.set_page_config(page_title="RAG")
st.title("RAG Assignment")


#syn for Streamlit to remember things.
if "memory" not in st.session_state:
    st.session_state.memory = ConversationMemory(SYSTEM_PROMPT)
if "messages" not in st.session_state:
    st.session_state.messages = []

#logic to load old message
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

#syn for chat input
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