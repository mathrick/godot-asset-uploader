import re

from mistletoe import Document
from mistletoe.block_token import BlockToken, List, Paragraph
from mistletoe.span_token import SpanToken
from mistletoe.markdown_renderer import MarkdownRenderer
from mistletoe.ast_renderer import AstRenderer

from . import errors as err

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


class MetaComment(BlockToken):
    START_REGEX = re.compile("^[^<]*<!--- (.*)( -->)?")
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
    def __init__(self, config, **kwargs):
        self.config = config
        self.suppress = []
        super().__init__(MetaComment, **kwargs)

    def render(self, token):
        result = ""
        try:
            if not self.suppress:
                return super().render(token)
        finally:
            if token in self.suppress:
                self.suppress.remove(token)

    def render_meta_comment(self, token, max_line_length=None):
        return [self.render_meta_item(c) for c in token.children]

    def render_meta_item(self, token, max_line_length=None):
        if token.tag == "changelog":
            if not self.config.changelog.exists():
                raise err.GdAssetError(f"Changelog file {config.changelog} not found")
            with self.config.changelog.open() as changelog_file:
                changelog = None
                for child in Document(changelog_file).children:
                    if isinstance(child, List):
                        changelog = child
                        break
                else:
                    raise GdAssetError("Changelog file {config.changelog} does not contain a list")

                to_render = [Paragraph([token.attrs["heading"] + ":"])] if "heading" in token.attrs else []

                if token.value:
                    changelog.children = changelog.children[:int(token.value)]

                to_render.append(changelog)
                token.parent.children = to_render
                return "".join([self.render(x) for x in to_render])

        raise err.GdAssetError(f"Unsupported metadata type: '{token.tag}'")
