from functools import lru_cache
from itertools import chain
from pathlib import Path
import shutil

import decorators
import hglib

from ..errors import DependencyMissingError
from .providers import remote_to_https


def b_(val):
    "Make value a bytes-like object that can be passed to hg"
    if isinstance(val, (bytes, bytearray)):
        return val
    # FIXME: Is that correct? Are we guaranteed that the default encoding is
    # UTF-8? And is that always what we should be passing into hg?
    return str(val).encode()


def s_(val):
    "Decode a string from a bytes-like object received from hg"
    if isinstance(val, str):
        return val
    # FIXME: Same as for b_(), is this correct?
    return val.decode()


# FIXME: Need to figure out how to package hg when creating distributions, so we
# don't have to rely on PATH just having hg available, which is going to be a
# huge pain to ensure, especially on Windows
@lru_cache(maxsize=4)
def has_hg_executable():
    return shutil.which("hg")


class ensure_hg_executable(decorators.FuncDecorator):
    "Decorator to simplify making sure we don't try to invoke hglib if hg executable is not present"
    def decorate(self, func, error=False, fallback=None):
        def wrapper(*args, **kwargs):
            if not has_hg_executable():
                if error:
                    raise DependencyMissingError("hg executable not found in PATH")
                return fallback
            return func(*args, **kwargs)

        return wrapper


CLIENTS = {}

@ensure_hg_executable(error=True)
def get_client_for(path):
    "Caching version of hglib.open()"
    path = Path(path)
    if path not in CLIENTS:
        client = hglib.open(b_(path))
        root = Path(s_(client.root()))
        for dir in chain([path], path.parents):
            CLIENTS[dir] = client
            if dir == root:
                break
    return CLIENTS[path]


@ensure_hg_executable(fallback=False)
def has_repo(path):
    # Note: originally, this code used get_client_for(), but this is very slow
    # in testing. Pytest defeats our caching attempts, and trying to open a
    # client in a non-hg directory can take over 0.5s
    return (path := Path(path) / ".hg").exists() and path.is_dir()


@ensure_hg_executable
def get_repo(path):
    """Open a repo containing PATH, traversing up the tree as needed, and using
whatever VCS is closest (currently Git and Mercurial are supported)."""
    try:
        return get_client_for(path)
    except hglib.error.ServerError:
        return None


# FIXME: should this try to handle hg-git and git remotes?
@ensure_hg_executable(error=True)
def guess_commit(root):
    client = get_client_for(root)
    return s_(client.parents()[0].node)


def guess_repo_url(root):
    client = get_repo(root)
    for cand in ["default-push", "default"]:
        if b_(cand) in client.paths():
            return remote_to_https(s_(client.paths()[b_(cand)]))
    return None
