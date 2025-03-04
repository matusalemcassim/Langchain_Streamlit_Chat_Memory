# python 3.8 (3.8.16) or it doesn't work
# pip install streamlit streamlit-chat langchain python-dotenv
import streamlit as st
from streamlit_chat import message
from dotenv import load_dotenv
import os
import base64

from SQLAgent import SQLAgent
from DataFormatter import DataFormatter

from langchain.chat_models import ChatOpenAI
from langchain.schema import (
    SystemMessage,
    HumanMessage,
    AIMessage
)

# ✅ Function to convert images to Base64 for HTML display
def get_base64(image_path):
    """Convert image to Base64 for HTML rendering in Streamlit."""
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()

# ✅ Define paths for logos
LOGO_DISTRITO_PATH = "logo/distrito-logo.png"
LOGO_HONDA_PATH = "logo/honda-logo.png"

def main():

    # setup streamlit page
    st.set_page_config(
        page_title="SQL Chatbot",
        page_icon="🤖"
    )

    # ✅ Layout: Left Logo - Title - Right Logo
    col1, col2, col3 = st.columns([0.10, 0.7, 0.15])

    with col1:
        st.markdown(
            f"""
            <div style="display: flex; justify-content: center; align-items: center; height: 100%;">
                <img src="data:image/png;base64,{get_base64(LOGO_DISTRITO_PATH)}" style="width:70px; height:auto;"/>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown("<h1 style='text-align: center; margin-bottom: 0px;'>Converse com os seus Dados</h1>", unsafe_allow_html=True)

    with col3:
        st.markdown(
            f"""
            <div style="display: flex; justify-content: center; align-items: center; height: 100%;">
                <img src="data:image/png;base64,{get_base64(LOGO_HONDA_PATH)}" style="width:70px; height:auto;"/>
            </div>
            """,
            unsafe_allow_html=True,
        )

    agent = SQLAgent()
    formatter = DataFormatter()

    chat = ChatOpenAI(temperature=0)

    # initialize message history
    if "messages" not in st.session_state:
        st.session_state.messages = [
            SystemMessage(content="You are a helpful assistant.")
        ]

    # sidebar with user input
    with st.sidebar:
        # user_input = st.text_input("Faça sua pergunta: ", key="user_input")
        with st.form(key="chat_form"):
            user_input = st.text_input("Faça sua pergunta: ",  key="user_input")
            submit_button = st.form_submit_button("ENVIAR")

        # handle user input
        if user_input:
            st.session_state.messages.append(HumanMessage(content=user_input))
            with st.spinner("Pensando..."):
                print(st.session_state.messages)
                response = chat(st.session_state.messages)
            st.session_state.messages.append(
                AIMessage(content=response.content))

    # display message history
    messages = st.session_state.get('messages', [])
    for i, msg in enumerate(messages[1:]):
        if i % 2 == 0:
            message(msg.content, is_user=True, key=str(i) + '_user')
        else:
            message(msg.content, is_user=False, key=str(i) + '_ai')


if __name__ == '__main__':
    main()