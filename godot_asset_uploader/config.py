from dataclasses import dataclass, field, fields, MISSING, asdict, replace
from functools import lru_cache
from pathlib import Path
from typing import Optional, ClassVar

import tomlkit, tomlkit.toml_file
from tomlkit.exceptions import NonExistentKey

from .errors import *
from .util import is_typed_as

CONFIG_FILE_NAME = "gdasset.toml"
CONFIG_FILE_COMMENT = """These are default values for the project's submission to Godot Asset Library
through Godot Asset Uploader (gdasset). It is safe to track and commit this
file through your version control system."""

def toml_path_encoder(path):
    if isinstance(path, Path):
        return tomlkit.string(str(path))
    raise TypeError(path)

tomlkit.register_encoder(toml_path_encoder)

@dataclass
class Config:
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

    # These fields should not be saved by save()
    VOLATILE: ClassVar = ["version", "commit", "previous_payload", "no_prompt", "quiet", "dry_run"]

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
        path_fields = [f for f in fields(self)
                       if is_typed_as(f.type, Path) and f.name != "root"]
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

    def save(self, path=None, exclude=None):
        "Save config as a TOML file under PATH. If PATH is not absolute, it will be relative to self.root"
        path = self.root / (path or CONFIG_FILE_NAME)
        out = tomlkit.toml_file.TOMLFile(path)
        doc = tomlkit.TOMLDocument()
        for line in CONFIG_FILE_COMMENT.splitlines():
            doc.add(tomlkit.comment(line))
        table = tomlkit.table()
        table.update({k: v for k, v in asdict(self).items()
                      if k not in self.VOLATILE and k not in (exclude or set())})
        doc["gdasset"] = table
        out.write(doc)

    def try_load(self, path=None):
        path = self.root / (path or CONFIG_FILE_NAME)
        try:
            with Path(path).open() as file:
                toml = tomlkit.load(file)
                return replace(self, **toml.get("gdasset").unwrap())
        except FileNotFoundError:
            return self

    @classmethod
    @lru_cache()
    def fields(cls):
        return {field.name: field for field in fields(cls)}

    @classmethod
    def is_required(cls, field_name):
        return cls.fields()[field_name].default is MISSING

def has_config_file(path):
    return (Path(path) / CONFIG_FILE_NAME).exists()
