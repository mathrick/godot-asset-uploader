from itertools import chain
from pathlib import Path
from string import Template

import giturlparse
from yarl import URL

from .. import config
from ..errors import GdAssetError, NoImplementationError

from .providers import RepoProvider, remote_to_https
from . import git, hg

IMPLS = [hg, git]


GITHUB_BASE_CONTENT_URL = URL("https://raw.githubusercontent.com/$owner/$repo/$commit/")
# FIXME: This is probably wrong in some cases, since GitLab has much more
# complicated ways of grouping repos with multiple levels of hierarchy
GITLAB_BASE_CONTENT_URL = URL("https://$host/$owner/$repo/-/raw/$commit/")


def dir_and_parents(path):
    path = Path(path)
    return chain([path] if path.is_dir() else [], path.parents)


def get_project_root(path):
    """Find the closest project root which contains the given PATH. The
root might be the PATH itself, or a parent directory.

A "project root" is defined as repository in a supported format
(currently, Git or Mercurial), OR a directory containing
'gdasset.ini'. If multiple candidates for the root exist, the closest
one (ie. fewest levels up the directory tree) will be picked."""
    for dir in dir_and_parents(path):
        if config.has_config_file(dir) or any(impl.has_repo(dir) for impl in IMPLS):
            return dir


def guess_vcs_type(path):
    """Return a tuple of (vcs_type: str, root: Path) if a known VCS has
been detected, starting at PATH and going up the parent chain"""
    path = Path(path)
    for dir in dir_and_parents(path):
        for impl in IMPLS:
            if impl.has_repo(path):
                return (impl, path)
    return (None, None)


def get_repo(path):
    """Open a repo containing PATH, traversing up the tree as needed, and using
whatever VCS is closest (currently Git and Mercurial are supported)."""
    vcs, root = guess_vcs_type(path)
    if vcs:
        return vcs.get_repo(root)
    return None


def dispatch_vcs(meth, error_detail, docstring=None):
    def dispatch(root, *args, **kwargs):
        try:
            vcs_type, root = guess_vcs_type(root)
            if not vcs_type:
                return None
            return getattr(vcs_type, meth)(root, *args, **kwargs)
        except KeyError:
            raise NotImplementedError(
                f"{error_detail} for {vcs_type} not implemented"
            )

    if docstring is not None:
        dispatch.__doc__ = docstring
    return dispatch


def dispatch_url(guessers, docstring=None):
    def dispatch(url, *args, **kwargs):
        for guesser in guessers:
            if (cand := guesser(url, *args, **kwargs)):
                return cand
        return None

    if docstring is not None:
        dispatch.__doc__ = docstring
    return dispatch


guess_commit = dispatch_vcs("guess_commit", [git, hg], "Head commit extraction")

guess_repo_url = dispatch_vcs("guess_repo_url", [git, hg], "Repo URL detection")


# NOTE: Mercurial providers are handled here as well. The biggest hosted provider
# for Hg is Heptapod, which is a fork of GitLab and will be detected as such
def guess_repo_provider(url):
    parsed = giturlparse.parse(url or "")
    platform = (parsed.platform if parsed else "").upper()
    if platform == "GITLAB" and "heptapod.net" in parsed.host:
        return RepoProvider.HEPTAPOD
    return url and RepoProvider.__members__.get(platform, RepoProvider.CUSTOM)


def guess_issues_url(url):
    "Try to guess the issues URL based on the remote repo URL"
    provider = guess_repo_provider(url)
    if provider in [
            RepoProvider.GITHUB, RepoProvider.GITLAB, RepoProvider.BITBUCKET, RepoProvider.HEPTAPOD
    ]:
        return str(URL(remote_to_https(url)) / "issues")
    return None


def guess_download_url(url, commit):
    "Try to guess the download URL based on the remote repo URL"
    provider = guess_repo_provider(url)
    url = URL(remote_to_https(url) or url)
    if provider in [RepoProvider.GITHUB, RepoProvider.GITLAB]:
        url = url / "archive" / f"{commit}.zip"
    elif provider == RepoProvider.HEPTAPOD:
        # FIXME: I don't know if the "-" is always valid, I don't fully
        # understand its role in GitLab URLs
        url = url / "-" / "archive" / commit / f"{commit}.zip"
    elif provider == RepoProvider.BITBUCKET:
        url = url / "get" / f"{commit}.zip"
    else:
        return None

    return str(url)


# FIXME: This assumes git
def resolve_with_base_content_url(provider_url, commit, relative_path, path_offset=None):
    """Get the base URL to resolve relative links against for the given provider.
I.e. https://raw.githubusercontent.com/owner/repo/commit/relative/path

    If PATH_OFFSET is given, it should be a slash-separated string representing
the difference between repository root, and the location of the file the link is
being generated from. I.e. if the links are resolved for docs/dev/README.md, then
the offset would be "docs/dev", and the resulting URL would become
https://raw.githubusercontent.com/owner/repo/commit/docs/dev/relative/path"""
    provider = guess_repo_provider(provider_url)
    parsed = giturlparse.parse(provider_url or "")
    if provider == RepoProvider.GITHUB:
        base_url = GITHUB_BASE_CONTENT_URL
    elif provider == RepoProvider.BITBUCKET:
        raise NoImplementationError(
            f"Can't resolve relative URL ({relative_path}), not supported in BitBucket repos"
        )
    elif provider == RepoProvider.GITLAB:
        base_url = GITLAB_BASE_CONTENT_URL
    else:
        raise GdAssetError(f"Unexpected repo provider '{provider}', this is a bug")
    if path_offset:
        base_url = base_url / path_offset
    template = Template(str(base_url / relative_path))
    return template.safe_substitute(**parsed.data, host=parsed.host, commit=commit)
