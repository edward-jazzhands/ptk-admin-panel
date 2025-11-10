run-dev:
    uv run -m ptk_admin_panel

gunicorn:
    uv run gunicorn -w 4 -b 0.0.0.0:5000 src.ptk_admin_panel.app:app --access-logfile -