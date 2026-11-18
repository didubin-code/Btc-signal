"""HTTP with retries, polite pacing and a provenance log (every response's URL, status, size, sha256 and fetch time).
Uses requests, which honours HTTPS_PROXY and REQUESTS_CA_BUNDLE (set in this environment)."""
import datetime, hashlib, json, os, time
import requests

SESSION = requests.Session()
SESSION.headers['User-Agent'] = 'pinradar-validation/1.0 (research; read-only public market data)'
PROV_PATH = None
_last = {}


def init(prov_path):
    global PROV_PATH
    PROV_PATH = prov_path
    os.makedirs(os.path.dirname(prov_path) or '.', exist_ok=True)


def _log(url, params, status, body):
    if not PROV_PATH:
        return
    rec = {'fetchedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'url': url, 'params': params or {},
           'status': status, 'bytes': len(body or b''), 'sha256': hashlib.sha256(body or b'').hexdigest()}
    with open(PROV_PATH, 'a') as f:
        f.write(json.dumps(rec) + '\n')


def get(url, params=None, host_min_interval=0.12, retries=7, timeout=60, ok_404=False):
    """GET with pacing per host (seconds between requests) and exponential backoff on 429 / 5xx / network errors."""
    host = url.split('/')[2]
    for i in range(retries):
        wait = _last.get(host, 0) + host_min_interval - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.time()
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            _log(r.url, params, r.status_code, r.content)
            if r.status_code == 404 and ok_404:
                return r
            if r.status_code == 429 or r.status_code >= 500:
                raise RuntimeError('HTTP %d' % r.status_code)
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001  (retry everything transient; the last error propagates)
            if i == retries - 1:
                raise
            time.sleep(min(90, 2 ** i))
