"""widgetcache — a tiny in-memory memoiser (the source of truth for the README)."""

DEFAULT_TTL = 300  # seconds; override per call with ttl=, or globally with --ttl


def cached(key, produce, ttl=DEFAULT_TTL, no_cache=False):
    """Return the stored value for `key` if it's younger than `ttl` seconds,
    otherwise call `produce()`, store it, and return that. `no_cache=True`
    skips the cache for one call."""
    ...
