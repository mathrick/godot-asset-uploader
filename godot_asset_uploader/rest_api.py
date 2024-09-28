from itertools import dropwhile
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlparse

import requests

from .util import StrEnum
from .errors import *

OFFICIAL_LIBRARY_ROOT = "https://godotengine.org/"
# FIXME: This is not actually stated anywhere in the docs, but circumstancial
# evidence suggests that categories and their ids are specific to the given
# library. This will need refactoring if other libraries ever become a thing
OFFICIAL_LIBRARY_CATEGORIES = {
    "Addons": {
        1: "2D Tools",
        2: "3D Tools",
        3: "Shaders",
        4: "Materials",
        5: "Tools",
        6: "Scripts",
        7: "Misc"
    },
    "Projects": {
        8: "Templates",
        9: "Projects",
        10: "Demos",
    },
}

# FIXME: Support other providers
class RepoProvider(StrEnum):
    CUSTOM = "Custom"
    GITHUB = "GitHub"
    GITLAB = "GitLab"
    BITBUCKET = "BitBucket"


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

def api_request(meth, *url, params=None, headers=None):
    headers = headers or {}
    headers.update({'Accept': 'application/json'})
    req = requests.request(meth, get_library_url(*url), headers=headers, data=params)
    try:
        req.raise_for_status()
    except requests.HTTPError:
        try:
            detail = req.json().get("error", "")
            detail = detail and f": {detail}"
        except requests.JSONDecodeError:
            detail = ""
        raise GdAssetError(f"API request to '{'/'.join(url)}' failed with code {req.status_code}{detail}")
    return req.json()

def GET(*url, params=None, headers=None):
    return api_request("get", *url, params=params, headers=headers)

def POST(*url, params=None, headers=None):
    return api_request("post", *url, params=params, headers=headers)

def get_asset_info(id):
    return GET("asset", guess_asset_id(id))

def login(user, passwd):
    json = POST("login", params={"username": user, "password": passwd})
