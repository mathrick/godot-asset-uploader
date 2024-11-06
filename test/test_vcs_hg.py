import pytest

from hglib.client import hgclient

from godot_asset_uploader.vcs import (
    hg,
    guess_vcs_type, get_repo, get_project_root,
    guess_repo_url, guess_repo_provider, guess_issues_url, guess_download_url,
    guess_commit,
)

from vcs_urls import HEPTAPOD_EXPECTED

COMMIT = "80393d431e2fc344a3bfdb3bc41096278e429916"


def test_git_basic(shared_datadir):
    repo = shared_datadir / "hg" / "repo-heptapod"
    assert guess_vcs_type(repo) == (hg, repo)
    assert isinstance(get_repo(repo), hgclient)
    assert get_project_root(repo) == repo


def do_test_hg_remote(repo, expected):
    assert (remote := guess_repo_url(repo)) == expected.repo_url
    assert (commit := guess_commit(repo)) == expected.commit
    assert guess_repo_provider(remote) == expected.provider
    assert guess_issues_url(remote) == expected.issues_url
    assert guess_download_url(remote, commit) == expected.download_url


@pytest.mark.parametrize(
    "repo, expected",
    [("repo-heptapod", HEPTAPOD_EXPECTED)])
def test_hg_remote_default(repo, expected, shared_datadir):
    repo = shared_datadir / "hg" / repo
    do_test_hg_remote(repo, expected)


@pytest.mark.parametrize(
    "repo, expected",
    [("repo-heptapod", HEPTAPOD_EXPECTED)])
def test_hg_remote_default_push(repo, expected, shared_datadir):
    repo = shared_datadir / "hg" / repo
    with (repo / ".hg" / "hgrc").open("w") as hgrc:
        hgrc.writelines([
            "[paths]\n"
            f"default-push = {expected.repo_url}\n"
        ])
    do_test_hg_remote(repo, expected)
