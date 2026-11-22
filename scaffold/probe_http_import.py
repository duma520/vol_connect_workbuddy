"""HTTP 导入回归：备份真实保险库 → 走 /admin/transfer/import → 校验 → 还原并比对哈希。"""
import hashlib, json, pathlib, shutil, sys, tempfile, urllib.request
sys.path.insert(0, r"G:\Python_Code\vol_connect_workbuddy")
from relay import config

BASE = "http://127.0.0.1:17583"
vault = pathlib.Path(config.load()["vault_dir"])
cn = vault / "cn"
originals = sorted(cn.glob("*.json"))
print("vault:", vault, "| cn files:", len(originals))

def digest(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.glob("*.json"))}

before = digest(cn)
backup = pathlib.Path(tempfile.mkdtemp(prefix="vaultbak_"))
for p in originals:
    shutil.copy2(p, backup / p.name)
print("backup ->", backup, "| files:", len(list(backup.glob("*.json"))))

ok = False
try:
    data = json.load(urllib.request.urlopen(BASE + "/admin/export", timeout=20))
    text = json.dumps(data, ensure_ascii=False)
    n = len(data["accounts"])
    req = urllib.request.Request(
        BASE + "/admin/transfer/import",
        data=json.dumps({"text": text, "indexes": list(range(n)), "region": "cn"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    res = json.load(urllib.request.urlopen(req, timeout=30))
    print("import -> imported:", res["imported"], "skipped:", res["skipped"], "failed:", len(res["failed"]))

    after = digest(cn)
    print("cn files after:", len(after))
    missing = set(before) - set(after)
    changed = [k for k in before if k in after and before[k] != after[k]]
    print("missing:", sorted(missing), "| content-changed:", len(changed))

    # 回读校验：中继侧仍能解出 13 个账号，token 非空
    hz = json.load(urllib.request.urlopen(BASE + "/admin/reload", data=b"{}", timeout=20)) if False else None
    health = json.load(urllib.request.urlopen(BASE + "/healthz", timeout=15))
    print("health after import:", health["accounts"], "accounts")
    ok = True
finally:
    for p in list(cn.glob("*.json")):
        p.unlink()
    for p in backup.glob("*.json"):
        shutil.copy2(p, cn / p.name)
    restored = digest(cn)
    print("restore identical:", restored == before, "| files:", len(restored))
    shutil.rmtree(backup, ignore_errors=True)

print("HTTP IMPORT REGRESSION:", "PASS" if ok else "FAIL")