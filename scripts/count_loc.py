"""Count project source lines with separate implementation, config, migration and test buckets."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SKIP={"node_modules","dist",".venv","venv","__pycache__",".pytest_cache"}
EXTS={".py",".js",".jsx",".ts",".tsx",".css",".html"}

def count(path):
    lines=path.read_text(encoding="utf-8-sig").splitlines()
    return sum(bool(line.strip()) and not line.lstrip().startswith(("#","//","/*","*")) for line in lines)

def main():
    runtime={}; feature={"FastAPI":{},"DRF":{}}; configuration={}; migrations={}; tests={}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in EXTS or any(part in SKIP for part in path.parts): continue
        rel=path.relative_to(ROOT).as_posix(); n=count(path)
        if "/test" in rel or rel.startswith("tests/") or path.name.startswith("test_"):
            tests[rel]=n; continue
        if "/migrations/" in rel:
            migrations[rel]=n; continue
        if rel.startswith("backend/fastapi_app/"):
            runtime[rel]=n; feature["FastAPI"][rel]=n
        elif rel.startswith("backend/drf_app/products/") and path.name in {"models.py","serializers.py","views.py","exceptions.py"}:
            runtime[rel]=n; feature["DRF"][rel]=n
        elif rel.startswith(("frontend/src/","frontend/index.html")):
            runtime[rel]=n
        elif rel.startswith("backend/drf_app/") or rel.startswith("scripts/"):
            configuration[rel]=n
    report={"method":"Count nonblank source lines; omit standalone comment lines. Runtime application includes FastAPI source, DRF product implementation, and shared frontend. DRF config/boilerplate, migrations, tests, scripts, generated assets, dependencies, caches, databases and README are separate or excluded.","total_application_loc":sum(runtime.values()),"runtime_files":runtime,"framework_feature_loc":{k:{"files":v,"total":sum(v.values()),"note":"FastAPI main.py includes app setup and route code; DRF bucket includes product models, serializers, views and exception formatting."} for k,v in feature.items()},"framework_configuration_and_scripts_loc":sum(configuration.values()),"configuration_files":configuration,"generated_migration_loc":sum(migrations.values()),"migration_files":migrations,"test_loc_excluded_from_application_total":sum(tests.values()),"test_files":tests}
    out=ROOT/"quality-results"; out.mkdir(exist_ok=True)
    (out/"loc.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    public=ROOT/"frontend/public/quality-results"; public.mkdir(parents=True,exist_ok=True)
    (public/"loc.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))

if __name__=="__main__": main()
