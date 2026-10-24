#!/usr/bin/env python3
"""Run repeatable, local HTTP benchmarks on isolated, identically seeded SQLite databases."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SEED = [
    {"title":"Classic cotton tee","description":"Everyday heavyweight cotton t-shirt","price":24.5,"category":"Clothing","stock":38,"image":"https://dummyjson.com/image/400x300"},
    {"title":"Studio headphones","description":"Over-ear wireless headphones","price":89.0,"category":"Electronics","stock":12,"image":"https://dummyjson.com/image/400x300"},
    {"title":"Ceramic pour-over set","description":"Hand-finished coffee dripper and cup","price":42.0,"category":"Home","stock":21,"image":"https://dummyjson.com/image/400x300"},
]

def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

def get_json(url):
    started = time.perf_counter()
    with urlopen(Request(url, headers={"Accept":"application/json"}), timeout=8) as response:
        status, payload = response.status, response.read()
    return (time.perf_counter()-started)*1000, status, json.loads(payload)

def summarize(url, warmups, requests, concurrency, trials):
    for _ in range(warmups):
        get_json(url)
    trial_rows, all_latencies = [], []
    for _ in range(trials):
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            rows = list(pool.map(lambda _: get_json(url), range(requests)))
        elapsed = time.perf_counter() - started
        latencies = [row[0] for row in rows]
        if any(row[1] != 200 for row in rows):
            raise RuntimeError(f"Unexpected HTTP status from {url}")
        all_latencies.extend(latencies)
        trial_rows.append({"mean_latency_ms":round(statistics.mean(latencies),3),"median_latency_ms":round(statistics.median(latencies),3),"p95_latency_ms":round(sorted(latencies)[min(len(latencies)-1,int(len(latencies)*.95))],3),"requests_per_second":round(len(latencies)/elapsed,2),"wall_seconds":round(elapsed,4)})
    elapsed_total = sum(t["wall_seconds"] for t in trial_rows)
    ordered = sorted(all_latencies)
    return {"url":url,"sample_count":len(all_latencies),"mean_latency_ms":round(statistics.mean(all_latencies),3),"median_latency_ms":round(statistics.median(all_latencies),3),"p95_latency_ms":round(ordered[min(len(ordered)-1,int(len(ordered)*.95))],3),"requests_per_second":round(len(all_latencies)/elapsed_total,2),"trials":trial_rows}

def versions():
    packages = ["fastapi","uvicorn","httpx","Django","djangorestframework","pydantic"]
    result = {}
    for package in packages:
        try: result[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: result[package] = "not installed"
    return result

def wait_ready(process, url):
    until = time.monotonic()+25
    while time.monotonic() < until:
        if process.poll() is not None:
            raise RuntimeError("Benchmark server exited before becoming ready")
        try:
            get_json(url)
            return
        except Exception:
            time.sleep(.25)
    raise TimeoutError(f"Server did not become ready: {url}")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=60, help="requests per trial per route")
    parser.add_argument("--warmups", type=int, default=8, help="warm-up requests per route and framework")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--no-start", action="store_true", help="benchmark already-running servers at --fastapi and --drf")
    parser.add_argument("--fastapi", default="http://127.0.0.1:8000")
    parser.add_argument("--drf", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    if min(args.requests,args.trials,args.concurrency) < 1 or args.warmups < 0: parser.error("counts must be positive; warmups may be zero")
    procs=[]
    with tempfile.TemporaryDirectory(prefix="imad-benchmark-") as temp:
        try:
            urls={"fastapi":args.fastapi.rstrip("/"),"drf":args.drf.rstrip("/")}
            db_paths={key:str(Path(temp)/f"{key}.sqlite3") for key in urls}
            if not args.no_start:
                env=os.environ.copy(); env["FASTAPI_DB_PATH"]=db_paths["fastapi"]; env["PYTHONPATH"]=str(ROOT/"backend/fastapi_app")
                port=free_port(); urls["fastapi"]=f"http://127.0.0.1:{port}"
                procs.append(subprocess.Popen([sys.executable,"-m","uvicorn","main:app","--host","127.0.0.1","--port",str(port),"--workers","1"],cwd=ROOT/"backend/fastapi_app",env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
                denv=os.environ.copy(); denv["DRF_DB_PATH"]=db_paths["drf"]; denv["PYTHONPATH"]=str(ROOT/"backend/drf_app")
                subprocess.run([sys.executable,"manage.py","migrate","--noinput"],cwd=ROOT/"backend/drf_app",env=denv,check=True,capture_output=True,text=True)
                port=free_port(); urls["drf"]=f"http://127.0.0.1:{port}"
                procs.append(subprocess.Popen([sys.executable,"-m","uvicorn","config.asgi:application","--host","127.0.0.1","--port",str(port),"--workers","1"],cwd=ROOT/"backend/drf_app",env=denv,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
                for p,key in zip(procs,urls): wait_ready(p,urls[key]+"/api/v1/health")
            first_ids={}
            data_counts={}
            for key,base in urls.items():
                _,_,listing=get_json(base+"/api/v1/products?limit=100&offset=0")
                actual = [{name: row[name] for name in SEED[0]} for row in listing["data"]]
                if sorted(actual,key=lambda row:row["title"]) != sorted(SEED,key=lambda row:row["title"]):
                    raise RuntimeError(f"{key} database does not contain the expected identical three-product benchmark fixture")
                first_ids[key]=listing["data"][0]["id"]
                data_counts[key]=listing["meta"]["total"]
            measurements={}
            for key,base in urls.items():
                measurements[key]={
                    "health":summarize(base+"/api/v1/health",args.warmups,args.requests,args.concurrency,args.trials),
                    "product_list":summarize(base+"/api/v1/products?limit=20&offset=0",args.warmups,args.requests,args.concurrency,args.trials),
                    "product_retrieve":summarize(base+f"/api/v1/products/{first_ids[key]}",args.warmups,args.requests,args.concurrency,args.trials),
                }
                measurements[key]["database_product_count"]=data_counts[key]
            report={"status":"measured","measured_at_utc":datetime.now(timezone.utc).isoformat(),"environment":{"python":platform.python_version(),"platform":platform.platform(),"packages":versions()},"configuration":{"server":"Uvicorn, one worker per app, local loopback HTTP","database":"separate temporary SQLite files; each seeded with the same 3 product records","cache":"DummyJSON cache not exercised; no upstream requests made","request_count":args.requests,"warmup_count":args.warmups,"trials":args.trials,"concurrency":args.concurrency,"external_calls":False},**measurements}
            output_dir=ROOT/"benchmark-results"; output_dir.mkdir(exist_ok=True)
            (output_dir/"latest.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
            public=ROOT/"frontend/public/benchmark-results"; public.mkdir(parents=True,exist_ok=True)
            (public/"latest.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
            print(json.dumps(report,indent=2)); print(f"Saved {output_dir/'latest.json'}")
        finally:
            for process in procs:
                process.terminate()
            for process in procs:
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill()

def post_json(url, body):
    req=Request(url,data=json.dumps(body).encode(),headers={"Content-Type":"application/json"},method="POST")
    with urlopen(req,timeout=8) as response: return 0,response.status,json.loads(response.read())

if __name__ == "__main__":
    try: main()
    except (OSError,URLError,TimeoutError,subprocess.CalledProcessError,RuntimeError) as error: raise SystemExit(f"Benchmark could not complete: {error}. Report remains pending.") from error
