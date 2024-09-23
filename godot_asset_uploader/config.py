from dataclasses import dataclass, field, fields, MISSING
from pathlib import Path
from typing import Optional

import tomlkit
from tomlkit.exceptions import NonExistentKey

from .errors import *
from .util import is_typed_as

@dataclass
class Config:
    root: Path
    readme: Path
    changelog: Optional[Path] = None
    plugin: Optional[Path] = None
    version: Optional[str] = None
    title: Optional[str] = None

    repo_provider: Optional[str] = None

    unwrap_links: bool = True
    preserve_html: bool = False

    def __post_init__(self):
        self.root = self.root.absolute()
        path_fields = [f for f in fields(self)
                      if is_typed_as(f.type, Path) and f.name != "root"]
        for field in path_fields:
            val = getattr(self, field.name, None)
            if val:
                setattr(self, field.name, self.root / val)
            val = getattr(self, field.name, None)
            # This means the field is required
            if field.default is MISSING and not (val and val.exists()):
                raise GdAssetError(f"{field.name.capitalize()} file '{val}' not found")

        if self.plugin:
            ini = tomlkit.parse(self.plugin.read_text())
            try:
                if self.version is None:
                    self.version = ini.get("plugin", {})["version"]
                if self.title is None:
                    self.title = ini.get("plugin", {})["name"]
            except NonExistentKey as e:
                raise GdAssetError(f"Could not read {self.plugin.relative_to(self.root)}: {e.args[0]}")
            except KeyError as e:
                raise GdAssetError(f"Could not read {self.plugin.relative_to(self.root)}: Key {e.args[0]} does not exist.")


def has_config_file(path):
    return (Path(path) / "gdasset.ini").exists()
