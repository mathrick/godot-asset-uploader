from functools import wraps, partial
from urllib.parse import urlparse
import re

from mistletoe import Document
from mistletoe.core_tokens import MatchObj
from mistletoe.block_token import BlockToken, List, Paragraph
from mistletoe.span_token import SpanToken, AutoLink
from mistletoe.markdown_renderer import MarkdownRenderer, Fragment
from mistletoe.ast_renderer import AstRenderer

from validator_collection.checkers import is_url

from . import config
from .errors import *
from .util import is_interesting_link, normalise_video_link, is_image_link

class MetaItem(SpanToken):
    def __init__(self, matches):
        header, *attrs = matches
        tag, *value = header.split(":", 1)
        self.tag = tag.lower()
        self.value = value[0].strip() if value else None
        self.attrs = {k.lower(): v.strip()
                      for attr in attrs
                      for k, v in [attr.split(":", 1)]}

    @property
    def content(self):
        return ": ".join([self.tag] + ([self.value] if self.value is not None else []))


# Annoyingly, GFM will sometimes only embed videos if it's a bare URL without
# any markup (ie. not a regular MD link syntax, nor the CommonMark autolink,
# ie. <http://foo>). Using markup sometimes actually disables the embedding (!),
# though the results of my testing are inconsistent, and sometimes it's the
# marked up link that works. This means we really need to have what GFM calls
# extended autolinks, or otherwise using the unmodified README.md will not work
# reliably.
#
# In any event, it seems they restrict embeds exclusively to uploaded
# attachments (ie. https://github.com/user-attachments/assets/..., as well as
# *.githubusercontent.com), so that a link to an external mp4 file for example
# will not trigger an embed, no matter the syntax.
class ExtendedAutoLink(AutoLink):
    # https://github.github.com/gfm/#autolinks-extension-
    pattern = re.compile("(?:^|[\s*_~(])(http(s)?://[^\s\a\b\f\n\r\t\v<>]+)")
    entity_ref_pattern = re.compile("&[a-zA-Z0-9]+;$")
    parse_inner=False

    @classmethod
    def find(cls, string):
        candidates = []
        # Apply extended autolink path validation from GFM
        for match in cls.pattern.finditer(string):
            # Strip trailing punctuation
            cand = match.group(1).rstrip("?!.,:*_~")
            # Strip umatched closing parens
            if cand.endswith(")"):
                unmatched = sum([-1 if c == "(" else -1 for c in cand if c in "()"])
                if unmatched < 0:
                    cand = cand[:unmatched]
            # Strip potential HTML entity references
            if cand.endswith(";"):
                if (ref := cand.search(cls.entity_ref_pattern)):
                    cand = cand[:ref.start()]
            if is_url(cand):
                # Need to recreate the match object to reflect our updated candidate
                start = match.start(1)
                end = match.start(1) + len(cand)
                match = MatchObj(start, end, (start, end, cand))
                candidates.append(match)
        return candidates

class Directive(BlockToken):
    START_REGEX = re.compile("^[^<]*<!--- (.*?)( -->)?$")
    END_REGEX = re.compile("^(.*) -->")

    def __init__(self, match):
        self.children = [MetaItem(match)]

    @property
    def content(self):
        return "<!--- {} -->".format('\n'.join([c.content for c in self.children]))

    @classmethod
    def start(cls, line):
        result = cls.START_REGEX.match(line)
        return result

    @classmethod
    def read(cls, lines):
        line = next(lines)
        buf = [cls.START_REGEX.match(line).group(1)]
        if cls.END_REGEX.search(line):
            return buf
        for line in lines:
            line = line.strip()
            if (match := cls.END_REGEX.search(line)):
                if match.group(1) is not None:
                    buf.append(match.group(1))
                    break
            buf.append(line.strip())
        return buf


