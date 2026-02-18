# AEMET OpenData API limits investigation

## What was investigated

I attempted to verify AEMET OpenData request limits from public internet sources (official documentation and public pages).

## Result in this environment

The current execution environment blocks outbound web access through the configured proxy (`CONNECT tunnel failed, response 403`), so live verification from AEMET pages could not be completed here.

## Practical limits strategy for this project

Until limits are confirmed from the official portal, this service should assume conservative protection:

1. Keep SQLite caching as the primary anti-overload mechanism.
2. Avoid repeated requests for the same station/time window.
3. Add backoff/retry on HTTP `429` and 5xx responses.
4. Throttle outbound calls per station (token bucket/leaky bucket in-memory or distributed lock if scaled).
5. Log rate-limit-related headers if present (for example `Retry-After`, `X-RateLimit-*`).

## How to verify limits outside this restricted environment

Use the helper script in `scripts/check_aemet_limits.sh` from a network with internet access:

- Checks basic connectivity and response headers.
- Sends a short burst of requests and counts status codes.
- Prints any rate-limit headers returned by upstream.

```bash
AEMET_API_KEY="..." scripts/check_aemet_limits.sh
```

## Notes

- AEMET may enforce limits by API key, IP, endpoint type, or temporary anti-abuse controls.
- Validate both: metadata endpoint and redirected `datos` URL behavior.
