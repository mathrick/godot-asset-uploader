from dataclasses import dataclass, field, fields, MISSING, asdict
from functools import lru_cache
from pathlib import Path
from typing import Optional, ClassVar

import tomlkit, tomlkit.toml_file
from tomlkit.exceptions import NonExistentKey

from .errors import *
from .util import is_typed_as

def toml_path_encoder(path):
    if isinstance(path, Path):
        return tomlkit.string(str(path))
    raise TypeError(path)

tomlkit.register_encoder(toml_path_encoder)

# NB: It's important that config is mutated to update it, instead of using
# dataclass.replace() or some other mechanism generating a new value, since we
# rely on the config being available all the way up to the outermost click
# context, which we actually create manually before click starts processing

class ConfigMixin:
    VOLATILE: ClassVar = []

    def __post_init__(self):
        pass

    @classmethod
    @lru_cache()
    def fields(cls):
        return {field.name: field for field in fields(cls)}

    @classmethod
    def is_required(cls, field_name):
        return cls.fields()[field_name].default is MISSING

    def set(self, field, value, validate=True):
        if field in self.fields():
            setattr(self, field, value)
            if validate:
                self.validate()
            return getattr(self, field)
        return value

    def save(self, path=None, exclude=None):
        "Save config as a TOML file under PATH. If PATH is not absolute, it will be relative to self.root"
        path = self.root / (path or self.FILE_NAME)
        out = tomlkit.toml_file.TOMLFile(path)
        doc = tomlkit.TOMLDocument()
        for line in self.FILE_COMMENT.splitlines():
            doc.add(tomlkit.comment(line))
        table = tomlkit.table()
        table.update({k: v for k, v in asdict(self).items()
                      if v is not None
                      and k not in self.VOLATILE
                      and k not in (exclude or set())})
        doc["gdasset"] = table
        out.write(doc)

    def try_load(self, path=None):
        path = self.root / (path or self.FILE_NAME)
        try:
            with Path(path).open() as file:
                toml = tomlkit.load(file)
                for field, val in toml.get("gdasset").items():
                    self.set(field, val, validate=False)
        except FileNotFoundError:
            pass

@dataclass
class Auth(ConfigMixin):
    VOLATILE: ClassVar = ["root", "password"]
    FILE_NAME: ClassVar = "gdasset-auth.toml"
    FILE_COMMENT: ClassVar = """DO NOT COMMIT THIS FILE IN YOUR VERSION CONTROL SYSTEM

These are the saved credentials used to log into Godot Asset Library.
They should not be shared or saved anywhere outside of your own machine."""
    root: Path
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None

    def validate(self):
        if not self.token and not (self.username and self.password):
            raise GdAssetError("Either a login token, or username and password must be provided.")


@dataclass
class Config(ConfigMixin):
    # These fields should not be saved by save()
    VOLATILE: ClassVar = ["version", "commit",
                          "previous_payload", "no_prompt", "quiet", "dry_run",
                          "auth"]
    FILE_NAME: ClassVar = "gdasset.toml"
    FILE_COMMENT: ClassVar = """These are default values for the project's submission to Godot Asset Library
through Godot Asset Uploader (gdasset). It is safe to track and commit this
file through your version control system."""
    root: Path
    readme: Path
    changelog: Optional[Path] = None
    plugin: Optional[Path] = None

    version: Optional[str] = None
    godot_version: Optional[str] = None
    licence: Optional[str] = None

    title: Optional[str] = None
    icon_url: Optional[str] = None
    repo_url: Optional[str] = None
    repo_provider: Optional[str] = None
    issues_url: Optional[str] = None
    download_url: Optional[str] = None
    commit: Optional[str] = None

    unwrap_links: bool = True
    preserve_html: bool = False

    previous_payload: Optional[dict] = None
    no_prompt: bool = False
    quiet: bool = False
    dry_run: bool = False

    auth: Optional[Auth] = None

    def __post_init__(self):
        self._parsed_plugin = None
        self.root = Path(self.root).absolute()
        path_fields = [f for f in fields(self)
                       if is_typed_as(f.type, Path) and f.name != "root"]
        for field in path_fields:
            val = getattr(self, field.name, None)
            if val:
                setattr(self, field.name, self.root / val)
            val = getattr(self, field.name, None)

        if self.version is None:
            self.version = self.get_plugin_key("version")
        if self.title is None:
            self.title = self.get_plugin_key("name")

    def validate(self):
        self.__post_init__()

        if not self.root.exists():
            raise GdAssetError(f"root directory '{self.root}' not found")

        path_fields = [f for f in fields(self) if is_typed_as(f.type, Path)]
        for field in path_fields:
            val = getattr(self, field.name, None)
            # This means the field is required
            if field.default is MISSING and not (val and val.exists()):
                raise GdAssetError(f"{field.name.capitalize()} file '{val}' not found")

    def get_plugin_key(self, key, default=None):
        if self._parsed_plugin is None and self.plugin:
            if not self.plugin.exists():
                raise GdAssetError(f"{self.plugin} not found")
            self._parsed_plugin = tomlkit.parse(self.plugin.read_text())
        if self._parsed_plugin is not None:
            try:
                return self._parsed_plugin.get(f"plugin", {})[key]
            except NonExistentKey as e:
                raise GdAssetError(f"Could not read {self.plugin.relative_to(self.root)}: {e.args[0]}")
            except KeyError as e:
                raise GdAssetError(f"Could not read {self.plugin.relative_to(self.root)}: Key {e.args[0]} does not exist.")
        return default


def has_config_file(path):
    return (Path(path) / Config.FILE_NAME).exists()

def has_auth_file(path):
    return (Path(path) / Auth.FILE_NAME).exists()
