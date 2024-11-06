from enum import Enum


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
