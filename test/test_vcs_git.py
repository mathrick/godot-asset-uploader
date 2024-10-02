import pytest

from dulwich.repo import Repo
from dulwich.porcelain import update_head, reset, open_repo_closing, active_branch

from godot_asset_uploader.config import Config
from godot_asset_uploader.vcs import (
    guess_vcs_type, get_repo, get_project_root,
    guess_repo_url,guess_issues_url, guess_download_url, guess_commit,
)

GITHUB_URL = "https://github.com/ihopethisisnotarealusername/dummy-repo"
GITHUB_ISSUES_URL = f"{GITHUB_URL}/issues"
HEAD = "98e7311dae8377ecb152a3258248e04cd53389c3"
GITHUB_DOWNLOAD_URL = f"{GITHUB_URL}/archive/{HEAD}.zip"

@pytest.fixture
def tmp_git_repo(shared_datadir):
    def prepare(repo_name):
        root = shared_datadir / repo_name
        # We have to do gymnastics here because git categorically
        # refuses to track another git repo as plain files
        (root / "_git").rename(root / ".git")
        return root
    return prepare

# NOTE: This is destructive to the index and working tree and will
# throw away all uncommitted state and not do a merge! Only suitable
# for use in tests.
def reset_branch(repo, branch):
    with open_repo_closing(repo) as repo:
        update_head(repo, branch)
        reset(repo, "hard", branch)

def test_git_basic(tmp_git_repo):
    repo = tmp_git_repo("repo-github")
    assert guess_vcs_type(repo) == ("git", repo)
    assert isinstance(get_repo(repo), Repo)
    assert get_project_root(repo) == repo

@pytest.mark.parametrize("branch", [
    "main",
    "branch-https",
    "push-remote-only"
])
def test_git_remote_github(branch, tmp_git_repo):
    repo = tmp_git_repo("repo-github")
    reset_branch(repo, branch)
    # Just a sanity check
    assert active_branch(repo).decode() == branch

    assert (remote := guess_repo_url(repo)) == GITHUB_URL
    assert (commit := guess_commit(repo)) == HEAD
    assert guess_issues_url(remote) == GITHUB_ISSUES_URL
    assert guess_download_url(remote, commit) == GITHUB_DOWNLOAD_URL
