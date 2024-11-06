import pytest

from godot_asset_uploader.vcs import (
    guess_repo_provider, guess_issues_url, guess_download_url,
)

from vcs_urls import (
    GITHUB_EXPECTED,
    BITBUCKET_EXPECTED,
    GITLAB_EXPECTED,
    GITLAB_SELF_HOSTED_EXPECTED,
    HEPTAPOD_EXPECTED,
)

@pytest.mark.parametrize(
    "expected",
    [GITHUB_EXPECTED,
     BITBUCKET_EXPECTED,
     GITLAB_EXPECTED,
     GITLAB_SELF_HOSTED_EXPECTED,
     HEPTAPOD_EXPECTED])
def test_provider_url(expected):
    for url in [expected.repo_url, expected.ssh_url]:
        assert guess_repo_provider(url) == expected.provider
        assert guess_issues_url(url) == expected.issues_url
        assert guess_download_url(url, expected.commit) == expected.download_url
