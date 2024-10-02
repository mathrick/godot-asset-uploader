import pytest

from dulwich.repo import Repo
from dulwich.porcelain import update_head, reset, open_repo_closing, active_branch

from godot_asset_uploader.config import Config
from godot_asset_uploader.vcs import (
    RepoProvider,
    guess_vcs_type, get_repo, get_project_root,
    guess_repo_url, guess_repo_provider, guess_issues_url, guess_download_url,
    guess_commit,
)

HEAD = "98e7311dae8377ecb152a3258248e04cd53389c3"
BRANCHES = ["main", "branch-https", "push-remote-only"]

GITHUB_URL = "https://github.com/ihopethisisnotarealusername/dummy-repo"
GITHUB_ISSUES_URL = f"{GITHUB_URL}/issues"
GITHUB_DOWNLOAD_URL = f"{GITHUB_URL}/archive/{HEAD}.zip"
GITHUB_EXPECTED = (
    HEAD, RepoProvider.GITHUB, GITHUB_URL, GITHUB_ISSUES_URL, GITHUB_DOWNLOAD_URL
)

BITBUCKET_URL = "https://ihopethisisnotarealusername@bitbucket.org/ihopethisisnotarealusername/dummy-repo"
BITBUCKET_ISSUES_URL = f"{BITBUCKET_URL}/issues"
BITBUCKET_DOWNLOAD_URL = f"{BITBUCKET_URL}/get/{HEAD}.zip"
BITBUCKET_EXPECTED = (
    HEAD, RepoProvider.BITBUCKET, BITBUCKET_URL, BITBUCKET_ISSUES_URL, BITBUCKET_DOWNLOAD_URL
)

GITLAB_URL = "https://gitlab.com/ihopethisisnotarealusername/dummy-repo"
GITLAB_ISSUES_URL = f"{GITLAB_URL}/issues"
GITLAB_DOWNLOAD_URL = f"{GITLAB_URL}/archive/{HEAD}.zip"
GITLAB_EXPECTED = (
    HEAD, RepoProvider.GITLAB, GITLAB_URL, GITLAB_ISSUES_URL, GITLAB_DOWNLOAD_URL
)

GITLAB_SELF_HOSTED_URL = "https://gitlab.self-hosted.com/ihopethisisnotarealusername/dummy-repo"
GITLAB_SELF_HOSTED_ISSUES_URL = f"{GITLAB_SELF_HOSTED_URL}/issues"
GITLAB_SELF_HOSTED_DOWNLOAD_URL = f"{GITLAB_SELF_HOSTED_URL}/archive/{HEAD}.zip"
GITLAB_SELF_HOSTED_EXPECTED = (
    HEAD, RepoProvider.GITLAB, GITLAB_SELF_HOSTED_URL, GITLAB_SELF_HOSTED_ISSUES_URL, GITLAB_SELF_HOSTED_DOWNLOAD_URL
)

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
    branch = branch.encode()
    with open_repo_closing(repo) as repo:
        update_head(repo, branch)
        reset(repo, "hard", branch)

def test_git_basic(tmp_git_repo):
    repo = tmp_git_repo("repo-github")
    assert guess_vcs_type(repo) == ("git", repo)
    assert isinstance(get_repo(repo), Repo)
    assert get_project_root(repo) == repo

@pytest.mark.parametrize(
    "repo, branch, expected",
    [("repo-github", branch, GITHUB_EXPECTED) for branch in BRANCHES] +
    [("repo-github", branch, GITHUB_EXPECTED) for branch in BRANCHES] +
    [("repo-bitbucket", branch, BITBUCKET_EXPECTED) for branch in BRANCHES] +
    [pytest.param(
        "repo-bitbucket", "branch-https-no-username", BITBUCKET_EXPECTED,
        marks=pytest.mark.xfail(reason="https://github.com/nephila/giturlparse/pull/108")
    )] +
    [("repo-gitlab", branch, GITLAB_EXPECTED) for branch in BRANCHES] +
    [("repo-gitlab-self-hosted", branch, GITLAB_SELF_HOSTED_EXPECTED) for branch in BRANCHES])
def test_git_remote(branch, repo, expected, tmp_git_repo):
    repo = tmp_git_repo(repo)
    reset_branch(repo, branch)
    head, provider, repo_url, issues_url, download_url = expected
    # Just a sanity check
    assert active_branch(repo).decode() == branch

    assert (remote := guess_repo_url(repo)) == repo_url
    assert (commit := guess_commit(repo)) == head
    assert guess_repo_provider(remote) == provider
    assert guess_issues_url(remote) == issues_url
    assert guess_download_url(remote, commit) == download_url
