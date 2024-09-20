import email
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import typing as t

import click

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".ogv", ".ogg")
IMAGE_EXTS = (".jpg", ".png", ".webp", ".gif")

YOUTUBE_URL = "https://youtube.com/watch?v={id}"

def is_interesting_link(href):
    "Return True if href is 'interesting', ie. might potentially point to preview media"
    uri = urlparse(href)
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
    uri = urlparse(href)
    return uri.path and any([uri.path.lower().endswith(ext) for ext in IMAGE_EXTS])

def normalise_youtube_link(href):
    uri = urlparse(href)
    if uri.scheme and uri.scheme in ["http", "https"]:
        path = uri.path.strip("/")
        qs = parse_qs(uri.query)
        if uri.netloc.endswith("youtube.com") or uri.netloc.endswith("youtube-nocookie.com"):
            if path == "oembed":
                return normalise_youtube_link(qs["url"][0]) if "url" in qs else None
            if path in ("watch", "embed"):
                return YOUTUBE_URL.format(id=qs["v"][0]) if "v" in qs else None
            if any(path.startswith(f"{x}/") for x in ["watch", "embed", "v", "e", "live", "shorts"]):
                return YOUTUBE_URL.format(id=path.split("/")[-1])
        if uri.netloc.endswith("youtu.be"):
            return YOUTUBE_URL.format(id=path)
    return None

def normalise_video_link(href):
    if (out := normalise_youtube_link(href)):
        return out
    uri = urlparse(href)
    if uri.path and any([uri.path.lower().endswith(ext) for ext in VIDEO_EXTS]):
        return href
    return None

def is_youtube_link(href):
    return normalise_youtube_link(href) is not None

def unexpanduser(path):
    path = Path(path)
    if path.is_relative_to(Path.home()):
        return "~" / path.relative_to(Path.home())

def ensure_tuple(x):
    if isinstance(x, tuple):
        return x
    return (x,)

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


class OptionRequiredIfMissing(click.Option):
    """Option is required if the context does not have `option` set"""

    def __init__(self, *a, **k):
        try:
            option = k.pop("required_if_missing")
        except KeyError:
            raise KeyError(
                "OptionRequiredIfMissing needs the required_if_missing keyword argument"
            )

        super().__init__(*a, **k)
        self._option = option

    def process_value(self, ctx, value):
        required = not ctx.params[self._option]
        dep_value = super().process_value(ctx, value)
        if required and dep_value is None:
            msg = "Required if --{} is not provided".format(self._option)
            raise click.MissingParameter(ctx=ctx, param=self, message=msg)
        return value
