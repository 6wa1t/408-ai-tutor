"""Shared API utilities for 408 AI Tutor frontend pages."""


def get_api_base() -> str:
    """Resolve the backend API base URL from session state or environment."""
    import streamlit as st
    import os
    return st.session_state.get("api_base", os.environ.get("API_BASE_URL", "http://localhost:8000"))
