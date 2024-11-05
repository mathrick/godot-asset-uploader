from functools import wraps
from itertools import chain
from pathlib import Path
import shutil

import decorators
import hglib

from ..errors import DependencyMissingError


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
def has_hg_executable():
    return shutil.which("hg")


class ensure_hg_executable(decorators.FuncDecorator):
    "Decorator to simplify making sure we don't try to invoke hglib if hg executable is not present"
    def decorate(self, func, error=False, fallback=None):
        @wraps(func)
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


@ensure_hg_executable
def has_repo(path):
    try:
        client = get_client_for(path)
        return Path(s_(client.root())) == Path(path)
    except hglib.error.ServerError:
        return False
