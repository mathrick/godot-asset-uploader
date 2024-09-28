from dataclasses import fields
from functools import wraps
import sys

import click

from . import vcs, config, rest_api
from .errors import *
from .markdown import get_asset_description
from .util import option, OptionRequiredIfMissing

CMD_EPILOGUE = """Most parameters can be inferred from the project repository,
README.md, plugin.cfg, and the existing library asset (when performing
an update). Missing information will be prompted for interactively,
unless the '--non-interactive / '-N' flag was passed."""

@click.group()
def cli():
    """Automatically upload or update an asset in Godot Asset Library
based on the project repository."""
    pass

# NOTE: ctx.obj is set to project root during command processing, and config afterwards
def process_root(ctx, _, path):
    ctx.obj = vcs.get_project_root(path)
    return ctx.obj

@click.pass_obj
def default_repo_provider(project_root):
    return vcs.guess_repo_provider(project_root)

@click.pass_obj
def default_repo_url(project_root):
    return vcs.guess_repo_url(project_root)

@click.pass_obj
def default_commit(project_root):
    return vcs.guess_commit(project_root)

def shared_options(cmd):
    @option("--readme", default="README.md", metavar="PATH", show_default=True,
            help="Location of README file, relative to project root")
    @option("--changelog", default="CHANGELOG.md", metavar="PATH", show_default=True,
            help="Location of changelog file, relative to project root")
    @option("--plugin", metavar="PATH",
            help="If specified, should be the path to a plugin.cfg file, "
            "which will be used to auto-populate project info")
    @option("--version", required_if_missing="plugin",
            help="Asset version. Required unless --plugin is provided", cls=OptionRequiredIfMissing)
    @option("--godot-version", required_if_missing="url",
            help="Minimum Godot version asset is compatible with. "
            "Required unless update URL is provided", cls=OptionRequiredIfMissing)
    @option("--licence", required_if_missing="url",
            help="Asset's licence. Required unless update URL is provided", cls=OptionRequiredIfMissing)
    @option("--title", required_if_missing=["plugin", "url"],
            help="Title / short description of the asset. "
            "Required unless --plugin or update URL is provided", cls=OptionRequiredIfMissing)
    @option("--icon-url", required_if_missing="url", help="Icon URL", cls=OptionRequiredIfMissing)
    @option("--repo-url", required_if_missing="url", default=default_repo_url,
            help="Repository URL. Will be inferred from repo remote if possible.", cls=OptionRequiredIfMissing)
    @option("--repo-provider", required_if_missing="url",
            type=click.Choice([x.name.lower() for x in rest_api.RepoProvider], case_sensitive=False),
            default=default_repo_provider,
            help="Repository provider. Will be inferred from repo remote if possible.", cls=OptionRequiredIfMissing)
    @option("--commit", required_if_missing="url", default=default_commit,
            help="Commit ID to upload. Will be inferred from current repo if possible.", cls=OptionRequiredIfMissing)
    @option("--unwrap-links/--no-unwrap-links", default=True, show_default=True,
            help="If true, all Markdown links will be converted to plain URLs. "
            "This is the default, since the asset library does not support any form of markup. "
            "If false, the original syntax, as used in the source Markdown file, will be preserved. "
            "Does not affect processing links to images and videos.")
    @option("--preserve-html/--no-preserve-html", default=False, show_default=True,
            help="If true, raw HTML fragments in Markdown will be left as-is. Otherwise they will be omitted from the output.")
    @click.argument("root", default=".", is_eager=True, callback=process_root)
    @click.pass_context
    @wraps(cmd)
    def make_cfg_and_call(ctx, root, *args, **kwargs):
        project_root = ctx.obj
        cfg_kwargs = {field.name: kwargs.pop(field.name)
                      for field in fields(config.Config) if field.name in kwargs}
        cfg = config.Config(
            root=project_root,
            **cfg_kwargs,
        )
        ctx.obj = cfg
        ctx.invoke(cmd, *args, **kwargs)

    return make_cfg_and_call

def get_asset_payload(cfg: config.Config):
    """Based on CFG, get the payload dict for the asset suitable for posting to the
asset library. The payload generated might not be complete, and might need to be
merged with another dict to provide missing values (this is the case for updates)"""
    description, previews = get_asset_description(cfg)
    return {
        "title": cfg.title,
        "description": description,
        "godot_version": "2.1",
        "version_string": cfg.version,
        "cost": cfg.licence,
        "download_provider": cfg.repo_provider,
        "download_commit": cfg.commit,
        "browse_url": cfg.repo_url,
        # "issues_url": cfg.xxx,
        "icon_url": cfg.icon_url,
        "download_url": "https://github.com/…/archive/master.zip",
        "previews": previews,
    }

@cli.command(epilog=CMD_EPILOGUE)
@shared_options
@click.pass_obj
def upload(cfg):
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

@cli.command()
@click.argument("username", required=True)
@click.option("--password", required=True, prompt=True, hide_input=True, show_default=True,
              help="Password to log in with. Will be prompted if not provided")
@click.pass_obj
def login(cfg, username, password):
    from pprint import pprint
    pprint(rest_api.login(username, password))

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
