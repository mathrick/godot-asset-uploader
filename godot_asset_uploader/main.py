import dataclasses
from functools import wraps
from inspect import signature
from pathlib import Path
import sys

import click

from . import vcs, config, rest_api
from .errors import *
from .markdown import get_asset_description
from .util import (OptionRequiredIfMissing, PriorityProcessingCommand,
                   readable_param_name, is_default_param)

CMD_EPILOGUE = """Most parameters can be inferred from the project repository,
README.md, plugin.cfg, and the existing library asset (when performing
an update). Missing information will be prompted for interactively,
unless the '--non-interactive / '-N' flag was passed."""

@click.group()
def cli():
    """Automatically upload or update an asset in Godot Asset Library
based on the project repository."""
    pass

def ensure_path_param(ctx, param, value):
    if not value:
        return
    root = getattr(ctx.obj, "root", None)
    path = root / value if root is not None else Path(value)
    required = param.required or ctx.obj.is_required(param.name) or not is_default_param(ctx, param.name)
    if required and not path.exists():
        raise GdAssetError(f"{readable_param_name(param)}: file '{path}' not found")
    return value

def process_root(ctx, param, path):
    ctx.obj = config.Config(
        root=vcs.get_project_root(path),
        # Fake value, since readme is required
        readme="."
    ).try_load()
    ensure_path_param(ctx, param, path)
    return ctx.obj.root

def process_path_param(ctx, param, path):
    ensure_path_param(ctx, param, path)
    ctx.obj = dataclasses.replace(ctx.obj, **{param.name: path})
    return ctx.obj.plugin

# Generic process callback to update config
def process_param(ctx, param, value):
    cfg_kwargs = {field.name for field in dataclasses.fields(config.Config)}
    if param.name in cfg_kwargs:
        ctx.obj = dataclasses.replace(ctx.obj, **{param.name: value})
    return getattr(ctx.obj, param.name)

@click.pass_obj
def default_repo_provider(cfg):
    return cfg.repo_provider or vcs.guess_repo_provider(cfg.repo_url)

@click.pass_obj
def default_repo_url(cfg):
    return cfg.repo_url or vcs.guess_repo_url(cfg.root)

@click.pass_obj
def default_issues_url(cfg):
    return cfg.issues_url or vcs.guess_issues_url(cfg.repo_url)

@click.pass_obj
def default_download_url(cfg):
    # NOTE: here we default to guessing rather than saved values, since this
    # value will usually differ from commit to commit
    return vcs.guess_download_url(cfg.repo_url, cfg.commit) or cfg.download_url

@click.pass_obj
def default_commit(cfg):
    return vcs.guess_commit(cfg.root)

def default_from_plugin(key):
    @click.pass_obj
    def default_value(cfg):
        return getattr(cfg, key, cfg.get_plugin_key(key))

    return default_value

def saved_default(key):
    @click.pass_obj
    def default_value(cfg):
        return getattr(cfg, key, None)

    return default_value

def option(*args, **kwargs):
    kw = {"callback": process_param}
    if any(kwargs.get(k) for k in ["required", "required_if_missing"]):
        kw.update({"prompt": True})
    kw.update(kwargs)
    # This is the easiest way of robustly getting the name of the option that I
    # can think of, even if it's a bit inelegant
    opt_class = kw.pop("cls", click.Option)
    opt = opt_class(args, **kw)
    kw.setdefault("default", saved_default(opt.name))
    return click.option(*args, **kw, cls=opt_class)

