"""One shared requests session with retries, used by every upstream provider."""
from __future__ import annotations

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from routing.exceptions import UpstreamError

_session: requests.Session | None = None


def get_session() -> requests.Session:
    global _session
    if _session is None:
        session = requests.Session()
        retry = Retry(
            total=2,
            backoff_factor=0.4,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
        adapter = HTTPAdapter(max_retries=retry, pool_maxsize=16)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers["User-Agent"] = settings.GEOCODER_USER_AGENT
        _session = session
    return _session


def get_json(provider: str, url: str, params: dict | None = None, **kwargs) -> dict:
    try:
        response = get_session().get(
            url, params=params, timeout=settings.UPSTREAM_TIMEOUT_SECONDS, **kwargs
        )
        response.raise_for_status()
        return response.json()
    except requests.Timeout as exc:
        raise UpstreamError(provider, "The provider timed out. Please try again.") from exc
    except requests.RequestException as exc:
        raise UpstreamError(provider, f"Request failed: {exc}") from exc
    except ValueError as exc:
        raise UpstreamError(provider, "The provider returned a malformed response.") from exc
