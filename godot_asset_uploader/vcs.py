from itertools import chain
from pathlib import Path
from urllib.parse import urlparse

from dulwich.repo import Repo as GitRepo
import dulwich.porcelain as git
from dulwich.errors import NotGitRepository
import giturlparse

from . import config, errors as err
from .rest_api import RepoProvider

def has_git_repo(path):
    try:
        repo = GitRepo(path)
        if repo.bare:
            raise err.BadRepoError(repo_type="git", path=path, details="Bare repos are not supported")
        return True
    except NotGitRepository:
        return False

def get_project_root(path):
    """Find the closest project root which contains the given PATH. The
root might be the PATH itself, or a parent directory.

A "project root" is defined as repository in a supported format
(currently, that means only Git), OR a directory containing
'gdasset.ini'. If multiple candidates for the root exist, the closest
one (ie. fewest levels up the directory tree) will be picked."""
    path = Path(path)
    for dir in chain([path] if path.is_dir() else [], path.parents):
        if config.has_config_file(dir) or has_git_repo(dir):
            return dir

def git_get_branch_remote(repo):
    """Like dulwich.porcelain.get_branch_remote(), but tries harder to figure out what
the remote is if the current branch doesn't have a remote set (remotes are
normally assigned on a per-branch basis). This happens with Magit for example,
where pushDefault will be taken into account in the absence of per-branch
remote, so the UI will show a remote branch, but dulwich will return nothing
when asked for the remote."""
    with git.open_repo_closing(repo) as r:
        branch_name = git.active_branch(r.path)
        config = r.get_config()
        for section, key in [
                ((b"branch", branch_name), b"remote"),
                ((b"branch", branch_name), b"pushRemote"),
                ((b"remote",), b"pushDefault"),
        ]:
            try:
                remote_name = config.get(section, key)
                break
            except KeyError:
                continue
        else:
            remote_name = b"origin"
    return remote_name

def git_get_remote_repo(repo, remote_location=None):
    "dulwich.porcelain.get_remote_repo(), modified to use git_get_branch_remote()"
    config = repo.get_config()
    if remote_location is None:
        remote_location = git_get_branch_remote(repo)
    if isinstance(remote_location, str):
        encoded_location = remote_location.encode()
    else:
        encoded_location = remote_location

    section = (b"remote", encoded_location)

    remote_name = None

    if config.has_section(section):
        remote_name = encoded_location.decode()
        encoded_location = config.get(section, "url")
    else:
        remote_name = None

    return (remote_name, encoded_location.decode())

def guess_vcs_type(path):
    """Return a tuple of (vcs_type: str, root: Path) if a known VCS has
been detected, starting at PATH and going up the parent chain"""
    path = Path(path)
    while path:
        if has_git_repo(path):
            return ("git", path)
    return (None, None)

def guess_git_repo_url(root):
    with git.open_repo_closing(root) as repo:
        remote, url = git_get_remote_repo(repo)
        parsed = giturlparse.parse(url or "")
        url = parsed.valid and parsed.url2https
        # Annoyingly, giturlparse always adds .git, so now we have to get rid of it
        parsed_url = urlparse(url)
        if parsed_url.path.endswith(".git"):
            parsed_url = parsed_url._replace(path=parsed_url.path[:-4])
        url = parsed_url.geturl()
        # Due to how dulwich returns the remote info, if a reasonable remote
        # wasn't found, the URL will be something nonsensical like "origin"
        # instead of None. Even if remote is found, the location could still be
        # a local directory for instance.
        return url if remote and parsed.valid else None

def guess_repo_url(root):
    repo_type, vcs_root = guess_vcs_type(root)
    if not repo_type:
        return None
    if repo_type == "git":
        return guess_git_repo_url(root)
    raise NotImplementedError(
        f"Repo URL detection for {repo_type} not implemented"
    )

def guess_git_repo_provider(root):
    url = guess_git_repo_url(root)
    platform = (giturlparse.parse(url or "").platform or "custom").upper()
    return url and RepoProvider.__members__.get(platform , RepoProvider.CUSTOM)

def guess_repo_provider(root):
    repo_type, vcs_root = guess_vcs_type(root)
    if not repo_type:
        return None
    if repo_type == "git":
        return guess_git_repo_provider(root)
    raise NotImplementedError(
        f"Repo provider detection for {repo_type} not implemented"
    )

def guess_git_commit(root):
    with git.open_repo_closing(root) as repo:
        return repo.head().decode()

def guess_commit(root):
    repo_type, vcs_root = guess_vcs_type(root)
    if not repo_type:
        return None
    if repo_type == "git":
        return guess_git_commit(root)
    raise NotImplementedError(
        f"Head commit extraction for {repo_type} not implemented"
    )
