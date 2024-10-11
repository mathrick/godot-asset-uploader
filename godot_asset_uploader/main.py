import dataclasses
from functools import wraps
from inspect import signature
from io import StringIO
import sys
import textwrap

import click, cloup
from cloup.formatting import sep, HelpFormatter
from cloup.constraints import constraint
from yarl import URL

from . import vcs, config, rest_api
from .errors import *
from .markdown import get_asset_description
from .util import dict_merge, terminal_width, debug_on_error
from .cli import (
    DynamicPromptOption, PriorityProcessingCommand,
    Constraint, RequireNamed, If, LenientIsSet as IsSet, Cond,
    optional, required_if_missing, require_all, accept_none,
    readable_param_name, is_default_param,
)

CMD_EPILOGUE = """Most parameters can be inferred from the project repository,
README.md, plugin.cfg, and the existing library asset (when performing
an update). Missing required options will be prompted for interactively,
unless the '--non-interactive' or '--quiet' flag was passed."""

CONTEXT_SETTINGS = cloup.Context.settings(
    align_option_groups=True,
    formatter_settings=HelpFormatter.settings(
        col1_max_width=20,
        row_sep=sep.RowSepIf(sep.multiline_rows_are_at_least(0.5)),
    ),
)

SEP = "=" * terminal_width()
MINISEP = "-" * terminal_width()


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


def process_category(ctx, param, value):
    try:
        return ctx.obj.set(param.name, int(value))
    except ValueError:
        return ctx.obj.set(param.name, rest_api.find_category_id(value))


@click.pass_obj
def default_category(cfg):
    group, name = rest_api.find_category_name(cfg.category)
    return f"{group}/{name}" if name else cfg.category


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

@click.pass_context
def have_explicit_auth(ctx, params=None):
    params = params or ["token", "username", "password"]
    return any(not is_default_param(ctx, param) for param in params)

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


def option(*args, **kwargs):
    kw = {"callback": process_param, "prompt": Constraint.auto_prompter()}
    kw.update(kwargs)
    # This is the easiest way of robustly getting the name of the option that I
    # can think of, even if it's a bit inelegant
    opt_class = kw.pop("cls", DynamicPromptOption)
    opt = opt_class(args, **kw)
    kw.setdefault("default", saved_default(opt.name))
    return cloup.option(*args, **kw, cls=opt_class)


def make_options_decorator(*options):
    def decorate(cmd):
        wrapper = wraps(cmd)
        for option in reversed(options):
            cmd = option(cmd)

        return wrapper(cmd)
    return decorate


def invoke_with_cfg(cmd):
    @click.pass_context
    @wraps(cmd)
    def make_cfg_and_call(ctx, *args, **kwargs):
        ctx.obj.validate()
        cfg_kwargs = {field.name for field in dataclasses.fields(config.Config)}
        cmd_kwargs = set(signature(cmd).parameters)
        for kw in cfg_kwargs - cmd_kwargs:
            kwargs.pop(kw, None)
        cmd(*args, **kwargs)

    return make_cfg_and_call


def invoke_with_auth(cmd):
    @click.pass_context
    @wraps(cmd)
    def make_auth_and_call(ctx, *args, **kwargs):
        auth_kwargs = {field.name for field in dataclasses.fields(config.Auth)}
        ensure_auth()
        ctx.obj.auth.validate()
        cmd_kwargs = set(signature(cmd).parameters)
        for kw in auth_kwargs - cmd_kwargs:
            kwargs.pop(kw, None)
        cmd(*args, **kwargs)

    return make_auth_and_call


# IMPORTANT: this must be processed very early on, and by process_root(), since
# it takes care of calling .try_load() to get any saved config values
root_arg = cloup.argument(
    "root", default=".", is_eager=True, callback=process_root,
    help="Root of the project, meaning a directory containing the file 'gdasset.toml', "
    "or a VCS repository (currently, only Git is supported). If not specified, it "
    "will be determined automatically, starting at the current directory."
)

