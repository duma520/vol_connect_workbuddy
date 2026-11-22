import json, sys, urllib.request
sys.path.insert(0, r"G:\Python_Code\vol_connect_workbuddy")
from relay import transfer

cases = [
    ("workbuddy.ai", "global"), ("www.workbuddy.ai", "global"),
    ("codebuddy.ai", "global"), ("www.codebuddy.ai", "global"),
    ("workbuddy.cn", "cn"), ("www.codebuddy.cn", "cn"),
    ("copilot.tencent.com", "cn"), ("x.copilot.tencent.com", "cn"),
    ("codebuddy.cn.evil.com", None), ("evil.com", None), ("", None),
    ("WORKBUDDY.AI", "global"), ("  www.codebuddy.cn  ", "cn"),
]
bad = 0
for domain, want in cases:
    got = transfer.region_of_domain(domain)
    ok = got == want
    bad += 0 if ok else 1
    print(("OK  " if ok else "FAIL"), repr(domain), "->", got, "want", want)
print("failures:", bad)

# 真实导出文件的 domain 分布
data = json.load(urllib.request.urlopen("http://127.0.0.1:17583/admin/export", timeout=15))
from collections import Counter
counts = Counter()
for rec in data["accounts"]:
    d = rec.get("domain") or ""
    counts[(d, transfer.region_of_domain(d))] += 1
print("real export domain -> region:")
for key, n in counts.items():
    print("  ", key, "x", n)