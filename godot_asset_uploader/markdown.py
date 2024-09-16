import re

from mistletoe import Document
from mistletoe.block_token import BlockToken
from mistletoe.span_token import SpanToken
from mistletoe.markdown_renderer import MarkdownRenderer
from mistletoe.ast_renderer import AstRenderer

class MetaItem(SpanToken):
    def __init__(self, match):
        self.tag, *value = match.split(":", 1)
        self.value = value[0].lstrip() if value else None
            
    @property
    def content(self):
        return ": ".join([self.tag] + ([self.value] if self.value is not None else []))


class MetaComment(BlockToken):
    START_REGEX = re.compile("^[^<]*<!--- (.*) (-->)?")
    END_REGEX = re.compile("^(.*) -->")

    def __init__(self, match):
        self.children = [MetaItem(m) for m in match]
    
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


class Renderer(AstRenderer):
    def __init__(self, config, **kwargs):
        self.config = config
        super().__init__(MetaComment, **kwargs)

    def render_meta_comment(self, token, max_line_length=None):
        if token.tag == "changelog":
            
        return [f"!!! {token.content} !!!"]
