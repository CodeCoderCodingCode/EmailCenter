"""Read-only application resources in source checkouts and frozen distributions."""
from pathlib import Path
import sys


def resource_path(*parts):
    root = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]
    return root.joinpath(*parts)


def shared_oauth_client():
    path = resource_path('assets', 'oauth', 'desktop_client.json')
    if path.is_file():
        return path
    # Development uses the existing Desktop client. Never discover token files.
    if not getattr(sys, 'frozen', False):
        candidates = sorted(resource_path('json').glob('client_secret_*.apps.googleusercontent.com.json'))
        if len(candidates) == 1:
            return candidates[0]
    return None
