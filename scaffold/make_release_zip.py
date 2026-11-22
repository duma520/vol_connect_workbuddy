import os, zipfile, pathlib, shutil
src = pathlib.Path(r"G:\Python_Code\vol_connect_workbuddy")
out = pathlib.Path(r"G:\Python_Code\vol_connect_workbuddy\dist")
out.mkdir(exist_ok=True)
zip_path = out / "vol_connect_workbuddy-v1.1.0.zip"
if zip_path.exists():
    zip_path.unlink()

TOP = "vol_connect_workbuddy-v1.1.0"
files = []
for folder in ("relay", "gui", "presets"):
    for p in sorted((src / folder).rglob("*.py")) + sorted((src / folder).rglob("*.json")) + sorted((src / folder).rglob("*.txt")) + sorted((src / folder).rglob("*.toml")) + sorted((src / folder).rglob("*.model")):
        if "__pycache__" in p.parts:
            continue
        files.append(p)
for name in ("README.md", "软件升级迭代记录.md", "LICENSE", "requirements.txt",
             "启动中继.bat", "启动中继_无界面.bat", "test_e2e.py"):
    p = src / name
    if p.exists():
        files.append(p)

files = sorted(set(files))
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for p in files:
        arc = TOP + "/" + p.relative_to(src).as_posix()
        zf.write(p, arc)

print("files in zip:", len(files))
print("zip bytes:", zip_path.stat().st_size)
with zipfile.ZipFile(zip_path) as zf:
    names = zf.namelist()
print("entries:", len(names))
for n in names[:8]:
    print("  ", n)
bad = [n for n in names if n.startswith(TOP + "/scaffold") or n.startswith(TOP + "/version") or "config.json" in n or "__pycache__" in n]
print("forbidden entries:", bad)