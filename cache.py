import os
from typing import Any, Callable, Dict, Optional

try:
    import bmemcached  # type: ignore
except Exception:  # pragma: no cover - handled by using a no-op cache
    bmemcached = None


CacheCreator = Callable[[], Any]

_DEFAULT_TTL_SECONDS = 300
_NAMESPACE = "shiftmgmt:v1"


class _BaseCache:
    """Minimal cache interface used by the rest of the app."""

    def get(self, key: str) -> Any:  # pragma: no cover - overridden
        raise NotImplementedError

    def set(self, key: str, value: Any, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> bool:  # pragma: no cover - overridden
        raise NotImplementedError

    def delete(self, key: str) -> bool:  # pragma: no cover - overridden
        raise NotImplementedError

    def get_or_set(
        self,
        key: str,
        creator: CacheCreator,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> Any:
        """
        Convenience helper to memoize an expensive computation.

        The creator is only called on cache miss. If creator() returns None,
        the value is *not* cached (so that None can represent 'no data').
        """
        existing = self.get(key)
        if existing is not None:
            return existing

        value = creator()
        if value is not None:
            self.set(key, value, ttl_seconds=ttl_seconds)
        return value


class _NoOpCache(_BaseCache):
    """
    Fallback cache used when bmemcached is not installed or MEMCACHEDCLOUD_*
    variables are not configured. Behaves like an always-miss cache.
    """

    def get(self, key: str) -> Any:
        return None

    def set(self, key: str, value: Any, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> bool:
        return False

    def delete(self, key: str) -> bool:
        return False


class _BMemcachedCache(_BaseCache):
    """Thin wrapper around bmemcached.Client that normalizes errors."""

    def __init__(self, client: "bmemcached.Client") -> None:
        self._client = client

    def get(self, key: str) -> Any:
        try:
            return self._client.get(key)
        except Exception:
            # Treat backend errors as a cache miss so they never break requests.
            return None

    def set(self, key: str, value: Any, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> bool:
        try:
            # bmemcached uses the 'time' argument for TTL in seconds.
            return bool(self._client.set(key, value, time=ttl_seconds))
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        try:
            return bool(self._client.delete(key))
        except Exception:
            return False


def _build_client() -> _BaseCache:
    """
    Initialize the cache client using MEMCACHEDCLOUD_* config vars.

    Falls back to a no-op cache if configuration or the client library
    is not available (for example, in local development).
    """
    servers = os.environ.get("MEMCACHEDCLOUD_SERVERS")
    username = os.environ.get("MEMCACHEDCLOUD_USERNAME")
    password = os.environ.get("MEMCACHEDCLOUD_PASSWORD")

    if not (servers and username and password and bmemcached):
        return _NoOpCache()

    # MEMCACHEDCLOUD_SERVERS is a comma-separated list.
    server_list = [s.strip() for s in servers.split(",") if s.strip()]
    if not server_list:
        return _NoOpCache()

    try:
        client = bmemcached.Client(server_list, username, password)
    except Exception:
        # If we cannot connect for any reason, degrade gracefully.
        return _NoOpCache()

    return _BMemcachedCache(client)


def make_key(*parts: Any) -> str:
    """
    Build a namespaced cache key composed of simple parts.

    Example:
        make_key(\"policy\", term_id) -> \"shiftmgmt:v1:policy:3\"
    """
    str_parts = [str(p) for p in parts]
    return ":".join([_NAMESPACE, *str_parts])


def policy_key(term_id: int) -> str:
    return make_key("policy", term_id)


def student_summary_key(student_id: int, week_start_iso: str) -> str:
    return make_key("student_summary", student_id, week_start_iso)


def schedule_preview_key(term_id: int, week_start_iso: Optional[str] = None) -> str:
    if week_start_iso:
        return make_key("schedule_preview", term_id, week_start_iso)
    return make_key("schedule_preview", term_id)


def outputs_index_key() -> str:
    """Key for small aggregate stats on the Outputs landing page."""
    return make_key("outputs", "index", "summary")


def all_students_weeks_key() -> str:
    """Key for the list of all week start dates used on the all-students view."""
    return make_key("outputs", "all_students", "weeks")


def invalidate_term(term_id: int) -> None:
    """
    Invalidate cached data that is scoped to a term.

    For now we delete known term-scoped keys. As we add more term-level
    caches, extend this helper rather than scattering deletes everywhere.
    """
    # Currently only schedule previews are term-scoped. Index summaries and
    # student summaries are mostly date / student scoped and rely on TTL.
    cache.delete(schedule_preview_key(term_id))


def invalidate_student(student_id: int, week_start_iso: Optional[str] = None) -> None:
    """
    Invalidate student-specific cached summaries.

    If week_start_iso is provided we clear that specific week; otherwise we
    rely on TTL-based expiry.
    """
    if week_start_iso:
        cache.delete(student_summary_key(student_id, week_start_iso))


# Global cache instance used throughout the app.
cache: _BaseCache = _build_client()


