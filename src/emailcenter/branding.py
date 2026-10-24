"""Shared local branding, including a self-contained browser logo."""

import base64
from pathlib import Path


def logo_path():
    from .resources import resource_path
    return resource_path('assets', 'Logo256.png')


def logo_data_url():
    path = logo_path()
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii") if path.is_file() else ""
