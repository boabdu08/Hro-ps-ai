import pandas as pd
import streamlit as st


def load_users():
    return pd.read_csv("users.csv")


def authenticate_user(username, password):
    users = load_users()

    user = users[
        (users["username"] == username) &
        (users["password"].astype(str) == str(password))
    ]

    if len(user) == 1:
        return user.iloc[0].to_dict()

    return None


def login_form():
    st.markdown("## 🔐 Staff Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    login_clicked = st.button("Login")

    if login_clicked:
        user = authenticate_user(username, password)

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