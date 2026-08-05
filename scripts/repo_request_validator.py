#!/usr/bin/env python3
"""Repo request form validator + Feishu notify on validation pass"""
import json, os, re, urllib.request, urllib.error

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_API = "https://api.github.com"
HEADERS = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}

FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_ADMIN_OPEN_ID = os.environ.get("FEISHU_ADMIN_OPEN_ID", "")


def api(method, path, data=None):
    url = f"{GITHUB_API}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.status == 204:
                return None
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"API {method} {path}: {e.code} {e.read().decode()[:200]}")
        return None


def notify_feishu(repo_name, repo_type, repo_full, issue_number, author, description="", visibility="", reason=""):
    if not all([FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_ADMIN_OPEN_ID]):
        print("Feishu credentials not configured, skip notify")
        return
    try:
        data = json.dumps({"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}).encode()
        req = urllib.request.Request(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            data=data, headers={"Content-Type": "application/json"})
        token = json.loads(urllib.request.urlopen(req, timeout=10).read()).get("tenant_access_token", "")
        if not token:
            return
        issue_url = f"https://github.com/{repo_full}/issues/{issue_number}"
        approve_url = f"https://github.com/{repo_full}/actions/workflows/approve-repo.yml"
        card = {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": "  New Repo Request"}, "template": "blue"},
            "elements": [
                {"tag": "markdown", "content": f"**{author}** 提交了建仓申请"},
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**仓库名称**\n{repo_name}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**可见性**\n{visibility}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**类型**\n{repo_type}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**描述**\n{description}"}},
                    ]
                },
                {"tag": "hr"},
                {"tag": "markdown", "content": f" 申请理由：{reason}"},
                {"tag": "hr"},
                {
                    "tag": "action",
                    "actions": [
                        {"tag": "button", "text": {"tag": "plain_text", "content": "查看 Issue"}, "type": "default", "url": issue_url},
                        {"tag": "button", "text": {"tag": "plain_text", "content": "  审批通过"}, "type": "primary", "url": f"{approve_url}?issue_number={issue_number}"},
                    ]
                },
                {"tag": "note", "elements": [{"tag": "plain_text", "content": f"点击审批通过 → 跳转 GitHub → 填入 Issue 号 #{issue_number} → Run workflow"}]}
            ]
        }
        urllib.request.urlopen(urllib.request.Request(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
            data=json.dumps({"receive_id": FEISHU_ADMIN_OPEN_ID, "msg_type": "interactive",
                             "content": json.dumps(card, ensure_ascii=False)}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}), timeout=10)
        print("Feishu notify sent")
    except Exception as e:
        print(f"Feishu notify failed: {e}")


def parse_fields(body):
    lines = (body or "").split("\n")
    fields = {}
    for i, line in enumerate(lines):
        for prefix in ["### 仓库类型", "### 仓库名称", "### 仓库描述", "### 可见性",
                        "### 开源许可证", "### Topics 标签", "### Owner", "### Maintainer",
                        "### Writer", "### 申请理由"]:
            if line.startswith(prefix):
                key = prefix.replace("### ", "").strip()
                for j in range(i + 1, min(i + 3, len(lines))):
                    val = lines[j].strip()
                    if val.startswith("_No response_"):
                        val = ""
                    if val and not val.startswith("###") and not val.startswith("_"):
                        fields[key] = val
                        break
                break
    return fields


def validate_repo_name(name):
    return bool(re.match(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$', name)) and len(name) <= 100


def validate_topics(raw):
    topics = re.split(r'[,\n]+', raw.strip())
    return [t.strip().lower() for t in topics if re.match(r'^[a-z0-9][a-z0-9.-]*$', t.strip())]


def split_users(raw):
    return [u.strip() for u in re.split(r'[,\n]+', raw) if u.strip()]


def main():
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    with open(event_path) as f:
        event = json.load(f)

    issue = event.get("issue", {})
    number = issue.get("number", 0)
    body = issue.get("body", "")
    repo_full = event.get("repository", {}).get("full_name", "")

    # only process repo creation requests
    if "### 仓库名称" not in (body or ""):
        print(f"Issue #{number}: not a repo creation request, skip validation")
        return

    fields = parse_fields(body)
    repo_name = fields.get("仓库名称", "").strip().lower()
    repo_type = fields.get("仓库类型", "")
    topics_raw = fields.get("Topics 标签", "")
    owner_str = fields.get("Owner", "")
    maint_str = fields.get("Maintainer", "")

    errors = []

    if not repo_name:
        errors.append("- 仓库名称不能为空")
    elif not validate_repo_name(repo_name):
        errors.append(f"- 仓库名称 `{repo_name}` 不符合规范（小写字母+数字+连字符，≤100字符，不以连字符开头/结尾）")

    valid_types = ["SDK", "Terraform Provider", "GitHub Action", "框架集成",
                   "Exporter / Plugin", "IoT SDK", "示例 / Lab / Sample",
                   "文档 / 数据集", "内部配置"]
    if repo_type and repo_type not in valid_types:
        errors.append(f"- 仓库类型 `{repo_type}` 无效，可选: {', '.join(valid_types)}")

    topics = validate_topics(topics_raw)
    if len(topics) < 3:
        errors.append(f"- Topics 至少需要 3 个合法标签（当前 {len(topics)} 个: {', '.join(topics) or '无'}）")

    owners = split_users(owner_str)
    maintainers = split_users(maint_str)
    if not owners:
        errors.append("- Owner（管理员）至少 1 人")
    if not maintainers:
        errors.append("- Maintainer（维护者）至少 1 人")

    comment_path = f"/repos/{repo_full}/issues/{number}/comments"

    if errors:
        msg = "##  建仓申请校验未通过\n\n请修正以下问题后重新提交：\n\n" + "\n".join(errors)
        api("POST", comment_path, {"body": msg})
        current_labels = [l["name"] for l in issue.get("labels", [])]
        if "status/pending" in current_labels:
            api("DELETE", f"/repos/{repo_full}/issues/{number}/labels/status/pending")
        print(f"Issue #{number}: validation FAILED")
    else:
        current_labels = [l["name"] for l in issue.get("labels", [])]
        if "status/pending" not in current_labels:
            api("POST", f"/repos/{repo_full}/issues/{number}/labels", {"labels": ["status/pending"]})
            msg = "##  建仓申请校验通过\n\n所有字段符合规范，等待管理员审批。"
            api("POST", comment_path, {"body": msg})
            author = issue.get("user", {}).get("login", "")
            description = fields.get("仓库描述", "")
            visibility = fields.get("可见性", "")
            reason = fields.get("申请理由", "")
            notify_feishu(repo_name, repo_type, repo_full, number, author, description, visibility, reason)
            print(f"Issue #{number}: validation PASSED, status/pending added, Feishu notified")
        else:
            print(f"Issue #{number}: validation PASSED (already pending)")


if __name__ == "__main__":
    main()
