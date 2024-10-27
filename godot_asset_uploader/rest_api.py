from dataclasses import replace
from enum import Enum
from itertools import dropwhile, islice, zip_longest, count
import math
import re

from bs4 import BeautifulSoup
import dirtyjson
from validator_collection.checkers import is_integer, is_url
import requests
from yarl import URL

from .util import StrEnum, dict_merge, normalise_newlines
from .errors import *

OFFICIAL_LIBRARY_ROOT = URL("https://godotengine.org/")
# FIXME: This is not actually stated anywhere in the docs, but circumstancial
# evidence suggests that categories and their ids are specific to the given
# library. This will need refactoring if other libraries ever become a thing
KNOWN_LIBRARY_CATEGORIES = {
    OFFICIAL_LIBRARY_ROOT: {
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
}

CATEGORY_ID_MAP = {
    lib: {
        id: (group, name)
        for group, names in categories.items()
        for id, name in names.items()
    } for lib, categories in KNOWN_LIBRARY_CATEGORIES.items()
}

def find_category_id(designator, library=OFFICIAL_LIBRARY_ROOT):
    """Find a category id from a possibly shorthand designator, such as 'Addons/Misc',
'a/2d' or 'proj'"""
    if len(parts := [x.lower() for x in re.split('[/_ ]', designator, maxsplit=1)]) == 2:
        group_cand, name_cand = parts
    elif len(parts) == 1:
        (name_cand,) = parts
        group_cand = ""
    else:
        raise ValueError(f"Can't interpret '{designator}' as an asset category")

    candidates = {
        f"{group}/{name}": id for group, names in KNOWN_LIBRARY_CATEGORIES[library].items()
        for id, name in names.items()
        if group.lower().startswith(group_cand)
        and name.lower().startswith(name_cand)
    }
    if not candidates:
        raise ValueError(f"Value '{designator}' could not be matched to an asset category")
    if len(candidates) > 1:
        raise ValueError(f"Ambiguous category '{designator}': could be any of {', '.join(candidates)}")

    (cand_id,) = candidates.values()
    return cand_id

def find_category_name(id, library=OFFICIAL_LIBRARY_ROOT):
    if not id:
        return (None, None)
    return CATEGORY_ID_MAP[OFFICIAL_LIBRARY_ROOT].get(int(id), (None, None))

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
        parsed = URL(id_or_url)
        # Currently we're only supporting the official asset library
        if parsed.scheme and parsed.host == OFFICIAL_LIBRARY_ROOT.host:
            path = list(dropwhile(lambda x: x != "asset", parsed.parts))
            if path and len(path) > 1:
                prefix, id, *suffix = path
                try:
                    return int(id) if not suffix else None
                except ValueError:
                    pass
    raise GdAssetError(f"{id_or_url} is not a valid asset ID or asset URL")


def get_library_url(*path, workaround=False):
    return str(OFFICIAL_LIBRARY_ROOT.joinpath("asset-library", *([] if workaround else ["api"]), *path))


def api_request(meth, *url, workaround=False, data=None, params=None, headers=None, cookies=None):
    headers = headers or {}
    if not workaround:
        headers.update({'Accept': 'application/json'})
    resp = requests.request(meth, get_library_url(*url, workaround=workaround),
                            data=data, headers=headers, params=params, cookies=cookies)
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        try:
            if not workaround:
                detail = resp_json(resp).get("error", "")
                detail = detail and f": {detail}"
            else:
                detail = f": {resp.reason}"
        except dirtyjson.error.Error:
            detail = ""
        raise HTTPRequestError(f"'{resp.request.method}' API request to '{'/'.join(url)}' failed with code {resp.status_code}{detail}")
    try:
        return resp_json(resp) if not workaround else resp
    except dirtyjson.error.Error:
        return {}


def get_csrf_for_workaround(token, *url):
    """Get CSRF token to work around bugs in asset library by selectively sending things as an HTML
form instead of using the REST API.

Cf. https://github.com/godotengine/godot-asset-library/issues/343 for context"""
    cookies = {"token": token}
    resp = requests.get(get_library_url(*url, workaround=True), cookies=cookies)
    soup = BeautifulSoup(resp.text, "html.parser")
    resp.cookies.update(cookies)
    return (
        resp.cookies,
        {
            "csrf_name": soup.select("form input[name=csrf_name]")[0].attrs["value"],
            "csrf_value": soup.select("form input[name=csrf_value]")[0].attrs["value"],
        }
    )


def GET(*url, params=None, headers=None):
    return api_request("get", *url, params=params, headers=headers)


def POST(*url, data=None, params=None, headers=None):
    return api_request("post", *url, data=data, params=params, headers=headers)


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


def is_payload_same(payload, reference):
    payload = dict(**payload)
    reference = dict(**reference)
    def normalise(previews):
        return [{
            "type": p["type"],
            "link": p["link"],
            "thumbnail": p.get("thumbnail") or p["link"],
        } for p in previews]

    def unmangle(v):
        return normalise_newlines(v).strip("\n") if isinstance(v, str) else v

    payload["previews"] = normalise(payload.get("previews", []))
    reference["previews"] = normalise(reference.get("previews", []))
    return (p1 := {k: unmangle(v) for k, v in payload.items()}) == (p2 := {k: unmangle(v) for k, v in reference.items()})


def is_payload_same_as_pending(payload, previous, pending):
    keys = (set(payload) | set(pending)) - {
        # These are only present in edits, except for category, which
        # for some reason is empty there
        'edit_id', 'user_id', 'submit_date', 'modify_date',
        'category', 'status', 'reason', 'support_level',
    }
    payload = dict_merge(previous, payload)
    pending = dict_merge(previous, pending)
    return is_payload_same({k: v for k, v in payload.items() if k in keys},
                           {k: v for k, v in pending.items() if k in keys})


def merge_asset_payload(new, old=None):
    old = old or {}
    volatile = ["download_commit", "version_string", "version",
                "type", "category", "rating", "support_level", "searchable",
                "author", "author_id", "modify_date",]
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

        return dict(**{"enabled": True,},
                    **op,
                    **{"type": p_new["type"],
                       "link": p_new["link"],
                       "thumbnail": p_new.get("thumbnail", p_new["link"])},
                    )

    payload["previews"] = [calculate_preview(p_new, p_old)
                           for p_new, p_old in zip_longest(new.get("previews", []), old.get("previews", []))
                           if p_new != p_old]
    return payload


def massage_previews_for_workaround(previews):
    """Re-encode previews into the special format the asset library HTML forms get
the previews in, to work around bugs"""
    return {
        f"previews[{i}][{k}]": v
        for i, preview in enumerate(previews)
        for k, v in preview.items()
    }


def upload_or_update_asset(cfg, json, workaround=True):
    json = dict(json)
    url = ("asset", json["asset_id"]) if "asset_id" in json else ("asset",)
    if workaround:
        cookies, csrf = get_csrf_for_workaround(cfg.auth.token, *url, "edit" if "asset_id" in json else "submit")
        json.update(csrf)
        json.update(massage_previews_for_workaround(json.pop("previews", [])))
        resp = api_request("post", *url, data=json, workaround=True, cookies=cookies)
        try:
            loc, id = URL(resp.url).parts[-2:]
            # not int(...) is technically unsafe if the int can equal 0, but
            # edit IDs start at 1, so it's fine
            if loc != "asset" or not int(id):
                raise ValueError
        except ValueError:
            raise HTTPRequestError(f"'{resp.request.method}' request with HTML form workaround to '{'/'.join(url)}' "
                                   "did not return expected data, upload probably failed")
    else:
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
