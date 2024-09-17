from itertools import dropwhile
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlparse
import requests

OFFICIAL_LIBRARY_ROOT = "https://godotengine.org/"

def guess_asset_id(id_or_url):
    "Attempt to guess asset id from what might be an existing URL"
    parsed = urlparse(str(id_or_url))
    # Currently we're only supporting the official asset library
    if parsed.scheme and parsed.netloc == urlparse(OFFICIAL_LIBRARY_ROOT).netloc:
        path = list(dropwhile(lambda x: x != "asset", PurePosixPath(parsed.path).parts))
        if path and len(path) > 1:
            prefix, id, *suffix = path
            try:
                return int(id) if not suffix else None
            except ValueError:
                pass
    return id_or_url

def get_library_url(*path):
    rest = "/".join(["asset-library", "api"] + [str(p) for p in path])
    url = urljoin(OFFICIAL_LIBRARY_ROOT, rest)
    return url

def get_library_json(url, params=None, headers=None):
    headers = headers or {}
    headers.update({'Accept': 'application/json'})
    return requests.get(url, headers=headers, params=params).json()

def get_asset_info(id):
    return get_library_json(get_library_url("asset", guess_asset_id(id)))
