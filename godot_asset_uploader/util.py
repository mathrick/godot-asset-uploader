import email
from functools import lru_cache
from itertools import islice
import os
import typing as t
import shutil
import sys, pdb, traceback

from yarl import URL

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".ogv", ".ogg"}
IMAGE_EXTS = {".jpg", ".png", ".webp", ".gif"}

YOUTUBE_URL = URL("https://youtube.com/watch")
YOUTUBE_DOMAINS = ("youtube.com", "youtube-nocookie.com")


def is_interesting_link(href):
    "Return True if href is 'interesting', ie. might potentially point to preview media"
    uri = URL(href)
    if uri.scheme and uri.scheme not in ("http", "https"):
        return False
    if not uri.scheme:
        _, maybe_email = email.utils.parseaddr(uri.path)
        # If we see an @, we assume it's an email, since GFM will
        # parse and autolink it as an email
        if "@" in maybe_email:
            return False
    return True


def is_image_link(href):
    uri = URL(href)
    return uri.path and any(uri.path.lower().endswith(ext) for ext in IMAGE_EXTS)


def normalise_youtube_link(href):
    uri = URL(href)
    if uri.scheme and uri.scheme in ["http", "https"]:
        path = uri.path.strip("/")
        if any(uri.host.endswith(domain) for domain in YOUTUBE_DOMAINS):
            if path == "oembed":
                return "url" in uri.query and normalise_youtube_link(uri.query["url"])
            if path in ("watch", "embed"):
                return "v" in uri.query and str(YOUTUBE_URL.with_query(v=uri.query["v"]))
            if any(path.startswith(f"{x}/") for x in ["watch", "embed", "v", "e", "live", "shorts"]):
                return str(YOUTUBE_URL.with_query(v=path.split("/")[-1]))
        # Special case: youtube accepts URLs of the form http://youtu.be/{id}&feature=channel,
        # which don't have a ? to mark the query string. But it also accepts
        # ones with proper ? present.
        if uri.host.endswith("youtu.be"):
            resolved = YOUTUBE_URL.with_query(f"v={uri.path[1:]}").update_query(uri.query)
            return normalise_youtube_link(resolved)
    return None


def normalise_video_link(href):
    if (out := normalise_youtube_link(href)):
        return out
    uri = URL(href)
    if uri.path and set(uri.suffixes) & VIDEO_EXTS:
        return href
    return None


def is_youtube_link(href):
    return normalise_youtube_link(href) is not None


def terminal_width(max_width=100):
    return min(shutil.get_terminal_size().columns, max_width)


def debug_on_error():
    # copied from pdbpp.xpm(), to provide a portable fallback in case pdbpp is
    # not present
    if (debug := os.getenv("DEBUG")) and debug.lower() not in ["0", "no"]:
        print(traceback.format_exc())
        pdb.post_mortem(sys.exc_info()[2])
    else:
        # NB: Turns out this is legal, as long as an exception is being handled,
        # it doesn't need to be lexically visible
        raise


def is_sequence(x):
    return isinstance(x, t.Sequence) and not isinstance(x, (bytes, str))


def ensure_tuple(x):
    if isinstance(x, tuple):
        return x
    return (x,)


def ensure_sequence(x):
    return x if is_sequence(x) else (x,)


def dict_merge(d1, d2):
    "Like d1.update(d2), but returns a new dict"
    return {k: d2.get(k, d1.get(k)) for k in set(d1) | set(d2)}


def batched(iterable, n):
    # batched('ABCDEFG', 3) → ABC DEF G
    if n < 1:
        raise ValueError('n must be at least one')
    iterator = iter(iterable)
    while batch := tuple(islice(iterator, n)):
        yield batch


def normalise_newlines(string):
    "Normalise \r and \r\n to \n"
    return "\n".join(string.splitlines())


def prettyprint_list(elems, sep1=" and ", sep2=", ", sep3=", and "):
    """Return a string listing elems in a nice way, ie.:
    * foo
    * foo and bar
    * foo, bar, and baz
    """
    elems = list(map(str, elems))
    if len(elems) <= 1:
        return "".join(elems)
    if len(elems) == 2:
        return sep1.join(elems)
    else:
        return f"{sep2.join(elems[:-1])}{sep3}{elems[-1]}"


@lru_cache
def is_typed_as(spec, x):
    """Return True if X (a type) matches SPEC (a type annotation). SPEC
can either be a simple type itself, or a more complicated construct,
such as Optional[Dict[str,int]]"""
    def get_base_type(T):
        origin = t.get_origin(T)
        if origin == t.Union:
            return t.get_args(T)
        if origin:
            return origin
        return T

    return issubclass(x, tuple([get_base_type(T) for T in ensure_tuple(spec)]))