INTERACTION_OPTIONS = [
    option("--non-interactive/--interactive", "-Y", "no_prompt",
           default=False, show_default=True, is_eager=True,
           help="Whether to confirm inferred default values interactively. "
           "Values passed in on the command line are always taken as-is and not confirmed."),
    option("--quiet/--echo", "-q", default=False, show_default=True,
           help="If quiet, no preview or other messages will be printed. Implies --non-interactive"),
]

interaction_options = cloup.option_group(
    "Behaviour flags",
    *INTERACTION_OPTIONS,
)

shared_behaviour_options = cloup.option_group(
    "Behaviour flags",
    option("--unwrap-links/--no-unwrap-links", default=True, show_default=True,
           help="If true, all Markdown links will be converted to plain URLs. "
           "This is the default, since the asset library does not support any form of markup. "
           "If false, the original syntax, as used in the source Markdown file, will be preserved. "
           "Does not affect processing links to images and videos."),
    option("--preserve-html/--no-preserve-html", default=False, show_default=True,
           help="If true, raw HTML fragments in Markdown will be left as-is. "
           "Otherwise they will be omitted from the output."),
    *INTERACTION_OPTIONS,
    option("--dry-run/--do-it", "-n", default=False, show_default=True,
           help="In dry run, assets will not actually be uploaded or updated."),
    option("--save/--no-save", default=True, show_default=True, prompt="Save your answers as defaults?",
           help="If true, config will be saved as gdasset.toml in the project root. "
           "Only explicitly provided values (either on command line or interactively) will be saved, "
           "inferred defaults will be skipped."),
)

def auth_param_required(param, ctx):
    return any()

SHORT_AUTH_OPTIONS = [
    option("--username", default=saved_auth("username"),
           required=Constraint.auto_require(), callback=process_auth,
           help="Username to log in with. Will be prompted if not provided"),
    option("--password", hide_input=True, default=saved_auth("password"),
           required=Constraint.auto_require(), callback=process_auth, prompt_required=False,
           help="Password to log in with. Will be prompted if not provided"),
    option("--save-auth/--no-save-auth", default=have_explicit_auth, show_default=True, prompt="Save your login token?",
           help="If true, the username and login token will be saved as gdasset-auth.toml in the project root. "
           "Auth information is saved separately from the config values, and the password is never saved."),
]

# Used by login()
short_auth_options = cloup.option_group(
    "Authentication options",
    *SHORT_AUTH_OPTIONS,
    constraint=require_all,
)

# Used by update() and upload()
shared_auth_options = cloup.option_group(
    "Authentication options",
    option("--token", default=saved_auth("token"), callback=process_auth,
           help="Token generated by an earlier login. Can be used instead of username and password."),
    *SHORT_AUTH_OPTIONS,
    constraint=If(IsSet("token"), then=accept_none, else_=RequireNamed("username", "password")).rephrased(
        "either --token or --username and --password are required, but not both"
    ),
)

shared_update_options = make_options_decorator(
    cloup.option_group(
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
    ),
    cloup.option_group(
        "Asset metadata inputs",
        option("--title", default=default_from_plugin("name", "title"), prompt=True,
               help="Title / short description of the asset"),
        option("--version", default=preferred_from_plugin("version"), prompt=True, help="Asset version"),
        option("--godot-version", prompt=True, help="Minimum Godot version asset is compatible with"),
        option("--category", default=default_category, callback=process_category, prompt=True,
               help="Asset's category. See the 'list' subcommand for possible choices"),
        option("--licence", prompt=True, help="Asset's licence"),
        constraint=Cond("previous_payload", optional,
                        "plugin", RequireNamed("godot_version", "category", "licence"),
                        else_=require_all),
    ),
    cloup.option_group(
        "Repository and download inputs",
        option("--repo-url", metavar="URL", default=default_repo_url, prompt=True,
               help="Repository URL. Will be inferred from repo remote if possible."),
        option("--repo-provider",  prompt=True, default=default_repo_provider, callback=process_repo_provider,
               type=click.Choice([x.name.lower() for x in rest_api.RepoProvider], case_sensitive=False),
               help="Repository provider. Will be inferred from repo remote if possible."),
        option("--issues-url", metavar="URL", default=default_issues_url, prompt=True,
               help="URL for reporting issues. Will be inferred from repository URL possible."),
        option("--commit", metavar="COMMIT_ID", required=True, default=default_commit, prompt=True,
               help="Commit ID to upload. Will be inferred from current repo if possible."),
        option("--download-url", metavar="URL", default=default_download_url, prompt=True,
               help="Download URL for asset's main ZIP. Will be inferred from repository URL possible."),
        option("--icon-url", metavar="URL", prompt=True, help="Icon URL"),
        constraint=required_if_missing("previous_payload"),
    ),
    shared_auth_options,
    shared_behaviour_options,
    root_arg,
)


