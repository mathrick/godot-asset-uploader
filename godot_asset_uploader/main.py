import dataclasses
from functools import wraps
from inspect import signature
from io import StringIO
import sys

import click, cloup
from cloup.formatting import sep, HelpFormatter
from cloup.constraints import If, require_any, require_all, IsSet
from yarl import URL

from . import vcs, config, rest_api
from .errors import *
from .markdown import get_asset_description
from .util import dict_merge, terminal_width, debug_on_error
from .cli import (
    OptionRequiredIfMissing, DynamicPromptOption, PriorityProcessingCommand,
    RequireNamed,
    readable_param_name, is_default_param,
)

CMD_EPILOGUE = """Most parameters can be inferred from the project repository,
README.md, plugin.cfg, and the existing library asset (when performing
an update). Missing information will be prompted for interactively,
unless the '--assume-yes' or '-Y' flag was passed."""

CONTEXT_SETTINGS = cloup.Context.settings(
    align_option_groups=True,
    formatter_settings=HelpFormatter.settings(
        col1_max_width=20,
        row_sep=sep.RowSepIf(sep.multiline_rows_are_at_least(0.5)),
    ),
)

@cloup.group(context_settings=CONTEXT_SETTINGS)
def cli():
    """Automatically upload or update an asset in Godot Asset Library
based on the project repository."""
    pass

def process_repo_provider(ctx, param, provider):
    return ctx.obj.set("repo_provider", vcs.RepoProvider(provider.upper()))

def process_root(ctx, param, value):
    val = process_param(ctx, param, value)
    ctx.obj.try_load()

# Generic process callback to update config
def process_param(ctx, param, value):
    return ctx.obj.set(param.name, value)

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

def default_from_plugin(key, cfg_key=None):
    "Get default value from config if present, or plugin.cfg otherwise"
    @click.pass_obj
    def default_value(cfg):
        return getattr(cfg, cfg_key or key, cfg.get_plugin_key(key))

    return default_value

def preferred_from_plugin(key):
    "Like default_from_plugin(), but plugin.cfg has higher priority than existing config value"
    @click.pass_obj
    def default_value(cfg):
        return cfg.get_plugin_key(key, getattr(cfg, key, None))

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
    opt_class = kw.pop("cls", DynamicPromptOption)
    opt = opt_class(args, **kw)
    kw.setdefault("default", saved_default(opt.name))
    return cloup.option(*args, **kw, cls=opt_class)

# IMPORTANT: this must be processed very early on, and by process_root(), since
# it takes care of calling .try_load() to get any saved config values
root_arg = cloup.argument(
    "root", default=".", is_eager=True, callback=process_root,
    help="Root of the project, meaning a directory containing the file 'gdasset.toml', "
    "or a VCS repository (currently, only Git is supported). If not specified, it "
    "will be determined automatically, starting at the current directory."
)

