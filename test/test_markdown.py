import pytest
import yaml

from godot_asset_uploader.config import Config
from godot_asset_uploader.markdown import (
    get_asset_description
)


@pytest.fixture(autouse=True)
def hack_pyyaml_multiline_strings():
    # This is a pretty ugly hack, but it's needed to make PyYAML use
    # "literal style block scalars", ie. the readable representation
    # of multiline strings.
    # Copied mostly from https://stackoverflow.com/a/15423007/339482
    def represent(self, tag, value, style=None):
        style = "|" if "\n" in value else style
        node = yaml.representer.ScalarNode(tag, value, style=style)
        if self.alias_key is not None:
            self.represented_objects[self.alias_key] = node
        return node

    old_represent = yaml.representer.BaseRepresenter.represent_scalar
    yaml.representer.BaseRepresenter.represent_scalar = represent
    yield
    yaml.representer.BaseRepresenter.represent_scalar = old_represent


@pytest.mark.parametrize("changelog", [
    "CHANGELOG-long.md",
    "CHANGELOG-short.md",
])
@pytest.mark.parametrize("readme", [
    "README-trivial.md",
    "README-with-changelog.md",
])
def test_get_asset_description(data_regression, datadir, readme, changelog):
    cfg = Config(root=datadir, readme=readme, changelog=changelog)
    description, previews = get_asset_description(cfg)
    data_regression.check({
        "description": description,
        "previews": previews,
    })
