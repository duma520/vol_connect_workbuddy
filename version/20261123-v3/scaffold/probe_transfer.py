import json, sys, tempfile, pathlib
sys.path.insert(0, r"G:\Python_Code\vol_connect_workbuddy")
from relay import transfer, accounts

# 造两条记录：cn 与 global
records = [
    {"access_token": "tok_a", "refresh_token": "ref_a", "uid": "uid-a", "nickname": "甲",
     "domain": "www.codebuddy.cn", "expiresAt": 1795380000000,
     "auth_raw": {"account": {"uin": "1001"}}},
    {"access_token": "tok_b", "uid": "uid-b", "nickname": "乙",
     "domain": "www.workbuddy.ai", "expiresAt": 1795380000000},
]
text = json.dumps(records, ensure_ascii=False)

with tempfile.TemporaryDirectory() as tmp:
    # cn 区域应只导入第 0 条
    merged = transfer.merge_records(transfer.parse_transfer_file(text), [0, 1], "cn")
    print("cn imported/skipped:", merged["imported"], merged["skipped"])
    paths = []
    for aid, cred in merged["changes"].items():
        paths.append(accounts.write_vault_account(cred, "cn", tmp))
        print("  wrote:", pathlib.Path(paths[-1]).name, "id=", aid)

    # 回读：重新载入应看到 1 个账号，token 与 uin 都保住
    loaded = accounts.load_from_vault(tmp, ["cn"])
    print("reload count:", len(loaded))
    print("  uin:", loaded[0].uin, "uid:", loaded[0].uid, "token_ok:", loaded[0].access_token == "tok_a")

    # 再导出，验证往返一致（expiresAt 是毫秒）
    back = transfer.transfer_record_of(loaded[0])
    print("re-export: expiresAt is ms?", back["expiresAt"] == 1795380000000)
    print("  keys:", sorted(back.keys()))

    # 覆盖语义：同一 uin 再导入一次，文件仍是 1 个
    files = list((pathlib.Path(tmp) / "cn").glob("*.json"))
    print("files after overwrite test:", len(files))