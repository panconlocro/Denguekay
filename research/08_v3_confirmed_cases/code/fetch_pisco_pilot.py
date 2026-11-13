"""Extract the March 2020 Piura pilot from the two published PISCOt NetCDFs."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import io
from time import time_ns
import requests
import h5py

class Ranged(io.RawIOBase):
    def __init__(self, url, block=1024*1024):
        self.session = requests.Session()
        self.base_url = url
        first = self.session.get(f"{url}?pilot={time_ns()}", headers={'Range':'bytes=0-15'},timeout=(12,30),stream=True)
        with first:
            if first.status_code != 206:
                raise ValueError(f"Figshare response {first.status_code} for range")
            self.length = int(first.headers['Content-Range'].rsplit('/',1)[1])
            self.url = first.url
        self.block = block
        self.pos = 0
        self.cache = {}
        self.bytes = 0

    def seek(self, offset, whence=0):
        self.pos = [0, self.pos, self.length][whence] + offset
        return self.pos

    def tell(self):
        return self.pos

    def readable(self):
        return True

    def seekable(self):
        return True

    def read(self, n=-1):
        size = min(self.length-self.pos, n if n>=0 else self.length)
        out=bytearray(size)
        self.readinto(out)
        return bytes(out)

    def readinto(self, dest):
        count = min(len(dest), self.length-self.pos)
        i = 0
        while i < count:
            k = self.pos//self.block
            idx = self.pos%self.block
            if k not in self.cache:
                lower = k*self.block
                upper = min(lower+self.block,self.length)-1
                if self.bytes+(upper-lower+1)>90*1024**2:
                    raise ValueError("Presupuesto de 90 MiB excedido")
                r=self.session.get(self.url, headers={'Range':f'bytes={lower}-{upper}'}, timeout=(12,30),stream=True)
                if r.status_code == 403:
                    err = r.text[:550]
                    r.close()
                    if "expired" not in err.lower():
                        raise ValueError("Figshare rechazó la lectura parcial con HTTP 403")
                    r = self.session.get(f"{self.base_url}?pilot={time_ns()}",
                                         headers={"Range": f"bytes={lower}-{upper}"}, timeout=(12,30), stream=True)
                    self.url = r.url
                with r:
                    actual=r.headers.get('Content-Range','')
                    if r.status_code!=206 or actual != f'bytes {lower}-{upper}/{self.length}':
                        raise ValueError(f"Figshare status={r.status_code}, range={actual}")
                    self.cache[k]=r.content
                self.bytes+=len(self.cache[k])
            block = self.cache[k]
            n = min(count-i,len(block)-idx)
            if n<=0: raise ValueError("Bloque sin bytes")
            dest[i:i+n]=block[idx:idx+n]
            i+=n
            self.pos+=n
        return count

import numpy as np
import pandas as pd

START = "2020-03-15"
FILES = {"tmax": 36735519, "tmin": 36762309}


def extract(item, folder):
    field, file_id = item
    url = f"https://ndownloader.figshare.com/files/{file_id}"
    remote = Ranged(url)
    try:
        with h5py.File(remote, "r") as source:
            lats = source["latitude"][:]
            lons = source["longitude"][:]
            dates = pd.Timestamp("2020-01-01") + pd.to_timedelta(source["time"][:], unit="D")
            ri = np.flatnonzero((lats >= -6.6) & (lats <= -3.9))
            ci = np.flatnonzero((lons >= -81.6) & (lons <= -79.0))
            di = np.flatnonzero(dates.isin(pd.date_range(START, periods=7)))
            if len(di) != 7 or not len(ri) or not len(ci):
                raise ValueError("Fechas o coordenadas fuera de PISCOt")
            sub = source[field][di.min():di.max()+1, ri.min():ri.max()+1, ci.min():ci.max()+1]
            np.savez_compressed(folder / f"pisco_{field}.npz", dates=dates[di].astype(str).to_numpy(dtype=str),
                                latitude=lats[ri], longitude=lons[ci], values=sub, bytes_downloaded=remote.bytes,
                                url=url)
            print(field,sub.shape,'bytes remotos',remote.bytes,flush=True)
    finally:
        remote.session.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(extract, item, args.output) for item in FILES.items()]
        for task in tasks:
            task.result()


if __name__ == "__main__":
    main()
