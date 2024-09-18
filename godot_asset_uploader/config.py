from dataclasses import dataclass, field, fields, MISSING
from pathlib import Path
from typing import Optional

from .errors import *
from .util import is_typed_as

@dataclass
class Config:
    root: Path
    readme: Path
    changelog: Optional[Path] = None

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

def has_config_file(path):
    return (Path(path) / "gdasset.ini").exists()
