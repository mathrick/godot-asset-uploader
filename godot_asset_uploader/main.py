from dataclasses import fields
from functools import wraps
import sys

import click

from . import vcs, config, rest_api
from .errors import *
from .markdown import get_asset_description
from .util import option, OptionRequiredIfMissing

@click.group()
def cli():
    """Automatically upload or update an asset in Godot Asset Library
based on the project repository."""
    pass

def shared_options(cmd):
    @option("--readme", default="README.md",
            help="Location of README file, relative to project root")
    @option("--changelog", default="CHANGELOG.md",
            help="Location of changelog file, relative to project root")
    @option("--plugin",
            help="If specified, should be the path to a plugin.cfg file, "
            "which will be used to auto-populate project info")
    @option("--version", required_if_missing="plugin",
            help="Asset version. Required unless --plugin is provided", cls=OptionRequiredIfMissing)
    @option("--title", required_if_missing=["plugin", "url"],
            help="Title / short description of the asset. "
            "Required unless --plugin or update URL is provided", cls=OptionRequiredIfMissing)
    @option("--licence", required_if_missing="url",
            help="Asset's licence. Required unless update URL is provided", cls=OptionRequiredIfMissing)
    @option("--unwrap-links/--no-unwrap-links", default=True, show_default=True,
            help="If true, all Markdown links will be converted to plain URLs. "
            "This is the default, since the asset library does not support any form of markup. "
            "If false, the original syntax, as used in the source Markdown file, will be preserved. "
            "Does not affect processing links to images and videos.")
    @option("--preserve-html/--no-preserve-html", default=False, show_default=True,
            help="If true, raw HTML fragments in Markdown will be left as-is. Otherwise they will be omitted from the output.")
    @click.argument("root", default=".")
    @click.pass_context
    @wraps(cmd)
    def make_cfg_and_call(ctx, root, *args, **kwargs):
        project_root = vcs.get_project_root(root)
        cfg_kwargs = {field.name: kwargs.pop(field.name)
                      for field in fields(config.Config) if field.name in kwargs}
        cfg = config.Config(
            root=project_root,
            **cfg_kwargs,
        )
        ctx.obj = cfg
        ctx.invoke(cmd, *args, **kwargs)

    return make_cfg_and_call
        
@cli.command()
@shared_options
@click.pass_obj
def test(cfg):
    """Test command

ROOT should be the root of the project, meaning a directory containing
the file 'gdasset.ini', or a VCS repository (currently, only Git is
supported). If not specified, it will be determined automatically,
starting at the current directory."""
    description, previews = get_asset_description(cfg)
    print(description)
    from pprint import pp
    pp(previews)

@cli.command()
@click.argument("url", required=True)
@click.pass_obj
def peek(cfg, url):
    from pprint import pprint
    pprint(rest_api.get_asset_info(url))

def die(msg, code=1):
    print("ERROR:", msg, file=sys.stdout)
    sys.exit(code)

def safe_cli():
    try:
        cli()
    except GdAssetError as e:
        die(str(e))

if __name__ == "__main__":
    cli()
