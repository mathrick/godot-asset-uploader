from contextlib import nullcontext
import pytest

import yaml
from yarl import URL

from godot_asset_uploader.errors import NoImplementationError
from godot_asset_uploader.config import Config
from godot_asset_uploader import vcs
from godot_asset_uploader.markdown import (
    get_asset_description
)

@pytest.fixture(autouse=True)
def hack_pyyaml_multiline_strings():
    # This is a pretty ugly hack, but it's needed to make PyYAML use
    # "literal style block scalars", ie. the readable representation
    # of multiline strings.
    # Copied mostly from https://stackoverflow.com/a/15423007/339482
    def represent_scalar(self, tag, value, style=None):
        style = "|" if "\n" in value else style
        node = yaml.representer.ScalarNode(tag, value, style=style)
        if self.alias_key is not None:
            self.represented_objects[self.alias_key] = node
        return node

    old_represent_scalar = yaml.representer.BaseRepresenter.represent_scalar
    yaml.representer.BaseRepresenter.represent_scalar = represent_scalar
    yield
    yaml.representer.BaseRepresenter.represent_scalar = old_represent_scalar

@pytest.mark.parametrize("changelog", [
    "CHANGELOG-long.md",
    "CHANGELOG-short.md",
])
@pytest.mark.parametrize("readme", [
    "README-trivial.md",
    "README-with-changelog.md",
])
@pytest.mark.parametrize("repo_url", [
    "https://github.com/dummy-user/dummy-repo",
    "https://dummy-user@bitbucket.org/dummy-user/dummy-repo",
    "https://gitlab.com/dummy-user/dummy-repo",
    "https://gitlab.self-hosted.com/dummy-user/dummy-repo",
])
@pytest.mark.parametrize("path_offset", [
    None,
    "",
    "docs",
    "docs/lib/foo",
])
def test_get_asset_description(request, data_regression, datadir, readme, changelog, repo_url, path_offset):
    cfg = Config(root=datadir, readme=readme, changelog=changelog)

    def prep_image_url(url):
        if not URL(url).absolute:
            return vcs.resolve_with_base_content_url(
                repo_url, "12345deadbeef7890", url, path_offset=path_offset
            )
        return url

    def prep_link_url(url):
        if not URL(url).absolute:
            return vcs.resolve_with_base_url(repo_url, url, cfg.commit)
        return url

    raises = pytest.raises(NoImplementationError) if (
        "bitbucket.org" in repo_url and "trivial" not in readme
    ) else nullcontext()

    description, previews = None, None
    with raises:
        description, previews = get_asset_description(
            cfg, prep_image_func=prep_image_url, prep_link_func=prep_link_url
        )

    data_regression.check({
        # Record execution params for easier inspection
        "PARAMS": {k: v for k, v in locals().items() if k in request.node.callspec.params},
        "description": description,
        "previews": previews,
    })
