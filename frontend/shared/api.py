"""Shared API utilities for 408 AI Tutor frontend pages."""


def get_api_base() -> str:
    """Resolve the backend API base URL from session state or environment.

    This URL is used for **server-side** HTTP requests (requests.get/post)
    from within the Streamlit process.  In Docker it points to the
    internal service name, e.g. ``http://backend:8000``.
    """
    import streamlit as st
    import os
    return st.session_state.get("api_base", os.environ.get("API_BASE_URL", "http://localhost:8000"))


def get_public_api_base() -> str:
    """Return a browser-accessible URL for static resources (images).

    ``st.image(url)`` sends the URL to the **browser**, which cannot
    resolve Docker-internal hostnames like ``backend``.  The environment
    variable ``PUBLIC_API_URL`` should be set to a host-reachable address
    such as ``http://localhost:8000``.

    Falls back to ``get_api_base()`` when ``PUBLIC_API_URL`` is not set
    (e.g. local dev where both URLs are the same).
    """
    import os
    return os.environ.get("PUBLIC_API_URL", get_api_base())
