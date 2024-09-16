from itertools import chain
from pathlib import Path
from dulwich.repo import Repo as GitRepo
from dulwich.errors import NotGitRepository

from . import config, errors as err

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
