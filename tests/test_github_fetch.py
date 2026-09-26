"""Offline tests for github_fetch: a fake session stands in for the network."""
import pytest
import requests

from github_fetch import (
    InvalidRepoURLError,
    NetworkError,
    RateLimitedError,
    ReadmeNotFoundError,
    RepoNotFoundError,
    fetch_readme,
    parse_repo_url,
)


class FakeResponse:
    def __init__(self, status_code, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


class FakeSession:
    """Returns responses by exact URL; anything unlisted is a 404. Records calls."""

    def __init__(self, routes=None, raise_exc=None):
        self.routes = routes or {}
        self.raise_exc = raise_exc
        self.calls = []

    def get(self, url, timeout):
        self.calls.append(url)
        if self.raise_exc:
            raise self.raise_exc
        return self.routes.get(url, FakeResponse(404))


RAW = "https://raw.githubusercontent.com/octo/repo"
PAGE = "https://github.com/octo/repo"


@pytest.mark.parametrize("url", [
    "https://github.com/octo/repo",
    "http://github.com/octo/repo/",
    "github.com/octo/repo",
    "https://www.github.com/octo/repo.git",
    "https://github.com/octo/repo/tree/main/src",
    "  https://github.com/octo/repo  ",
])
def test_parse_valid_urls(url):
    assert parse_repo_url(url) == ("octo", "repo")


@pytest.mark.parametrize("url", [
    "", "   ", "https://gitlab.com/octo/repo", "https://github.com/octo",
    "https://github.com/", "not a url", "https://github.com/bad_owner!/repo",
])
def test_parse_invalid_urls(url):
    with pytest.raises(InvalidRepoURLError):
        parse_repo_url(url)


def test_first_variant_on_main():
    session = FakeSession({f"{RAW}/main/README.md": FakeResponse(200, "# Hello")})
    result = fetch_readme("https://github.com/octo/repo", session=session)
    assert (result.branch, result.filename, result.text) == ("main", "README.md", "# Hello")
    assert session.calls == [f"{RAW}/main/README.md"]


def test_falls_back_to_master_and_later_variant():
    session = FakeSession({f"{RAW}/master/readme.md": FakeResponse(200, "lower")})
    result = fetch_readme("https://github.com/octo/repo", session=session)
    assert (result.branch, result.filename) == ("master", "readme.md")
    assert session.calls == [
        f"{RAW}/main/README.md", f"{RAW}/main/README", f"{RAW}/main/readme.md",
        f"{RAW}/master/README.md", f"{RAW}/master/README", f"{RAW}/master/readme.md",
    ]


def test_repo_not_found():
    with pytest.raises(RepoNotFoundError, match="octo/repo"):
        fetch_readme("https://github.com/octo/repo", session=FakeSession())


def test_readme_not_found_when_repo_exists():
    session = FakeSession({PAGE: FakeResponse(200, "<html>")})
    with pytest.raises(ReadmeNotFoundError, match="main or master"):
        fetch_readme("https://github.com/octo/repo", session=session)


@pytest.mark.parametrize("response", [
    FakeResponse(429),
    FakeResponse(403, headers={"X-RateLimit-Remaining": "0"}),
])
def test_rate_limited(response):
    session = FakeSession({f"{RAW}/main/README.md": response})
    with pytest.raises(RateLimitedError):
        fetch_readme("https://github.com/octo/repo", session=session)


def test_unexpected_status_is_not_reported_as_missing():
    session = FakeSession({f"{RAW}/main/README.md": FakeResponse(500)})
    with pytest.raises(NetworkError, match="HTTP 500"):
        fetch_readme("https://github.com/octo/repo", session=session)


def test_connection_failure():
    session = FakeSession(raise_exc=requests.ConnectionError("boom"))
    with pytest.raises(NetworkError, match="Couldn't reach GitHub"):
        fetch_readme("https://github.com/octo/repo", session=session)
