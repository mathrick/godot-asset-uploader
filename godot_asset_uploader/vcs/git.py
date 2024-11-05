from dulwich.repo import Repo as GitRepo
import dulwich.porcelain as git
from dulwich.errors import NotGitRepository

import giturlparse
from yarl import URL

from ..errors import BadRepoError
from ..rest_api import RepoProvider


def has_repo(path):
    try:
        repo = GitRepo(path)
        if repo.bare:
            raise BadRepoError(repo_type="git", path=path, details="Bare repos are not supported")
        return True
    except NotGitRepository:
        return False


def get_repo(path):
    """Open a Git repo containing PATH. It is an error if there's no repo rooted exactly at PATH."""
    return GitRepo(path)


def get_branch_remote(repo):
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


def get_remote_repo(repo, remote_location=None):
    "dulwich.porcelain.get_remote_repo(), modified to use get_branch_remote()"
    config = repo.get_config()
    if remote_location is None:
        remote_location = get_branch_remote(repo)
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


def guess_commit(root):
    with git.open_repo_closing(root) as repo:
        return repo.head().decode()


def guess_repo_url(root):
    with git.open_repo_closing(root) as repo:
        remote, url = get_remote_repo(repo)
        parsed = giturlparse.parse(url or "")
        url = parsed.valid and parsed.url2https
        # Annoyingly, giturlparse always adds .git, so now we have to get rid of it
        url = url and str(URL(url).with_suffix(""))
        # Due to how dulwich returns the remote info, if a reasonable remote
        # wasn't found, the URL will be something nonsensical like "origin"
        # instead of None. Even if remote is found, the location could still be
        # a local directory for instance.
        return url if remote and parsed.valid else None


def guess_repo_provider(url):
    platform = (giturlparse.parse(url or "").platform or "custom").upper()
    return url and RepoProvider.__members__.get(platform, RepoProvider.CUSTOM)


def guess_issues_url(url):
    "Try to guess the issues URL based on the remote repo URL"
    provider = guess_repo_provider(url)
    if provider in [RepoProvider.GITHUB, RepoProvider.GITLAB, RepoProvider.BITBUCKET]:
        return str(URL(url) / "issues")
    return None


def guess_download_url(url, commit):
    "Try to guess the download URL based on the remote repo URL"
    provider = guess_repo_provider(url)
    parsed = URL(url)
    if provider in [RepoProvider.GITHUB, RepoProvider.GITLAB]:
        parsed = parsed / "archive" / f"{commit}.zip"
    elif provider == RepoProvider.BITBUCKET:
        parsed = parsed / "get" / f"{commit}.zip"
    else:
        return None

    return str(parsed)
