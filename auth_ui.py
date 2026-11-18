"""Login/signup gate + the top-right account control, called once from app.py.

Kept at the project root alongside theme.py/live.py -- pure UI glue, not
business logic, so investor_ai/ stays Streamlit-free.

Login state lives in st.session_state, which Streamlit shares across every
page within one browser session -- log in once, it holds as you navigate
between pages. It does NOT survive closing the browser tab or restarting
the app; there's no persistent cookie/token here. That's a deliberate v1
simplification (no extra dependency, no external identity provider) --
fine for a small personal/shared tool, worth revisiting before this handles
anything more sensitive.

There is no sidebar in this layout (navigation moved to a top bar via
st.navigation(position="top")) -- account status/logout are pinned to the
top-right corner instead, on the same axis as the nav. Deliberately no live
portfolio value here: computing it needs a fresh price fetch per held
ticker, and this control renders on every single page (including ones like
Manage Positions that intentionally stay network-light), so it only shows
things that cost a local DB read at most.
"""

import streamlit as st

from investor_ai import auth


def require_login() -> int:
    """Shows a login/signup form and halts the app (st.stop()) until the
    visitor is authenticated. Returns the logged-in user's id otherwise.

    Called once from app.py (the router), right after apply_theme() and
    before st.navigation/nav.run() -- individual pages read
    st.session_state["user_id"] directly rather than calling this again.
    """
    auth.init_db()

    if "user_id" in st.session_state:
        _render_account_control()
        return st.session_state["user_id"]

    st.title("Log in")
    st.caption("Each account has its own private paper portfolio -- nobody else can see or edit it.")

    tab_login, tab_signup = st.tabs(["Log in", "Create account"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in")
            if submitted:
                user_id = auth.authenticate(username, password)
                if user_id is not None:
                    st.session_state["user_id"] = user_id
                    st.session_state["username"] = username.strip()
                    st.rerun()
                else:
                    st.error("Incorrect username or password.")

    with tab_signup:
        with st.form("signup_form"):
            new_username = st.text_input("Choose a username")
            new_password = st.text_input(
                "Choose a password", type="password", help=f"At least {auth.MIN_PASSWORD_LENGTH} characters."
            )
            confirm_password = st.text_input("Confirm password", type="password")
            submitted = st.form_submit_button("Create account")
            if submitted:
                if new_password != confirm_password:
                    st.error("Passwords don't match.")
                else:
                    try:
                        user_id = auth.create_user(new_username, new_password)
                    except auth.UsernameTakenError as e:
                        st.error(str(e))
                    except auth.WeakCredentialsError as e:
                        st.error(str(e))
                    else:
                        st.session_state["user_id"] = user_id
                        st.session_state["username"] = new_username.strip()
                        st.success("Account created!")
                        st.rerun()

    st.stop()


def _render_account_control() -> None:
    """Account status + logout, pinned to the top-right corner.

    Rendered here as ordinary page content and then fixed into position by
    CSS (see theme.py, .st-key-account_bar). Streamlit draws the top nav in
    its own header region, and there is no API to place widgets inside it,
    so sharing that horizontal axis means positioning against the viewport.

    Deliberately no wordmark: the nav's Home entry and the home page's own
    title carry identity, and a second row just for a logo was the awkward
    band this replaces.
    """
    with st.container(horizontal=True, vertical_alignment="center", key="account_bar"):
        st.caption(f"Logged in as **{st.session_state.get('username', '')}**")
        if st.button("Log out", icon=":material/logout:", key="app_bar_logout"):
            # Clear everything, not just the identity keys -- otherwise
            # per-account UI state (like the Recommendations page's
            # "changed since last check" tracking) could leak into whatever
            # account logs in next in this same browser tab.
            st.session_state.clear()
            st.rerun()
