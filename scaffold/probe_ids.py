import json, pathlib, sys
sys.path.insert(0, r"G:\Python_Code\vol_connect_workbuddy")
from relay import config, transfer, accounts
vault = pathlib.Path(config.load()["vault_dir"])
cn = vault / "cn"
print("files in cn:", len(list(cn.glob("*.json"))))
for p in sorted(cn.glob("*.json"))[:20]:
    doc = json.loads(p.read_text(encoding="utf-8"))
    acct = doc.get("account") or {}
    auth = doc.get("auth") or {}
    print("file=%-42s accountId=%-38s uin=%-22s uid=%s" % (
        p.stem, str(doc.get("accountId"))[:38], str(acct.get("uin"))[:22], str(acct.get("uid"))[:20]))

print()
print("--- 我们的派生 id 会是什么 ---")
pool = accounts.load_from_vault(str(vault), ["cn"])
for a in pool[:5]:
    print("label=%-20s account_id=%-38s uin=%-20s uid=%s" % (a.label[:20], a.account_id[:38], a.uin[:20], a.uid[:20]))