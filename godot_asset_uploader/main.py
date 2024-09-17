from functools import wraps
import sys

import click

from . import vcs, config
from .errors import *
from .markdown import Renderer, Document

@click.group()
def cli():
    """Automatically upload or update an asset in Godot Asset Library
based on the project repository."""
    pass

def shared_options(cmd):
    @click.option("--readme", default="README.md", help="Location of README file, relative to project root")
    @click.option("--changelog", default="CHANGELOG.md", help="Location of changelog file, relative to project root")
    @click.argument("root", default=".")
    @click.pass_context
    @wraps(cmd)
    def make_cfg_and_call(ctx, readme, changelog, root, *args, **kwargs):
        project_root = vcs.get_project_root(root)
        cfg = config.Config(
            readme=project_root / readme,
            changelog=changelog and project_root / changelog
        )
        if not cfg.readme.exists():
            raise GdAssetError(f"Readme file '{cfg.readme}' not found")
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
    with open(cfg.readme) as input:
        with Renderer(cfg, max_line_length=None) as renderer:
            rendered = renderer.render(Document(input))
            print(rendered)


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
