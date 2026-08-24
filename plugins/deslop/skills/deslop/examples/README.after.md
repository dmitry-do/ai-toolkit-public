# widgetcache

widgetcache memoises a function call in memory, keyed by a `key` you supply: within the TTL a
repeated call returns the stored value instead of running the function again.

Values are cached for five minutes by default (`DEFAULT_TTL = 300`); pass `ttl=` to change it for
one call, `--ttl` to change the default, or `no_cache=True` to skip the cache for a single call.