@click.pass_context
def login_and_update_token(ctx, force=False):
    auth = ctx.obj.auth
    if auth.token and not force:
        return
    json = rest_api.login(auth.username, auth.password)
    auth.token = json["token"]
    ctx.set_parameter_source("token", ctx.get_parameter_source("password"))

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
        "category_id": cfg.category,
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
def save_cfg(ctx, cfg, include_defaults=False):
    exclude = {
        param for param in ctx.params if is_default_param(ctx, param)
    } if not include_defaults else {}
    cfg.save(exclude=exclude)

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
        def p(*args, **kwargs):
            print(*args, **kwargs, file=buf)

        category_id = int(payload["category_id"])
        group, name = rest_api.CATEGORY_ID_MAP[rest_api.OFFICIAL_LIBRARY_ROOT][category_id]
        category = f"{group}/{name}"

        p(SEP)
        p(payload["title"])
        p("Version:", payload["version_string"])
        p("Licence:", payload["cost"])
        p()
        p("Category:", category)
        p("Godot version:", payload["godot_version"])
        p("Download provider:", payload["download_provider"])
        p("Repo/browse URL:", payload["browse_url"])
        p("Issues URL:", payload["download_url"])
        p("Commit:", payload["download_commit"])
        p("Download URL:", payload["download_url"])
        p(MINISEP)
        p()
        for line in payload["description"].splitlines():
            p(line)
        p()
        p(MINISEP)
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
        p(SEP)
        maybe_print(buf.getvalue(), pager=not cfg.no_prompt)

SHARED_PRIORITY_ADJUSTMENTS = [
    ("token", "username", "password", "save_auth"),
]
SHARED_PRIORITY_LIST = ["root", "readme", "no_prompt", "quiet", "plugin"]

class UploadCommand(PriorityProcessingCommand):
    PRIORITY_LIST = SHARED_PRIORITY_LIST
    PRIORITY_ADJUSTMENTS = SHARED_PRIORITY_ADJUSTMENTS

@cli.command(epilog=CMD_EPILOGUE, cls=UploadCommand)
@shared_update_options
@invoke_with_cfg
@invoke_with_auth
def upload(save, save_auth):
    """Upload a new asset to the library"""
    # NB: Cannot just use ctx.forward(update) because of https://github.com/pallets/click/issues/2753
    # I.e. this MUST be broken out to a shared function that isn't a click command
    upload_or_update(previous_payload={}, save=save, save_auth=save_auth)

def process_update_url(ctx, _, url):
    if url is not None:
        payload = rest_api.get_asset_info(url)
        ctx.obj = rest_api.update_cfg_from_payload(ctx.obj, payload)
        # Explicit config file should take priority over existing asset URL
        ctx.obj.try_load()
        return payload
    return {}


