import time
import threading
from collections import OrderedDict


class TTLCache:
    """Simple thread-safe TTL cache with size bound.

    Items expire after ttl_seconds. Evicts LRU when maxsize exceeded.
    """

    def __init__(self, ttl_seconds: int = 6 * 3600, maxsize: int = 512):
        self.ttl = max(60, int(ttl_seconds))
        self.maxsize = max(16, int(maxsize))
        self._lock = threading.Lock()
        self._data = OrderedDict()

    def get(self, key):
        now = time.time()
        with self._lock:
            if key not in self._data:
                return None
            value, ts = self._data.pop(key)
            if now - ts > self.ttl:
                return None
            # mark as recently used
            self._data[key] = (value, ts)
            return value

    def set(self, key, value):
        now = time.time()
        with self._lock:
            if key in self._data:
                self._data.pop(key)
            self._data[key] = (value, now)
            if len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def clear(self):
        with self._lock:
            self._data.clear()