class Renderer(MarkdownRenderer):
    def __init__(self, config,
                 image_callback=None, link_callback=None, html_callback=None,
                 **kwargs):
        self.config = config
        self.image_callback = image_callback
        self.link_callback = link_callback
        self.html_callback = html_callback
        self.suppressed = []
        super().__init__(Directive, ExtendedAutoLink, **kwargs)

    def suppress(self, token):
        if token not in self.suppressed:
            self.suppressed.append(token)

    def unsuppress(self, token):
        if token in self.suppressed:
            self.suppressed.remove(token)

    # We need to override all render methods so we can suppress them
    # if needed
    def __getattribute__(self, name):
        base_meth = object.__getattribute__(self, name)
        if callable(base_meth) and name.startswith("render_") and name not in type(self).__dict__:
            return partial(object.__getattribute__(self, "maybe_render"), base_meth)
        return base_meth

    def maybe_render(self, method, token, *args, **kwargs):
        try:
            if not self.suppressed:
                return method(token, *args, **kwargs)
            return []
        finally:
            self.unsuppress(token)

    def delegated(callback_name):
        """Decorator to implement the common delegation logic for rendering
images, video, and HTML fragments"""
        def do_delegate(method):
            method_name = method.__name__
            @wraps(method)
            def func(self, token, max_line_length=None):
                is_block = isinstance(token, BlockToken)
                callback = getattr(self, callback_name)
                result = callback and callback(token)
                if result == True or not callback:
                    if not self.suppressed:
                        kwargs = {"max_line_length": max_line_length} if is_block else {}
                        return getattr(super(), method_name)(token, **kwargs)
                elif result is not None:
                    return result
                return [] if is_block else ""
            return func

        return do_delegate

    @delegated("image_callback")
    def render_image(self, token):
        pass

    @delegated("link_callback")
    def render_link(self, token):
        pass

    @delegated("link_callback")
    def render_auto_link(self, token):
        pass

    @delegated("link_callback")
    def render_extended_auto_link(self, token):
        pass

    @delegated("html_callback")
    def render_html_span(self, token):
        pass

    @delegated("html_callback")
    def render_html_block(self, token, max_line_length=None):
        pass

    def render_directive(self, token, max_line_length=None):
        item = token.children[0]
        if item.tag == "changelog":
            if not self.config.changelog.exists():
                raise GdAssetError(f"Changelog file {config.changelog} not found")
            with self.config.changelog.open() as changelog_file:
                changelog = None
                for child in Document(changelog_file).children:
                    if isinstance(child, List):
                        changelog = child
                        break
                else:
                    raise GdAssetError("Changelog file {config.changelog} does not contain a list")

                to_render = [Paragraph([item.attrs["heading"] + ":"])] if "heading" in item.attrs else []

                if item.value:
                    changelog.children = changelog.children[:int(item.value)]

                to_render.append(changelog)
                # Needed to set child.parent properly
                token.children = to_render
                return ["".join([self.render(x) for x in to_render])]
        if item.tag == "gdasset":
            if not item.value or item.value not in ("include", "exclude"):
                raise GdAssetError(f"The 'gdasset' directive must have a value of 'include' or 'exclude' on line {token.line_number}")
            if item.value == "exclude":
                self.suppress(token.parent)
            else:
                self.unsuppress(token.parent)
            return []

        raise GdAssetError(f"Unsupported directive: '{item.tag}'")


def get_asset_description(cfg: config.Config):
    "Return description (str) and previews (list of dicts) for the asset"
    description = None
    previews = []

    def process_image(token):
        previews.append({"type": "image", "link": token.src})

    def process_link(token):
        print("got link", token.target)
        uri = urlparse(token.target)
        if not is_interesting_link(token.target):
            pass
        elif (href := normalise_video_link(token.target)):
            previews.append({"type": "video", "link": href})
            return None
        elif is_image_link(token.target):
            previews.append({"type": "image", "link": token.target})
            return None
        # All links will be converted to autolink syntax, since the asset
        # library doesn't support any form of markup whatsoever
        if cfg.unwrap_links:
            return [Fragment(f"{token.target}")]
        else:
            return True

    def process_html(token):
        return True if cfg.preserve_html else None

    with open(cfg.readme) as input:
        with Renderer(cfg,
                      image_callback=process_image,
                      link_callback=process_link,
                      html_callback=process_html,
                      max_line_length=None) as renderer:
            description = renderer.render(Document(input))

    return (description, previews)
