import streamlit as st
from api_client import login_user_api


def login_form():
    st.markdown("## 🔐 Staff Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if not username.strip() or not password.strip():
            st.warning("Please enter both username and password.")
            return

        user = login_user_api(username.strip(), password)

        if user:
            st.session_state["logged_in"] = True
            st.session_state["user"] = user
            st.success(f"Welcome, {user['name']}")
            st.rerun()
        else:
            st.error("Invalid username or password")


def logout_button():
    if st.sidebar.button("Logout"):
        st.session_state["logged_in"] = False
        st.session_state["user"] = None
        st.rerun()


def require_login():
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if "user" not in st.session_state:
        st.session_state["user"] = None

    return st.session_state["logged_in"]