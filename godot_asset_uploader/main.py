from dataclasses import fields
from functools import wraps
import sys

import click

from . import vcs, config, rest_api
from .errors import *
from .markdown import get_asset_payload

@click.group()
def cli():
    """Automatically upload or update an asset in Godot Asset Library
based on the project repository."""
    pass

def shared_options(cmd):
    @click.option("--readme", default="README.md", help="Location of README file, relative to project root")
    @click.option("--changelog", default="CHANGELOG.md", help="Location of changelog file, relative to project root")
    @click.option("--unwrap-links/--no-unwrap-links", default=True, show_default=True,
                  help="If true, links will be converted to <http://foo.bar> form. "
                  "This is the default, since the asset library does not support any form of markup. "
                  "If false, the original syntax, as used in the source Markdown file, will be preserved. "
                  "Does not affect processing links to images and videos.")
    @click.option("--preserve-html/--no-preserve-html", default=False, show_default=True,
                  help="If true, raw HTML fragments in Markdown will be left as-is. Otherwise they will be omitted from the output.")
    @click.argument("root", default=".")
    @click.pass_context
    @wraps(cmd)
    def make_cfg_and_call(ctx, readme, changelog, root, *args, **kwargs):
        project_root = vcs.get_project_root(root)
        cfg = config.Config(
            root=project_root,
            readme=readme,
            changelog=changelog,
            **kwargs,
        )
        for field in fields(cfg):
            if field.name in kwargs:
                del kwargs[field.name]
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
    print(get_asset_payload(cfg))

@cli.command()
@click.argument("asset-id", required=True)
@click.pass_obj
def peek(cfg, asset_id):
    from pprint import pprint
    pprint(rest_api.get_asset_info(asset_id))

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
