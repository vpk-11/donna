from concurrent.futures import ThreadPoolExecutor

from config import settings

# ponytail: a hung scan keeps its worker thread until it returns; the caller is unblocked at the timeout.
_pool = ThreadPoolExecutor(max_workers=4)


def scan_with_timeout(scanner, **kwargs):
    """Run scanner.scan in a worker thread. Raises TimeoutError after settings.scanner_timeout_s."""
    return _pool.submit(scanner.scan, **kwargs).result(timeout=settings.scanner_timeout_s)
