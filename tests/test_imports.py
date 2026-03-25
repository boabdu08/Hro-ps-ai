def test_backend_app_imports():
    import main  # noqa: F401


def test_dashboard_imports():
    # Ensure Streamlit app can import without bringing heavy ML deps in CI.
    # Dashboard imports API client, which imports settings. This should be safe.
    import dashboard  # noqa: F401
