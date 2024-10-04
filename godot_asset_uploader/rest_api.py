from dataclasses import replace
from itertools import dropwhile, islice, zip_longest, count
import math
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlparse

import dirtyjson
from validator_collection.checkers import is_integer, is_url
import requests

from .util import StrEnum, dict_merge, normalise_newlines
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

def resp_json(resp):
    """Like requests.response.json(), but uses dirtyjson to be more
resilient to PHP's bullshit that we get back"""
    return dirtyjson.loads(resp.content)

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

def api_request(meth, *url, data=None, params=None, headers=None):
    headers = headers or {}
    headers.update({'Accept': 'application/json'})
    resp = requests.request(meth, get_library_url(*url), data=data, headers=headers, params=params)
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        try:
            detail = resp_json(resp).get("error", "")
            detail = detail and f": {detail}"
        except dirtyjson.error.Error:
            detail = ""
        raise HTTPRequestError(f"'{resp.request.method}' API request to '{'/'.join(url)}' failed with code {resp.status_code}{detail}")
    try:
        return resp_json(resp)
    except dirtyjson.error.Error:
        return {}

def GET(*url, params=None, headers=None):
    return api_request("get", *url, params=params, headers=headers)

def POST(*url, data=None, params=None, headers=None):
    return api_request("post", *url, data=None, params=params, headers=headers)

def get_paginated(*url, params=None, headers=None, max_pages=None):
    result = []
    for page in islice(count(0), max_pages):
        params["page"] = page
        json = GET(*url, params=params, headers=headers)
        result += json["result"]
        if page >= json["pages"] - 1:
            break
    return result

def get_asset_info(asset_id):
    return GET("asset", guess_asset_id(asset_id))

def get_pending_edits(asset_id):
    """Get the updated payloads representing any pending edits for the
asset. Edits will be merged with the original payload info."""
    # We have to get the ids first, then fetch each edit individually,
    # because asset/edit listings lack commits and previews
    ids = [edit["edit_id"]
           for edit in get_paginated("asset", "edit", params={
                   "asset": guess_asset_id(asset_id), "status": "new in_review"
           })]
    return [dict_merge(edit["original"],
                       # Need to normalise strings heavily because
                       # browser edits mangle things horribly
                       {k: v
                        for k, v in edit.items() if v is not None and k != "original"})
            for edit_id in ids
            for edit in [GET("asset", "edit", edit_id)]]


def is_payload_same_as_pending(previous, payload, pending):
    def normalise(previews):
        return [{
            "type": p["type"],
            "link": p["link"],
            "thumbnail": p.get("thumbnail", p["link"])
        } for p in previews]

    def unmangle(v):
        return normalise_newlines(v).strip("\n") if isinstance(v, str) else v

    keys = (set(payload) | set(pending)) - {
        # These are only present in edits, except for category, which
        # for some reason is empty there
        'edit_id', 'user_id', 'submit_date', 'modify_date',
        'category', 'status', 'reason', 'support_level',
    }
    payload = dict_merge(previous, payload)
    payload["previews"] = normalise(payload["previews"])
    pending = dict_merge(previous, pending)
    pending["previews"] = normalise(pending["previews"])
    return not [k for k in keys if unmangle(payload.get(k)) != unmangle(pending.get(k))]


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
    POST(*url, data=json)

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
    json = POST("login", data={"username": user, "password": passwd})
    return json

def login_and_update_token(cfg, force=False):
    if cfg.auth.token and not force:
        return
    json = login(cfg.auth.username, cfg.auth.password)
    cfg.auth.token = json["token"]
