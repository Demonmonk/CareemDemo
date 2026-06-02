"""
Entry point for Streamlit Community Cloud.

Streamlit Cloud defaults the "Main file path" to `streamlit_app.py`. The real
app lives in `app.py`; this thin shim just runs it so the default path works
with no extra configuration.
"""

import runpy

runpy.run_path("app.py", run_name="__main__")