def shared_options(cmd):
    @cloup.option_group(
        "Project discovery options",
        option("--readme", default="README.md", metavar="PATH",
               show_default=True,
               help="Location of README file, relative to project root"),
        option("--changelog", default="CHANGELOG.md", metavar="PATH",
               show_default=True,
               help="Location of changelog file, relative to project root"),
        option("--plugin", metavar="PATH", is_eager=True,
               help="If specified, should be the path to a plugin.cfg file, "
               "which will be used to auto-populate project info"),
    )
    @cloup.option_group(
        "Asset metadata inputs",
        option("--title", required_if_missing=["plugin", "url"], default=default_from_plugin("name", "title"),
               help="Title / short description of the asset. "
               "Required unless --plugin or update URL is provided", cls=OptionRequiredIfMissing),
        option("--version", required_if_missing="plugin", default=preferred_from_plugin("version"),
               help="Asset version. Required unless --plugin is provided", cls=OptionRequiredIfMissing),
        option("--godot-version", required_if_missing="url",
               help="Minimum Godot version asset is compatible with. "
               "Required unless update URL is provided", cls=OptionRequiredIfMissing),
        option("--licence", required_if_missing="url",
               help="Asset's licence. Required unless update URL is provided", cls=OptionRequiredIfMissing),
    )
    @cloup.option_group(
        "Repository and download inputs",
        option("--repo-url", metavar="URL", required_if_missing="url", default=default_repo_url,
               help="Repository URL. Will be inferred from repo remote if possible.", cls=OptionRequiredIfMissing),
        option("--repo-provider", required_if_missing="url",
               type=click.Choice([x.name.lower() for x in rest_api.RepoProvider], case_sensitive=False),
               default=default_repo_provider, callback=process_repo_provider,
               help="Repository provider. Will be inferred from repo remote if possible.", cls=OptionRequiredIfMissing),
        option("--issues-url", metavar="URL", required_if_missing="url", default=default_issues_url,
               help="URL for reporting issues. Will be inferred from repository URL possible.", cls=OptionRequiredIfMissing),
        option("--commit", metavar="COMMIT_ID", required=True, default=default_commit,
               help="Commit ID to upload. Will be inferred from current repo if possible."),
        option("--download-url", metavar="URL", required_if_missing="url", default=default_download_url,
               help="Download URL for asset's main ZIP. Will be inferred from repository URL possible.", cls=OptionRequiredIfMissing),
        option("--icon-url", metavar="URL", required_if_missing="url", help="Icon URL", cls=OptionRequiredIfMissing),
    )
    @cloup.option_group(
        "Behaviour flags",
        option("--unwrap-links/--no-unwrap-links", default=True, show_default=True,
               help="If true, all Markdown links will be converted to plain URLs. "
               "This is the default, since the asset library does not support any form of markup. "
               "If false, the original syntax, as used in the source Markdown file, will be preserved. "
               "Does not affect processing links to images and videos."),
        option("--preserve-html/--no-preserve-html", default=False, show_default=True,
               help="If true, raw HTML fragments in Markdown will be left as-is. "
               "Otherwise they will be omitted from the output."),
        option("--assume-yes/--confirm", "-Y", "no_prompt",
               default=False, show_default=True, is_eager=True,
               help="Whether to confirm inferred default values interactively. "
               "Values passed in on the command line are always taken as-is and not confirmed."),
        option("--quiet/--verbose", "-q", default=False, show_default=True,
               help="If quiet, preview will not be printed."),
        option("--dry-run/--do-it", "-n", default=False, show_default=True,
               help="In dry run, assets will not actually be uploaded or updated."),
        option("--save/--no-save", default=True, show_default=True, prompt="Save your answers as defaults?",
               help="If true, config will be saved as gdasset.toml in the project root. "
               "Only explicitly provided values (either on command line or interactively) will be saved, "
               "inferred defaults will be skipped."),
    )
    @shared_auth_options
    @root_arg
    @click.pass_context
    @wraps(cmd)
    def make_cfg_and_call(ctx, *args, **kwargs):
        ctx.obj.validate()
        cfg_kwargs = {field.name for field in dataclasses.fields(config.Config)}
        cmd_kwargs = set(signature(cmd).parameters)
        for kw in cfg_kwargs - cmd_kwargs:
            kwargs.pop(kw, None)
        ctx.invoke(cmd, *args, **kwargs)

    return make_cfg_and_call

@click.pass_obj
def ensure_auth(cfg):
    if not cfg.auth:
        cfg.auth = config.Auth(cfg.root)
        cfg.auth.try_load()

def saved_auth(field):
    @click.pass_obj
    def default(cfg):
        ensure_auth()
        return getattr(cfg.auth, field, None)
    return default

def process_auth(ctx, param, value):
    ensure_auth()
    return ctx.obj.auth.set(param.name, value, validate=False)

@click.pass_context
def invalidate_token(ctx):
    ctx.obj.auth.set("token", None, validate=False)
    ctx.params["token"] = None

def process_password(ctx, param, value):
    value = process_auth(ctx, param, value)
    if not is_default_param(ctx, param):
        # We need to invalidate the token if any password is passed in
        invalidate_token()
    return value

def process_username(ctx, param, value):
    previous = ctx.obj.auth.username
    value = process_auth(ctx, param, value)
    if previous and previous != value:
        # We need to invalidate the token if the username has changed
        invalidate_token()
    return value

class PasswordOption(DynamicPromptOption):
    """--password needs special processing, since we shouldn't prompt for it if a
token has been received from any source"""
    def prompt_for_value(self, ctx):
        if ctx.obj.auth.token:
            return None
        else:
            return super().prompt_for_value(ctx)

