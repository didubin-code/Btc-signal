"""Binance spot BTCUSDT 1-second klines from the public archive data.binance.vision (bulk files with published SHA-256 checksums).
UNTESTED until data.binance.vision is reachable. Writes one file per UTC day: <out>/proxy/<YYYY-MM-DD>.f64 = 86,400 float64 LE,
the CLOSE of each second's kline (NaN where Binance published no kline for that second; nothing is filled in), plus
<out>/proxy/<day>.json with row count, gaps and the archive checksum.

  python3 fetch_binance_1s.py --from 2023-10-01 --to 2026-10-16 --out data/sec [--symbol BTCUSDT]

Notes: USDT, not USD (the settlement index is USD); the replay's basis model is learned from Kalshi's official values where they
exist, and the long-horizon proxy study states its outcomes in proxy terms. Spot archive timestamps are in microseconds from 2025."""
import argparse, csv, datetime, hashlib, io, json, math, os, struct, sys, zipfile
import http_util as H

BASE = 'https://data.binance.vision/data/spot'


def day_range(a, b):
    d = datetime.date.fromisoformat(a)
    e = datetime.date.fromisoformat(b)
    while d < e:
        yield d
        d += datetime.timedelta(days=1)


def fetch_zip(url):
    z = H.get(url, host_min_interval=0.05, ok_404=True)
    if z.status_code == 404:
        return None, None
    c = H.get(url + '.CHECKSUM', host_min_interval=0.05, ok_404=True)
    want = c.text.split()[0] if c.status_code == 200 else None
    got = hashlib.sha256(z.content).hexdigest()
    if want and want != got:
        raise RuntimeError('checksum mismatch ' + url)
    return z.content, {'sha256': got, 'checksumPublished': want}


def to_seconds(raw, day):
    t0 = int(datetime.datetime(day.year, day.month, day.day, tzinfo=datetime.timezone.utc).timestamp())
    arr = [math.nan] * 86400
    rows = 0
    zf = zipfile.ZipFile(io.BytesIO(raw))
    with zf.open(zf.namelist()[0]) as f:
        for row in csv.reader(io.TextIOWrapper(f)):
            if not row or not row[0].strip().isdigit():
                continue                                   # header line, if any
            ot = int(row[0])
            sec = ot // 1_000_000 if ot > 10 ** 14 else ot // 1000     # µs (2025+) or ms
            k = sec - t0
            if 0 <= k < 86400:
                arr[k] = float(row[4])
                rows += 1
    return arr, rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--from', dest='frm', required=True)
    p.add_argument('--to', required=True)
    p.add_argument('--out', default='data/sec')
    p.add_argument('--symbol', default='BTCUSDT')
    p.add_argument('--subdir', default='proxy')
    a = p.parse_args()
    od = os.path.join(a.out, a.subdir)
    os.makedirs(od, exist_ok=True)
    H.init(os.path.join(a.out, 'PROVENANCE_binance_%s.ndjson' % a.symbol))
    for d in day_range(a.frm, a.to):
        fn = os.path.join(od, d.isoformat() + '.f64')
        if os.path.exists(fn):
            continue
        url = '%s/daily/klines/%s/1s/%s-1s-%s.zip' % (BASE, a.symbol, a.symbol, d.isoformat())
        raw, meta = fetch_zip(url)
        if raw is None:
            print(d, 'not published', file=sys.stderr)
            continue
        arr, rows = to_seconds(raw, d)
        gaps = sum(1 for x in arr if math.isnan(x))
        with open(fn + '.tmp', 'wb') as f:
            f.write(struct.pack('<86400d', *arr))
        os.replace(fn + '.tmp', fn)
        with open(fn.replace('.f64', '.json'), 'w') as f:
            json.dump({'day': d.isoformat(), 'source': url, 'rows': rows, 'secondsWithoutKline': gaps, **meta}, f)
        print(d, rows, 'rows', gaps, 'empty seconds', file=sys.stderr)


if __name__ == '__main__':
    main()
