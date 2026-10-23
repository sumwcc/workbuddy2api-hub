#!/usr/bin/env python3
"""
import_txt_accounts.py
批量解析微信导出的 手机号----AccessToken----RefreshToken 格式文本账号，并导入到 WorkBuddy Hub 中。
"""

import os
import sys
import json
import base64
import argparse
import glob
import subprocess
import time

def decode_jwt_payload(token):
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        rem = len(parts[1]) % 4
        padded = parts[1] + ("=" * (4 - rem) if rem else "")
        return json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except Exception as exc:
        print(f"[!] JWT payload decode error: {exc}", file=sys.stderr)
        return {}

def parse_json_file(fp):
    try:
        with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
            data = json.load(fh)
    except Exception as exc:
        print(f"[!] JSON 解析失败 ({fp}): {exc}", file=sys.stderr)
        return []

    raw_items = []
    if isinstance(data, list):
        raw_items = data
    elif isinstance(data, dict):
        if isinstance(data.get("accounts"), list):
            raw_items = data["accounts"]
        else:
            raw_items = [data]

    parsed = []
    fallback_name = os.path.splitext(os.path.basename(fp))[0]
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        acc = item.get("account") if isinstance(item.get("account"), dict) else item
        auth = item.get("auth") if isinstance(item.get("auth"), dict) else item
        access_token = (auth.get("accessToken") or item.get("accessToken") or "").strip()
        refresh_token = (auth.get("refreshToken") or item.get("refreshToken") or "").strip()
        if not access_token:
            print(f"[!] JSON 缺少 accessToken: {fp}", file=sys.stderr)
            continue
        jwt_payload = decode_jwt_payload(access_token)
        uid = (acc.get("uid") or item.get("uid") or jwt_payload.get("sub") or "").strip()
        if not uid:
            print(f"[!] 无法从 JSON 或 Token 中解析出 uid: {fp}", file=sys.stderr)
            continue
        nickname = (
            acc.get("nickname")
            or item.get("nickname")
            or jwt_payload.get("preferred_username")
            or fallback_name
        )
        exp = auth.get("expiresAt") or item.get("expiresAt") or jwt_payload.get("exp")
        domain = (auth.get("domain") or item.get("domain") or "").strip() or "copilot.tencent.com"
        realm = (auth.get("realm") or item.get("realm") or "").strip() or "cn"
        enterprise_id = (acc.get("enterpriseId") or item.get("enterpriseId") or "").strip()

        account_item = {
            "uid": uid,
            "nickname": str(nickname).strip(),
            "domain": domain,
            "realm": realm,
            "platform": item.get("platform") or "CLI",
            "product": item.get("product") or "workbuddy",
            "enterpriseId": enterprise_id,
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "expiresAt": exp,
            "enabled": True,
            "source": "import",
        }
        parsed.append(account_item)
        print(f"[+] 成功解析 JSON 账号: {account_item['nickname']} (UID: {uid}, 过期时间: {exp})")
    return parsed


def parse_account_files(file_paths):
    accounts = []
    for fp in file_paths:
        if not os.path.exists(fp):
            print(f"[!] 文件不存在: {fp}", file=sys.stderr)
            continue
        if fp.lower().endswith(".json"):
            accounts.extend(parse_json_file(fp))
            continue
        with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
            content = fh.read().strip()
        # 若 txt 内实际是 JSON 内容，也自动按 JSON 解析
        if content.startswith("{") or content.startswith("["):
            accounts.extend(parse_json_file(fp))
            continue
        parts = content.split("----")
        if len(parts) < 3:
            print(f"[!] 文件格式不符合 手机号----AT----RT: {fp}", file=sys.stderr)
            continue
        phone = parts[0].strip()
        access_token = parts[1].strip()
        refresh_token = parts[2].strip()

        payload = decode_jwt_payload(access_token)
        uid = payload.get("sub")
        exp = payload.get("exp")
        if not uid:
            print(f"[!] 无法从 Token 中解析出 sub/uid: {fp}", file=sys.stderr)
            continue

        account_item = {
            "uid": uid,
            "nickname": phone,
            "domain": "copilot.tencent.com",
            "realm": "cn",
            "platform": "CLI",
            "product": "workbuddy",
            "enterpriseId": "",
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "expiresAt": exp,
            "enabled": True,
            "source": "import"
        }
        accounts.append(account_item)
        print(f"[+] 成功解析 TXT 账号: {phone} (UID: {uid}, 过期时间: {exp})")
    return accounts

