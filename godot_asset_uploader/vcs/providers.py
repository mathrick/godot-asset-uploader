from enum import Enum

import giturlparse
from yarl import URL


class StrEnum(str, Enum):
    @classmethod
    def _missing_(cls, value):
        value = value.upper()
        for member in cls:
            if member.name == value:
                return member
        return None

    def __new__(cls, name, normalised=None):
        member = str.__new__(cls, name)
        member._value_ = name
        member.normalised = (normalised or name)
        return member


class RepoProvider(StrEnum):
    CUSTOM = "Custom"
    GITHUB = "GitHub"
    GITLAB = "GitLab"
    BITBUCKET = "BitBucket"
    HEPTAPOD = "Heptapod", "GitLab"


def remote_to_https(url):
    "Normalise remote URL so that it's always a https:// URL, if it's a known provider"
    parsed = giturlparse.parse(url or "")
    url = parsed.valid and parsed.url2https
    # Annoyingly, giturlparse always adds .git, so now we have to get rid of it
    url = url and str(URL(url).with_suffix(""))
    return url if parsed.valid else None
