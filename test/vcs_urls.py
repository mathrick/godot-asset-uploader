from collections import namedtuple

from godot_asset_uploader.vcs import RepoProvider

ExpectedResults = namedtuple(
    "ExpectedResults",
    ["commit", "provider", "repo_url", "ssh_url", "issues_url", "download_url"]
)

GIT_COMMIT = "98e7311dae8377ecb152a3258248e04cd53389c3"
HG_COMMIT = "80393d431e2fc344a3bfdb3bc41096278e429916"

GITHUB_URL = "https://github.com/ihopethisisnotarealusername/dummy-repo"
GITHUB_SSH_URL = "https://github.com/ihopethisisnotarealusername/dummy-repo"
GITHUB_ISSUES_URL = f"{GITHUB_URL}/issues"
GITHUB_DOWNLOAD_URL = f"{GITHUB_URL}/archive/{GIT_COMMIT}.zip"
GITHUB_EXPECTED = ExpectedResults(
    GIT_COMMIT, RepoProvider.GITHUB, GITHUB_URL, GITHUB_SSH_URL,
    GITHUB_ISSUES_URL, GITHUB_DOWNLOAD_URL
)

BITBUCKET_URL = "https://ihopethisisnotarealusername@bitbucket.org/ihopethisisnotarealusername/dummy-repo"
BITBUCKET_SSH_URL = "git@bitbucket.org:ihopethisisnotarealusername/dummy-repo.git"
BITBUCKET_ISSUES_URL = f"{BITBUCKET_URL}/issues"
BITBUCKET_DOWNLOAD_URL = f"{BITBUCKET_URL}/get/{GIT_COMMIT}.zip"
BITBUCKET_EXPECTED = ExpectedResults(
    GIT_COMMIT, RepoProvider.BITBUCKET, BITBUCKET_URL, BITBUCKET_SSH_URL,
    BITBUCKET_ISSUES_URL, BITBUCKET_DOWNLOAD_URL
)

GITLAB_URL = "https://gitlab.com/ihopethisisnotarealusername/dummy-repo"
GITLAB_SSH_URL = "git@gitlab.com:ihopethisisnotarealusername/dummy-repo.git"
GITLAB_ISSUES_URL = f"{GITLAB_URL}/issues"
GITLAB_DOWNLOAD_URL = f"{GITLAB_URL}/archive/{GIT_COMMIT}.zip"
GITLAB_EXPECTED = ExpectedResults(
    GIT_COMMIT, RepoProvider.GITLAB, GITLAB_URL, GITLAB_SSH_URL,
    GITLAB_ISSUES_URL, GITLAB_DOWNLOAD_URL
)

GITLAB_SELF_HOSTED_URL = "https://gitlab.self-hosted.com/ihopethisisnotarealusername/dummy-repo"
GITLAB_SELF_HOSTED_SSH_URL = "git@gitlab.self-hosted.com:ihopethisisnotarealusername/dummy-repo.git"
GITLAB_SELF_HOSTED_ISSUES_URL = f"{GITLAB_SELF_HOSTED_URL}/issues"
GITLAB_SELF_HOSTED_DOWNLOAD_URL = f"{GITLAB_SELF_HOSTED_URL}/archive/{GIT_COMMIT}.zip"
GITLAB_SELF_HOSTED_EXPECTED = ExpectedResults(
    GIT_COMMIT, RepoProvider.GITLAB, GITLAB_SELF_HOSTED_URL, GITLAB_SELF_HOSTED_SSH_URL,
    GITLAB_SELF_HOSTED_ISSUES_URL, GITLAB_SELF_HOSTED_DOWNLOAD_URL
)

HEPTAPOD_URL = "https://foss.heptapod.net/ihopethisisnotarealusername/dummy-repo"
HEPTAPOD_SSH_URL = "ssh://hg@foss.heptapod.net/ihopethisisnotarealusername/dummy-repo"
HEPTAPOD_ISSUES_URL = f"{HEPTAPOD_URL}/issues"
HEPTAPOD_DOWNLOAD_URL = f"{HEPTAPOD_URL}/-/archive/{HG_COMMIT}/{HG_COMMIT}.zip"
HEPTAPOD_EXPECTED = ExpectedResults(
    HG_COMMIT, RepoProvider.HEPTAPOD, HEPTAPOD_URL, HEPTAPOD_SSH_URL,
    HEPTAPOD_ISSUES_URL, HEPTAPOD_DOWNLOAD_URL
)