def shared_auth_options(cmd):
    @cloup.option_group(
        "Authentication options",
        option("--token", default=saved_auth("token"), callback=process_auth,
               help="Token generated by an earlier login. Can be used instead of username and password."),
        option("--username", default=saved_auth("username"), callback=process_auth,
               help="Username to log in with. Will be prompted if not provided"),
        option("--password", hide_input=True, default=saved_auth("password"), callback=process_auth,
               help="Password to log in with. Will be prompted if not provided", cls=PasswordOption),
        option("--save-auth/--no-save-auth", default=True, show_default=True, prompt="Save your login token?",
               help="If true, the username and login token will be saved as gdasset-auth.toml in the project root. "
               "Auth information is saved separately from the config values, and the password is never saved."),
        constraint=If(IsSet("token"), then=require_any.rephrased("optional"), else_=RequireNamed("username", "password"))
    )
    @click.pass_context
    @wraps(cmd)
    def make_auth_and_call(ctx, *args, **kwargs):
        auth_kwargs = {field.name for field in dataclasses.fields(config.Auth)}
        ensure_auth()
        ctx.obj.auth.validate()
        cmd_kwargs = set(signature(cmd).parameters)
        for kw in auth_kwargs - cmd_kwargs:
            kwargs.pop(kw, None)
        ctx.invoke(cmd, *args, **kwargs)

    return make_auth_and_call

def get_asset_payload(cfg: config.Config):
    """Based on CFG, get the payload dict for the asset suitable for posting to the
asset library. The payload generated might not be complete, and might need to be
merged with another dict to provide missing values (this is the case for updates)"""
    path_offset = "/".join(cfg.readme.parent.relative_to(cfg.root).parts)
    def prep_image_url(url):
        if not URL(url).absolute:
            return vcs.resolve_with_base_content_url(
                cfg.repo_url, cfg.commit, url, path_offset=path_offset
            )
        return url

    def prep_link_url(url):
        if not URL(url).absolute:
            return vcs.resolve_with_base_url(cfg.repo_url, cfg.commit, url)
        return url

    description, previews = get_asset_description(
        cfg, prep_image_func=prep_image_url, prep_link_func=prep_link_url
    )
    return {
        "title": cfg.title,
        "description": description,
        "godot_version": cfg.godot_version,
        "version_string": cfg.version,
        "cost": cfg.licence,
        "download_provider": cfg.repo_provider.value,
        "download_commit": cfg.commit,
        "browse_url": cfg.repo_url,
        "issues_url": cfg.issues_url,
        "icon_url": cfg.icon_url,
        "download_url": cfg.download_url,
        "previews": previews,
    }

@click.pass_context
def save_cfg(ctx, cfg):
    cfg.save(exclude={param for param in ctx.params
                      if is_default_param(ctx, param)})

def maybe_print(msg, *args, pager=False, **kwargs):
    ctx = click.get_current_context(silent=True)
    cfg = ctx and ctx.obj
    if cfg and cfg.quiet:
        return
    if pager:
        click.echo_via_pager(msg, *args, **kwargs)
    else:
        click.echo(msg, *args, **kwargs)

def summarise_payload(cfg, payload):
    with StringIO() as buf:
        sep = "=" * terminal_width()
        minisep = "-" * terminal_width()
        def p(*args, **kwargs):
            print(*args, **kwargs, file=buf)

        p(sep)
        p(payload["title"])
        p("Version:", payload["version_string"])
        p("Licence:", payload["cost"])
        p()
        p("Download provider:", payload["download_provider"])
        p("Repo/browse URL:", payload["browse_url"])
        p("Issues URL:", payload["download_url"])
        p("Commit:", payload["download_commit"])
        p("Download URL:", payload["download_url"])
        p(minisep)
        p()
        for line in payload["description"].splitlines():
            p(line)
        p()
        p(minisep)
        ops = {
            "delete": " (deleted)",
            "insert": " (new)",
        }
        previews = [(p["type"].capitalize(), p["link"], ops.get(p["operation"], ""))
                    for p in payload["previews"]]
        if previews:
            p("Previews:")
            for type, link, op in previews:
                p(f"  {type}{op}: {link}")
        p(sep)
        maybe_print(buf.getvalue(), pager=not cfg.no_prompt)

SHARED_PRIORITY_ADJUSTMENTS = [
    ("token", "username", "password", "save_auth"),
]
SHARED_PRIORITY_LIST = ["root", "readme", "no_prompt", "quiet", "plugin"]