def retry_with_auth(max_retries=1):
    """Decorator which authenticates, runs the wrapped block, and retries up to
MAX_RETRIES times. If a HTTPRequestError occurs, it will attempt to
re-authenticate, then retry."""
    @click.pass_context
    def runit(ctx, block):
        cfg = ctx.obj
        force = False
        for retry in range(max_retries, -1, -1):
            try:
                have_username = not is_default_param(ctx, "username")
                have_password = not is_default_param(ctx, "password")
                have_full_auth = have_username and have_password
                # If we're given one, we'll disregard the token and require full auth info
                if (have_username or have_password) and (force or not have_full_auth):
                    if not have_username:
                        cfg.auth.username = click.prompt("Username", default=cfg.auth.username)
                    if not have_password:
                        cfg.auth.password = click.prompt("Password", hide_input=True)
                    have_full_auth = True

                login_and_update_token(force=force or have_full_auth)
                block()
                break
            except HTTPRequestError as exc:
                # Don't bother retrying if we have full auth, since in this case
                # we've already tried a fresh token
                if retry and not cfg.no_prompt and not have_full_auth:
                    printerr(exc)
                    invalidate_token()
                    force = True
                    continue
                raise
    return runit


@click.pass_context
def upload_or_update(ctx, previous_payload, save, save_auth):
    """Shared implementation for the upload and update commands. Needs to be broken
out to a non-command function because of https://github.com/pallets/click/issues/2753"""
    cfg = ctx.obj
    payload = get_asset_payload(cfg)
    pending = []
    confirmation = False

    if previous_payload:
        pending = rest_api.get_pending_edits(previous_payload["asset_id"])

    # NB: We can't use merge_asset_payload() for comparisons because of the
    # special processing it does to previews
    if (rest_api.is_payload_same(dict_merge(previous_payload, payload), previous_payload)):
        maybe_print("No changes from the existing asset listing, not updating")
    elif any(rest_api.is_payload_same_as_pending(payload, previous_payload, edit)
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
        @retry_with_auth()
        def _():
            rest_api.upload_or_update_asset(cfg, payload)
    else:
        maybe_print("Aborted!")

    if save_auth:
        save_cfg(cfg.auth, include_defaults=True)

class UpdateCommand(PriorityProcessingCommand):
    PRIORITY_LIST = SHARED_PRIORITY_LIST + ["url"]
    PRIORITY_ADJUSTMENTS = SHARED_PRIORITY_ADJUSTMENTS

@cli.command(epilog=CMD_EPILOGUE, cls=UpdateCommand)
@cloup.argument("previous_payload", metavar="URL", required=True, callback=process_update_url,
                help="Either the full URL to an asset in the library, or an ID (such as '3133'), which will be looked up")
@shared_update_options
@invoke_with_cfg
@invoke_with_auth
def update(previous_payload, save, save_auth):
    """Update an existing asset in the library"""
    upload_or_update(previous_payload=previous_payload, save=save, save_auth=save_auth)

class LoginCommand(PriorityProcessingCommand):
    PRIORITY_LIST = SHARED_PRIORITY_LIST + ["url"]
    PRIORITY_ADJUSTMENTS = SHARED_PRIORITY_ADJUSTMENTS

@cli.command(cls=LoginCommand)
@short_auth_options
@interaction_options
@root_arg
@invoke_with_cfg
@invoke_with_auth
@click.pass_obj
def login(cfg, root, save_auth):
    """Log into the asset library using the provided credentials

This is not required before using other commands, but can be used to save the generated token
for future use."""
    @retry_with_auth()
    def _():
        maybe_print("Login successful")
        if save_auth:
            save_cfg(cfg.auth, include_defaults=True)


@cli.group()
def list():
    "Show known values and choices"
    pass


CATEGORIES_EPILOGUE = """\
Categories can be specified either by group/name (i.e. "Addons/Misc"), or by
numeric ID, as listed above. Names are not case-sensitive and can be shortened
as long as they're unique, and the group can be dropped, i.e. "ad/mi" and "misc" are
both equivalent.\
"""

@list.command(epilog=CATEGORIES_EPILOGUE)
def categories():
    "Show asset categories in known libraries"
    p = click.echo
    p("Asset categories in known asset libraries")
    p(SEP)
    p()
    for lib, categories in rest_api.KNOWN_LIBRARY_CATEGORIES.items():
        p(lib)
        p(MINISEP)
        for group, names in categories.items():
            p(f"  {group}")
            for id, name in names.items():
                p(f"{id: 6}: {name}")
        p()

    for line in textwrap.wrap(CATEGORIES_EPILOGUE, width=terminal_width()):
        p(line)


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
