from dataclasses import dataclass, field
from pathlib import Path

from typing import Optional


@dataclass
class Config:
    readme: Path
    changelog: Optional[Path]


def has_config_file(path):
    return (Path(path) / "gdasset.ini").exists()
