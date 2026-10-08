import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status

from app.core.security import get_current_user


class RateLimiter:
    """Fenetre glissante en memoire (un seul processus).

    A remplacer par un stockage partage (Redis) quand l'API tourne sur plusieurs instances.
    """

    def __init__(self, name: str, limit: int, window_seconds: int):
        self.name = name
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                retry = int(self.window - (now - hits[0])) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Trop de requetes, reessayez plus tard.",
                    headers={"Retry-After": str(retry)},
                )
            hits.append(now)

    def by_ip(self):
        def dependency(request: Request) -> None:
            self._check(f"ip:{request.client.host if request.client else 'inconnu'}")
        return Depends(dependency)

    def by_user(self):
        def dependency(current_user=Depends(get_current_user)) -> None:
            self._check(f"user:{current_user.id}")
        return Depends(dependency)


login_limiter = RateLimiter("login", limit=10, window_seconds=60)
inscription_limiter = RateLimiter("inscription", limit=5, window_seconds=3600)
extraction_limiter = RateLimiter("extraction", limit=20, window_seconds=60)
analyse_limiter = RateLimiter("analyse", limit=30, window_seconds=3600)
generation_limiter = RateLimiter("generation", limit=15, window_seconds=3600)
import_cv_limiter = RateLimiter("import_cv", limit=10, window_seconds=3600)
