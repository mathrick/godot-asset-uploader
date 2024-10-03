from dataclasses import replace
from itertools import dropwhile, zip_longest
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlparse

from validator_collection.checkers import is_integer, is_url
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

    @classmethod
    def _missing_(cls, value):
        value = value.upper()
        for member in cls:
            if member.name == value:
                return member
        return None

def guess_asset_id(id_or_url):
    "Attempt to guess asset id from what might be an existing URL"
    if is_integer(id_or_url):
        return id_or_url
    if is_url(id_or_url):
        parsed = urlparse(id_or_url)
        # Currently we're only supporting the official asset library
        if parsed.scheme and parsed.netloc == urlparse(OFFICIAL_LIBRARY_ROOT).netloc:
            path = list(dropwhile(lambda x: x != "asset", PurePosixPath(parsed.path).parts))
            if path and len(path) > 1:
                prefix, id, *suffix = path
                try:
                    return int(id) if not suffix else None
                except ValueError:
                    pass
    raise GdAssetError(f"{id_or_url} is not a valid asset ID or asset URL")

def get_library_url(*path):
    rest = "/".join(["asset-library", "api"] + [str(p) for p in path])
    url = urljoin(OFFICIAL_LIBRARY_ROOT, rest)
    return url

def api_request(meth, *url, params=None, headers=None):
    headers = headers or {}
    headers.update({'Accept': 'application/json'})
    resp = requests.request(meth, get_library_url(*url), headers=headers, data=params)
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        try:
            detail = resp.json().get("error", "")
            detail = detail and f": {detail}"
        except requests.JSONDecodeError:
            detail = ""
        raise HTTPRequestError(f"'{resp.request.method}' API request to '{'/'.join(url)}' failed with code {resp.status_code}{detail}")
    return resp.json()

def GET(*url, params=None, headers=None):
    return api_request("get", *url, params=params, headers=headers)

def POST(*url, params=None, headers=None):
    return api_request("post", *url, params=params, headers=headers)

def get_asset_info(id):
    return GET("asset", guess_asset_id(id))

def merge_asset_payload(new, old=None):
    old = old or {}
    volatile = ["download_commit", "version_string"]
    special = ["previews"]
    payload = {k: v for k, v in old.items() if k not in volatile + special}
    payload.update({k: v for k, v in new.items() if k not in special})

    def calculate_preview(p_new, p_old):
        if p_new and p_old:
            op = {"operation": "update",
                  "edit_preview_id": p_old["preview_id"]}
        elif p_new and not p_old:
            op = {"operation": "insert"}
        else:
            return {"operation": "delete",
                    "edit_preview_id": p_old["preview_id"]}

        return dict(**{"enabled": True,
                       "type": p_new["type"],
                       "link": p_new["link"],
                       "thumbnail": p_new.get("thumbnail")},
                    **op)

    payload["previews"] = [calculate_preview(p_new, p_old)
                           for p_new, p_old in zip_longest(new.get("previews", []), old.get("previews", []))
                           if p_new != p_old]
    return payload

def upload_or_update_asset(cfg, json, retries=1):
    url = ("asset", json["asset_id"]) if "asset_id" in json else ("asset",)
    json["token"] = cfg.auth.token
    POST(*url, params=json)

def update_cfg_from_payload(cfg, json):
    remap = {
        "version_string": "version",
        "cost": "licence",
        "download_provider": "repo_provider",
        "download_commit": "commit",
        "browse_url": "repo_url",
    }
    return replace(cfg, **{remapped: v for k, v in json.items()
                           if (remapped := remap.get(k, k)) in cfg.fields()})

def login(user, passwd):
    json = POST("login", params={"username": user, "password": passwd})
    return json

def login_and_update_token(cfg, force=False):
    if cfg.auth.token and not force:
        return
    json = login(cfg.auth.username, cfg.auth.password)
    cfg.auth.token = json["token"]