def deploy_to_server(accounts, server_host="34.96.166.42", server_user="mwsu"):
    """
    通过 SSH 将解析好的账号在服务器上直接通过 wb_accounts.AccountPool 写入落盘并同步积分
    """
    remote_script = """
import sys, json, os
sys.path.append("/home/mwsu/workbuddy2api-hub")
import wb_accounts

raw = sys.stdin.read()
rows = json.loads(raw)
pool = wb_accounts.AccountPool("/home/mwsu/workbuddy2api-hub/accounts")
pool.load()

report = pool.import_rows(rows, realm="cn", overwrite=True)
print("IMPORT_REPORT:" + json.dumps(report, ensure_ascii=False))

# 刷新新导入账号的积分
results = []
for uid in report.get("added", []) + report.get("updated", []):
    acc = pool.get(uid)
    if not acc:
        continue
    try:
        cf = acc.fetch_credits()
        credits = acc.credits or {}
        remain = credits.get("remain", 0)
        used = credits.get("used", 0)
        results.append({"uid": uid, "nickname": acc.nickname, "remain": remain, "used": used, "ok": True})
        acc.save(pool.dir)
    except Exception as e:
        results.append({"uid": uid, "nickname": acc.nickname, "error": str(e), "ok": False})

print("CREDITS_REPORT:" + json.dumps(results, ensure_ascii=False))
"""
    cmd = ["ssh", f"{server_user}@{server_host}", f"python3 -c '{remote_script}'"]
    print(f"[*] 正在向服务器 {server_user}@{server_host} 导入并初始化积分...")
    res = subprocess.run(cmd, input=json.dumps(accounts, ensure_ascii=False), capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[!] 导入失败:\n{res.stderr}", file=sys.stderr)
        return False, res.stderr
    print(res.stdout)

    # 平滑重载 Hub 服务
    print("[*] 正在平滑重载 PM2 wb-proxy 进程...")
    reload_res = subprocess.run(["ssh", f"{server_user}@{server_host}", "pm2 reload wb-proxy"], capture_output=True, text=True)
    print(reload_res.stdout)
    return True, res.stdout

def main():
    parser = argparse.ArgumentParser(description="批量导入微信导出的 WorkBuddy 文本账号")
    parser.add_argument(
        "--dir",
        default="/Users/mwsu/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/s420224237_3aa2/msg/file/2026-10",
        help="包含 txt 账号文件的目录",
    )
    parser.add_argument("--server", default="34.96.166.42")
    parser.add_argument("--user", default="mwsu")
    parser.add_argument("--dry-run", action="store_true", help="只解析，不写入服务器")
    parser.add_argument("--report", default="", help="解析结果 JSON 报告路径（不含 token）")
    args = parser.parse_args()

    txt_paths = sorted(glob.glob(os.path.join(args.dir, "*.txt")))
    json_paths = sorted(glob.glob(os.path.join(args.dir, "*.json")))
    file_paths = txt_paths + json_paths
    if not file_paths:
        print(f"[!] 目录中没有 txt 或 json 文件: {args.dir}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] 目录: {args.dir}")
    print(f"[*] 发现 {len(file_paths)} 个账号文件 (txt: {len(txt_paths)}, json: {len(json_paths)})")
    accounts = parse_account_files(file_paths)
    if not accounts:
        print("[!] 没有有效账号可导入，退出。")
        sys.exit(1)

    seen = set()
    duplicates = []
    for account in accounts:
        uid = account["uid"]
        if uid in seen:
            duplicates.append(uid)
        seen.add(uid)

    now = int(time.time())
    expired = [
        account
        for account in accounts
        if account.get("expiresAt") and int(account["expiresAt"]) < now
    ]

    print(f"[*] 解析成功 {len(accounts)} 个账号，去重后 {len(seen)} 个 UID")
    if duplicates:
        print(f"[!] 文档内重复 UID: {duplicates}")
    if expired:
        print(
            f"[!] {len(expired)} 个 accessToken 已过期，将导入并由 Hub 尝试用 refreshToken 刷新"
        )

    if args.report:
        report = [
            {
                "phone": account["nickname"],
                "uid": account["uid"],
                "expiresAt": account.get("expiresAt"),
            }
            for account in accounts
        ]
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"[*] 解析报告已写入: {args.report}")

    if args.dry_run:
        print("[*] dry-run 模式，未写入服务器。")
        return

    print(f"[*] 准备将 {len(accounts)} 个账号推送到香港服务器...")
    ok, output = deploy_to_server(
        accounts, server_host=args.server, server_user=args.user
    )
    if not ok:
        sys.exit(1)

    for line in output.splitlines():
        if line.startswith("IMPORT_REPORT:"):
            import_report = json.loads(line[len("IMPORT_REPORT:") :])
            print(
                "[*] 导入结果: "
                f"新增 {len(import_report.get('added', []))}, "
                f"更新 {len(import_report.get('updated', []))}, "
                f"跳过 {len(import_report.get('skipped', []))}, "
                f"无效 {len(import_report.get('invalid', []))}"
            )
            for item in import_report.get("skipped", []):
                print(f"    - 跳过: {item}")
            for item in import_report.get("invalid", []):
                print(f"    - 无效: {item}")
        elif line.startswith("CREDITS_REPORT:"):
            credit_rows = json.loads(line[len("CREDITS_REPORT:") :])
            failed = [row for row in credit_rows if not row.get("ok")]
            print(
                f"[*] 积分刷新: 成功 {len(credit_rows) - len(failed)}, "
                f"失败 {len(failed)}"
            )
            for row in failed:
                print(
                    f"    - {row.get('nickname') or row.get('uid')}: {row.get('error')}"
                )

    print("[*] 账号导入全部完成！")

if __name__ == "__main__":
    main()