def shared_options(cmd):
    @option("--readme", default="README.md", metavar="PATH",
            show_default=True, callback=process_path_param,
            help="Location of README file, relative to project root")
    @option("--changelog", default="CHANGELOG.md", metavar="PATH",
            show_default=True, callback=process_path_param,
            help="Location of changelog file, relative to project root")
    @option("--plugin", metavar="PATH", callback=process_path_param, is_eager=True,
            help="If specified, should be the path to a plugin.cfg file, "
            "which will be used to auto-populate project info")
    @option("--version", required_if_missing="plugin", default=default_from_plugin("version"),
            help="Asset version. Required unless --plugin is provided", cls=OptionRequiredIfMissing)
    @option("--godot-version", required_if_missing="url",
            help="Minimum Godot version asset is compatible with. "
            "Required unless update URL is provided", cls=OptionRequiredIfMissing)
    @option("--licence", required_if_missing="url",
            help="Asset's licence. Required unless update URL is provided", cls=OptionRequiredIfMissing)
    @option("--title", required_if_missing=["plugin", "url"], default=default_from_plugin("name"),
            help="Title / short description of the asset. "
            "Required unless --plugin or update URL is provided", cls=OptionRequiredIfMissing)
    @option("--icon-url", required_if_missing="url", help="Icon URL", cls=OptionRequiredIfMissing)
    @option("--repo-url", required_if_missing="url", default=default_repo_url,
            help="Repository URL. Will be inferred from repo remote if possible.", cls=OptionRequiredIfMissing)
    @option("--repo-provider", required_if_missing="url",
            type=click.Choice([x.name.lower() for x in rest_api.RepoProvider], case_sensitive=False),
            default=default_repo_provider,
            help="Repository provider. Will be inferred from repo remote if possible.", cls=OptionRequiredIfMissing)
    @option("--issues-url", required_if_missing="url", default=default_issues_url,
            help="URL for reporting issues. Will be inferred from repository URL possible.", cls=OptionRequiredIfMissing)
    @option("--commit", required=True, default=default_commit,
            help="Commit ID to upload. Will be inferred from current repo if possible.")
    @option("--download-url", required_if_missing="url", default=default_download_url,
            help="Download URL for asset's main ZIP. Will be inferred from repository URL possible.", cls=OptionRequiredIfMissing)
    @option("--unwrap-links/--no-unwrap-links", default=True, show_default=True,
            help="If true, all Markdown links will be converted to plain URLs. "
            "This is the default, since the asset library does not support any form of markup. "
            "If false, the original syntax, as used in the source Markdown file, will be preserved. "
            "Does not affect processing links to images and videos.")
    @option("--preserve-html/--no-preserve-html", default=False, show_default=True,
            help="If true, raw HTML fragments in Markdown will be left as-is. Otherwise they will be omitted from the output.")
    @option("--save/--no-save", default=True, show_default=True, prompt="Save these answers as defaults?",
            help="If true, config will be saved as gdasset.toml in the project root.")
    @click.argument("root", default=".", is_eager=True, callback=process_root)
    @click.pass_context
    @wraps(cmd)
    def make_cfg_and_call(ctx, root, *args, **kwargs):
        ctx.obj.validate()
        cfg_kwargs = {field.name for field in dataclasses.fields(config.Config)}
        cmd_kwargs = set(signature(cmd).parameters)
        for kw in cfg_kwargs - cmd_kwargs:
            kwargs.pop(kw, None)
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
        "godot_version": cfg.godot_version,
        "version_string": cfg.version,
        "cost": cfg.licence,
        "download_provider": cfg.repo_provider,
        "download_commit": cfg.commit,
        "browse_url": cfg.repo_url,
        "issues_url": cfg.issues_url,
        "icon_url": cfg.icon_url,
        "download_url": cfg.download_url,
        "previews": previews,
    }


class UploadCommand(PriorityProcessingCommand):
    PRIORITY_LIST = ["root", "plugin", "repo_url"]

@shared_options
@cli.command(epilog=CMD_EPILOGUE, cls=UploadCommand)
@click.pass_context
def upload(ctx, save):
    """Upload a new asset to the library.

ROOT should be the root of the project, meaning a directory containing
the file 'gdasset.toml', or a VCS repository (currently, only Git is
supported). If not specified, it will be determined automatically,
starting at the current directory."""
    cfg = ctx.obj
    description, previews = get_asset_description(cfg)
    print(description)
    from pprint import pp
    pp(cfg.commit)
    if save:
        excluded = {param for param in ctx.params
                          if is_default_param(ctx, param)}
        cfg.save(exclude={param for param in ctx.params
                          if is_default_param(ctx, param)})


def process_update_url(ctx, _, url):
    if url is not None:
        return rest_api.get_asset_info(url)
    return {}

class UpdateCommand(PriorityProcessingCommand):
    PRIORITY_LIST = ["root", "url"]

@cli.command(cls=UpdateCommand)
@click.argument("previous_payload", metavar="URL", required=True, callback=process_update_url)
@shared_options
@click.pass_obj
def update(cfg, previous_payload, save):
    """Update an existing asset in the library.

ROOT has the same meaning as for 'upload'. URL should either be the full URL to
an asset in the library, or its ID (such as '3133'), which will be looked up."""
    from pprint import pp
    pp(rest_api.merge_asset_payload(get_asset_payload(cfg), previous_payload))

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