class UploadCommand(PriorityProcessingCommand):
    PRIORITY_LIST = SHARED_PRIORITY_LIST
    PRIORITY_ADJUSTMENTS = SHARED_PRIORITY_ADJUSTMENTS

@cli.command(epilog=CMD_EPILOGUE, cls=UploadCommand)
@shared_options
@click.pass_context
def upload(ctx, save, save_auth):
    """Upload a new asset to the library"""
    ctx.invoke(update, previous_payload={})

def process_update_url(ctx, _, url):
    if url is not None:
        payload = rest_api.get_asset_info(url)
        ctx.obj = rest_api.update_cfg_from_payload(ctx.obj, payload)
        # Explicit config file should take priority over existing asset URL
        ctx.obj.try_load()
        return payload
    return {}

class UpdateCommand(PriorityProcessingCommand):
    PRIORITY_LIST = SHARED_PRIORITY_LIST + ["url"]
    PRIORITY_ADJUSTMENTS = SHARED_PRIORITY_ADJUSTMENTS

@cli.command(epilog=CMD_EPILOGUE, cls=UpdateCommand)
@cloup.argument("previous_payload", metavar="URL", required=True, callback=process_update_url,
                help="Either the full URL to an asset in the library, or an ID (such as '3133'), which will be looked up")
@shared_options
@click.pass_context
def update(ctx, previous_payload, save, save_auth):
    """Update an existing asset in the library"""
    cfg = ctx.obj
    payload = get_asset_payload(cfg)
    pending = []
    confirmation = False

    if previous_payload:
        pending = rest_api.get_pending_edits(previous_payload["asset_id"])

    # NB: We can't use merge_asset_payload() for comparisons because of the
    # special processing it does to previews
    if dict_merge(previous_payload, payload) == previous_payload:
        maybe_print("No changes from the existing asset listing, not updating")
    if any(rest_api.is_payload_same_as_pending(previous_payload, payload, edit)
           for edit in pending):
        maybe_print("There is already a pending edit for this asset with identical changes, not updating")
    else:
        payload = rest_api.merge_asset_payload(payload, previous_payload)
        summarise_payload(cfg, payload)
        confirmation = cfg.no_prompt or cfg.dry_run or click.confirm(
            "Proceed with the update?" if previous_payload else "Proceed with the upload?"
        )
    if save:
        save_cfg(cfg)

    if cfg.dry_run:
        maybe_print("DRY RUN: no changes were made")
    elif confirmation:
        rest_api.login_and_update_token(cfg)
        for retry in range(1, -1, -1):
            try:
                rest_api.upload_or_update_asset(cfg, payload)
            except HTTPRequestError as exc:
                if retry and (not cfg.no_prompt or cfg.auth.password):
                    printerr(exc)
                    invalidate_token()
                    password_param = [p for p in ctx.command.params if p.name == "password"][0]
                    cfg.auth.password = cfg.auth.password or password_param.prompt_for_value(ctx)
                    rest_api.login_and_update_token(cfg, force=True)
                    continue
                raise

    if save_auth:
        save_cfg(cfg.auth)

class LoginCommand(PriorityProcessingCommand):
    PRIORITY_LIST = SHARED_PRIORITY_LIST + ["url"]
    PRIORITY_ADJUSTMENTS = SHARED_PRIORITY_ADJUSTMENTS

@cli.command(cls=LoginCommand)
@shared_auth_options
@root_arg
@click.pass_obj
def login(cfg, root, save_auth):
    """Log into the asset library using the provided credentials

This is not required before using other commands, but can be used to save the generated token
for future use, or test an existing token."""
    rest_api.login_and_update_token(cfg, force=True)
    # FIXME: actually save the token
    click.echo("Login successful")
    if save_auth:
        save_cfg(cfg.auth)

def printerr(msg):
    maybe_print(f"ERROR: {msg}", file=sys.stderr)

def die(msg, code=1):
    printerr(msg)
    sys.exit(code)

def safe_cli():
    with click.Context(cli) as ctx:
        ctx.obj = config.Config(root=".", readme=".")
        try:
            cli(parent=ctx)
        except GdAssetError as e:
            die(str(e))
        except Exception as e:
            debug_on_error()

if __name__ == "__main__":
    safe_cli()
