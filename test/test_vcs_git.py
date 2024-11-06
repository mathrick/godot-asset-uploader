import pytest

from dulwich.repo import Repo
from dulwich.porcelain import update_head, reset, open_repo_closing, active_branch

from godot_asset_uploader.vcs import (
    git as git_module,
    guess_vcs_type, get_repo, get_project_root,
    guess_repo_url, guess_repo_provider, guess_issues_url, guess_download_url,
    guess_commit,
)

from vcs_urls import (
    GITHUB_EXPECTED,
    BITBUCKET_EXPECTED,
    GITLAB_EXPECTED,
    GITLAB_SELF_HOSTED_EXPECTED,
)

BRANCHES = ["main", "branch-https", "push-remote-only"]


@pytest.fixture
def tmp_git_repo(shared_datadir):
    def prepare(repo_name):
        root = shared_datadir / "git" / repo_name
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
    assert guess_vcs_type(repo) == (git_module, repo)
    assert isinstance(get_repo(repo), Repo)
    assert get_project_root(repo) == repo


@pytest.mark.parametrize(
    "repo, branch, expected",
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
    # Just a sanity check
    assert active_branch(repo).decode() == branch

    assert (remote := guess_repo_url(repo)) == expected.repo_url
    assert (commit := guess_commit(repo)) == expected.commit
    assert guess_repo_provider(remote) == expected.provider
    assert guess_issues_url(remote) == expected.issues_url
    assert guess_download_url(remote, commit) == expected.download_url
