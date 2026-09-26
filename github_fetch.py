"""README fetch for public GitHub repos (Blueprint Sections 3.2, 4 step 2, 6.4, 8.1).

Standalone: depends only on `requests`. Tries README variants on `main`, then `master`,
via raw.githubusercontent.com. No auth, so only public repos work.
"""
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

BRANCHES = ("main", "master")
README_FILENAMES = ("README.md", "README", "readme.md")
RAW_URL = "https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filename}"
REPO_PAGE_URL = "https://github.com/{owner}/{repo}"
TIMEOUT_SECONDS = 10

# GitHub's documented character sets for user/org and repository names.
_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


class GitHubFetchError(Exception):
    """Base class. `str(err)` is a user-facing, actionable message."""


class InvalidRepoURLError(GitHubFetchError):
    pass


class RepoNotFoundError(GitHubFetchError):
    pass


class ReadmeNotFoundError(GitHubFetchError):
    pass


class RateLimitedError(GitHubFetchError):
    pass


class NetworkError(GitHubFetchError):
    pass


@dataclass(frozen=True)
class FetchedReadme:
    owner: str
    repo: str
    branch: str
    filename: str
    source_url: str
    text: str


def parse_repo_url(url: str) -> tuple[str, str]:
    """Return (owner, repo) from a github.com repo URL, or raise InvalidRepoURLError."""
    cleaned = (url or "").strip()
    if not cleaned:
        raise InvalidRepoURLError("Please enter a GitHub repository URL.")
    if not re.match(r"^https?://", cleaned, re.IGNORECASE):
        cleaned = "https://" + cleaned
    parsed = urlparse(cleaned)
    host = (parsed.hostname or "").lower()
    if host not in ("github.com", "www.github.com"):
        raise InvalidRepoURLError(
            f"'{url}' is not a github.com URL. Use the form https://github.com/owner/repo."
        )
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise InvalidRepoURLError(
            f"'{url}' doesn't include both an owner and a repository name. "
            "Use the form https://github.com/owner/repo."
        )
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    if not _OWNER_RE.match(owner) or not _REPO_RE.match(repo) or repo in (".", ".."):
        raise InvalidRepoURLError(
            f"'{owner}/{repo}' isn't a valid GitHub owner/repository name."
        )
    return owner, repo


def _get(session: requests.Session, url: str) -> requests.Response:
    try:
        response = session.get(url, timeout=TIMEOUT_SECONDS)
    except requests.Timeout:
        raise NetworkError("GitHub didn't respond in time. Check your connection and try again.") from None
    except requests.RequestException as exc:
        raise NetworkError(f"Couldn't reach GitHub ({type(exc).__name__}). Check your connection and try again.") from None
    if _is_rate_limited(response):
        raise RateLimitedError(
            "GitHub is rate-limiting requests right now. Wait a minute and try again, "
            "or paste the README text directly instead."
        )
    return response


def _is_rate_limited(response: requests.Response) -> bool:
    if response.status_code == 429:
        return True
    return response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0"


def fetch_readme(url: str, session: requests.Session | None = None) -> FetchedReadme:
    """Fetch the README for a public GitHub repo. Raises a GitHubFetchError subclass on failure."""
    owner, repo = parse_repo_url(url)
    session = session or requests.Session()

    for branch in BRANCHES:
        for filename in README_FILENAMES:
            raw_url = RAW_URL.format(owner=owner, repo=repo, branch=branch, filename=filename)
            response = _get(session, raw_url)
            if response.status_code == 200:
                return FetchedReadme(owner, repo, branch, filename, raw_url, response.text)
            if response.status_code != 404:
                raise NetworkError(
                    f"GitHub returned an unexpected error (HTTP {response.status_code}) "
                    f"for {raw_url}. Try again shortly."
                )

    # Every raw lookup 404'd: raw.githubusercontent.com can't tell a missing repo from a
    # missing README, so check whether the repo page itself exists.
    page = _get(session, REPO_PAGE_URL.format(owner=owner, repo=repo))
    if page.status_code == 404:
        raise RepoNotFoundError(
            f"Repository '{owner}/{repo}' wasn't found. Check the spelling; "
            "private repositories aren't supported."
        )
    raise ReadmeNotFoundError(
        f"No README ({', '.join(README_FILENAMES)}) was found in '{owner}/{repo}' on the "
        f"{' or '.join(BRANCHES)} branch. If the repo uses another default branch or "
        "README name, paste the text directly instead."
    )
