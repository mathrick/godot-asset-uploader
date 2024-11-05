from itertools import chain
from pathlib import Path
from string import Template

import giturlparse
from yarl import URL

from .. import config
from ..errors import GdAssetError, NoImplementationError
from ..rest_api import RepoProvider

from . import git, hg

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
        if config.has_config_file(dir) or git.has_repo(dir):
            return dir

def guess_vcs_type(path):
    """Return a tuple of (vcs_type: str, root: Path) if a known VCS has
been detected, starting at PATH and going up the parent chain"""
    path = Path(path)
    impls = [git, hg]
    for dir in dir_and_parents(path):
        for impl in impls:
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


def dispatch_vcs(mapping, error_detail, docstring=None):
    def dispatch(root, *args, **kwargs):
        try:
            vcs_type, root = guess_vcs_type(root)
            if not vcs_type:
                return None
            return mapping[vcs_type](root, *args, **kwargs)
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


guess_commit = dispatch_vcs({git: git.guess_commit}, "Head commit extraction")

guess_repo_url = dispatch_vcs({git: git.guess_repo_url}, "Repo URL detection")

guess_repo_provider = dispatch_url([git.guess_repo_provider])

guess_issues_url = dispatch_url([git.guess_issues_url])

guess_download_url = dispatch_url([git.guess_download_url])


# FIXME: This assumes git
def resolve_with_base_content_url(provider_url, commit, relative_path, path_offset=None):
    """Get the base URL to resolve relative links against for the given provider.
I.e. https://raw.githubusercontent.com/owner/repo/commit/relative/path

    If PATH_OFFSET is given, it should be a slash-separated string representing
the difference between repository root, and the location of the file the link is
being generated from. I.e. if the links are resolved for docs/dev/README.md, then
the offset would be "docs/dev", and the resulting URL would become
https://raw.githubusercontent.com/owner/repo/commit/docs/dev/relative/path"""
    provider = git.guess_repo_provider(provider_url)
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
