import email
from enum import Enum
from functools import lru_cache
from urllib.parse import urlparse, parse_qs, urlencode
import os
from pathlib import Path
import typing as t
import shutil
import sys, pdb, traceback

import click, cloup
from click.core import ParameterSource

class StrEnum(str, Enum):
    pass

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".ogv", ".ogg")
IMAGE_EXTS = (".jpg", ".png", ".webp", ".gif")

YOUTUBE_URL = "https://youtube.com/watch?v={id}"
YOUTUBE_DOMAINS = ("youtube.com", "youtube-nocookie.com")

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
        if any(uri.netloc.endswith(domain) for domain in YOUTUBE_DOMAINS):
            if path == "oembed":
                return normalise_youtube_link(qs["url"][0]) if "url" in qs else None
            if path in ("watch", "embed"):
                return YOUTUBE_URL.format(id=qs["v"][0]) if "v" in qs else None
            if any(path.startswith(f"{x}/") for x in ["watch", "embed", "v", "e", "live", "shorts"]):
                return YOUTUBE_URL.format(id=path.split("/")[-1])
        # Special case: youtube accepts URLs of the form http://youtu.be/{id}&feature=channel,
        # which don't have a ? to mark the query string. But it also accepts
        # ones with proper ? present.
        if uri.netloc.endswith("youtu.be"):
            return normalise_youtube_link(YOUTUBE_URL.format(id="&".join([path, urlencode(qs, doseq=True)])))
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

def terminal_width():
    return shutil.get_terminal_size().columns

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

def unexpanduser(path):
    path = Path(path)
    if path.is_relative_to(Path.home()):
        return "~" / path.relative_to(Path.home())

def is_sequence(x):
    return isinstance(x, t.Sequence) and not isinstance(x, (bytes, str))

def ensure_tuple(x):
    if isinstance(x, tuple):
        return x
    return (x,)

def ensure_sequence(x):
    return x if is_sequence(x) else (x,)

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

def readable_param_name(param):
    prefix = "" if param.param_type_name == "argument" else "--"
    return f"'{prefix}{param.human_readable_name}'"

def is_default_param(ctx, param):
    return ctx.get_parameter_source(param) in [
        ParameterSource.DEFAULT,
        ParameterSource.DEFAULT_MAP,
    ]


class DynamicPromptOption(cloup.Option):
    "Allow disabling prompting through command-line switch"
    def prompt_for_value(self, ctx):
        assert self.prompt is not None
        if ctx.obj.no_prompt:
            return self.get_default(ctx)
        else:
            return super().prompt_for_value(ctx)


class OptionRequiredIfMissing(DynamicPromptOption):
    """Dependent option which is required if the context does not have
specified option(s) set"""

    def __init__(self, *args, **kwargs):
        try:
            options = ensure_sequence(kwargs.pop("required_if_missing"))
        except KeyError:
            raise KeyError(
                "OptionRequiredIfMissing needs the required_if_missing keyword argument"
            )

        super().__init__(*args, **kwargs)
        self._options = options

    def process_value(self, ctx, value):
        required = not any(ctx.params.get(opt) for opt in self._options)
        dep_value = super().process_value(ctx, value)
        if required and dep_value is None:
            opt_names = [readable_param_name(p) for p in ctx.command.params
                         if p.name in self._options]
            # opt_names might be empty, e.g. if the only option is 'url' and
            # it's not taken by the currently processed command
            msg = f"Required unless one of {', '.join(opt_names)} is provided" if opt_names else None
            raise click.MissingParameter(ctx=ctx, param=self, message=msg)
        return value


class PriorityOptionParser(click.OptionParser):
    """Order of proessing and grabbing defaults for options is very important for
the UI, since a lot of things depend on previous values. This allows us to
ensure the order is correct and preserved, no matter how the user invokes us"""
    def __init__(self, ctx, priority_list, priority_adjustments=None):
        self.order = list(ctx.command.params)
        all_params = {p.name: p for p in self.order}
        priority_adjustments = [[all_params[name] for name in adjustment if name in all_params]
                                for adjustment in priority_adjustments or []]
        for adjustment in priority_adjustments:
            # We're trying to nudge the order just enough to satisfy the
            # ordering in the current adjustment without affecting other
            # elements. To do this, we create the list of *current* indexes of
            # the relevant params in ctx.params, then sort it. Then we insert
            # each param in turn in the given spot in the list
            indexes = [self.order.index(p) for p in adjustment]
            for param, slot in zip(adjustment, sorted(indexes)):
                self.order[slot] = param
        # Finally, things in priority list just go into the front unconditionally
        self.order = [
            all_params[param] for param in priority_list if param in all_params
        ] + [p for p in self.order if p.name not in priority_list]
        super().__init__(ctx)

    def parse_args(self, args):
        opts, args, order = super().parse_args(args)
        return (opts, args, self.order)


class PriorityProcessingCommand(cloup.Command):
    PRIORITY_LIST = []
    PRIORITY_ADJUSTMENTS = []

    def make_parser(self, ctx):
        parser = PriorityOptionParser(ctx, self.PRIORITY_LIST, self.PRIORITY_ADJUSTMENTS)
        for param in self.get_params(ctx):
            param.add_to_parser(parser, ctx)
        return parser
