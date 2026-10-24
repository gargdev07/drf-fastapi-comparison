"""Run both API suites, cross-contract tests and frontend build; save factual result summary."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def run(label, command, cwd):
    result=subprocess.run(command,cwd=cwd,capture_output=True,text=True)
    output=(result.stdout+"\n"+result.stderr).strip()
    return {"name":label,"command":" ".join(command),"exit_code":result.returncode,"passed":result.returncode==0,"output":output[-5000:]}

def main():
    python=sys.executable
    rows=[
        run("FastAPI and cross-framework contract tests",[python,"-m","pytest","-q","backend/fastapi_app","tests"],ROOT),
        run("Django REST Framework tests",[python,"manage.py","test"],ROOT/"backend/drf_app"),
        run("React production build",["npm.cmd" if os.name == "nt" else "npm","run","build"],ROOT/"frontend"),
    ]
    # A separate count script produces reproducible LOC evidence without counting generated output.
    subprocess.run([python,"scripts/count_loc.py"],cwd=ROOT,check=True,capture_output=True,text=True)
    report={"status":"passed" if all(r["passed"] for r in rows) else "failed","measured_at_utc":datetime.now(timezone.utc).isoformat(),"passed":sum(r["passed"] for r in rows),"failed":sum(not r["passed"] for r in rows),"checks":rows}
    out=ROOT/"quality-results"; out.mkdir(exist_ok=True)
    (out/"latest.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    public=ROOT/"frontend/public/quality-results"; public.mkdir(parents=True,exist_ok=True)
    (public/"latest.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))
    if report["failed"]: raise SystemExit(1)

if __name__=="__main__": main()
