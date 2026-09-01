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
    # 中英文字段前缀映射（key → 统一字段名）
    prefix_map = [
        ("### 初始化语言", "初始化语言"),
        ("### Initialization Language", "初始化语言"),
        ("### 仓库类型", "仓库类型"),
        ("### Repository Type", "仓库类型"),
        ("### 仓库名称", "仓库名称"),
        ("### Repository Name", "仓库名称"),
        ("### 仓库描述", "仓库描述"),
        ("### Repository Description", "仓库描述"),
        ("### 可见性", "可见性"),
        ("### Visibility", "可见性"),
        ("### 开源许可证", "开源许可证"),
        ("### Open Source License", "开源许可证"),
        ("### Topics 标签", "Topics 标签"),
        ("### Topics Tags", "Topics 标签"),
        ("### Owner", "Owner"),
        ("### Maintainer", "Maintainer"),
        ("### Writer", "Writer"),
        ("### 申请理由", "申请理由"),
        ("### Justification", "申请理由"),
    ]
    for i, line in enumerate(lines):
        for prefix, key in prefix_map:
            if line.startswith(prefix):
                # 读取标题后直到下一个 ### 标题之间的所有非空行，拼接为字段值
                vals = []
                for j in range(i + 1, len(lines)):
                    nxt = lines[j].strip()
                    if nxt.startswith("###"):
                        break
                    if nxt == "_No response_":
                        continue
                    if nxt:
                        vals.append(nxt)
                fields[key] = "\n".join(vals) if vals else ""
                break
    return fields


def validate_repo_name(name):
    return bool(re.match(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$', name)) and len(name) <= 100


def validate_topics(raw):
    topics = re.split(r'[,\n、；;　\s]+', raw.strip())
    return [t.strip().lower() for t in topics if re.match(r'^[a-z0-9][a-z0-9.-]*$', t.strip())]


def split_users(raw):
    return [u.strip() for u in re.split(r'[,\n、；;　\s]+', raw) if u.strip()]


def get_org_members(org="huaweicloud"):
    """拉取组织全部成员登录名集合（分页）"""
    members = set()
    page = 1
    while page <= 10:
        result = api("GET", f"/orgs/{org}/members?per_page=100&page={page}")
        if not isinstance(result, list) or not result:
            break
        members.update(u.get("login") for u in result if isinstance(u, dict) and u.get("login"))
        if len(result) < 100:
            break
        page += 1
    return members


CATEGORY_TYPES = {
    "产品项目": ["SDK", "Terraform Provider", "GitHub Action", "框架集成", "Exporter / Plugin", "IoT SDK"],
    "示例教程": ["示例 / Lab / Sample"],
    "文档数据": ["文档 / 数据集"],
    "内部配置": ["内部配置"],
}


def normalize_repo_type_combo(combo):
    """将英文表单的组合选项映射为内部统一的中文组合。"""
    combo = (combo or "").strip()
    mapping = [
        ("Product / SDK", "产品项目 / SDK"),
        ("Product / Terraform Provider", "产品项目 / Terraform Provider"),
        ("Product / GitHub Action", "产品项目 / GitHub Action"),
        ("Product / Framework Integration", "产品项目 / 框架集成"),
        ("Product / Exporter / Plugin", "产品项目 / Exporter / Plugin"),
        ("Product / IoT SDK", "产品项目 / IoT SDK"),
        ("Sample / Lab / Sample", "示例教程 / 示例 / Lab / Sample"),
        ("Documentation / Docs / Dataset", "文档数据 / 文档 / 数据集"),
        ("Internal / Internal Config", "内部配置 / 内部配置"),
    ]
    norm = combo.replace(" ", "")
    for en, zh in mapping:
        if norm == en.replace(" ", ""):
            return zh
    return combo


def parse_repo_type_combo(combo):
    """拆分组合选项 '一级分类 / 二级类型'，容忍有无空格差异。"""
    combo = normalize_repo_type_combo(combo)
    combo = (combo or "").strip()
    for cat in CATEGORY_TYPES:
        if combo.startswith(cat):
            rest = combo[len(cat):].lstrip(" /　").strip()
            if rest:
                return cat, rest
            return cat, CATEGORY_TYPES[cat][0]
    return None, combo


def main():
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    with open(event_path) as f:
        event = json.load(f)

    issue = event.get("issue", {})
    number = issue.get("number", 0)
    body = issue.get("body", "")
    repo_full = event.get("repository", {}).get("full_name", "")

    # only process repo creation requests (中英文表单)
    body_text = body or ""
    if not any(k in body_text for k in ["### 仓库名称", "### Repository Name", "### Repository Type"]):
        print(f"Issue #{number}: not a repo creation request, skip validation")
        return

    fields = parse_fields(body)
    repo_name = fields.get("仓库名称", "").strip().lower()
    repo_type_combo = fields.get("仓库类型", "")
    topics_raw = fields.get("Topics 标签", "")
    owner_str = fields.get("Owner", "")
    maint_str = fields.get("Maintainer", "")
    visibility = (fields.get("可见性", "") or "").strip().lower()

    # 组合选项拆分: "一级分类 / 二级类型"（容忍空格差异）
    repo_category, repo_type = parse_repo_type_combo(repo_type_combo)

    errors = []

    if not repo_name:
        errors.append("- 仓库名称不能为空")
    elif not validate_repo_name(repo_name):
        errors.append(f"- 仓库名称 `{repo_name}` 不符合规范（小写字母+数字+连字符，≤100字符，不以连字符开头/结尾）")

    if repo_category not in CATEGORY_TYPES:
        errors.append(f"- 仓库类型 `{repo_type_combo}` 无效，可选组合: 产品项目/SDK、产品项目/Terraform Provider、产品项目/GitHub Action、产品项目/框架集成、产品项目/Exporter/Plugin、产品项目/IoT SDK、示例教程/示例/Lab/Sample、文档数据/文档/数据集、内部配置/内部配置")
    elif repo_type.replace(" ", "") not in [t.replace(" ", "") for t in CATEGORY_TYPES[repo_category]]:
        allowed = ", ".join(CATEGORY_TYPES[repo_category])
        errors.append(f"- 类型不匹配：分类 `{repo_category}` 应搭配二级类型（{allowed}），当前选择了 `{repo_type}`")

    topics = validate_topics(topics_raw)
    if len(topics) < 3:
        errors.append(f"- Topics 至少需要 3 个合法标签（当前 {len(topics)} 个: {', '.join(topics) or '无'}）")

    owners = split_users(owner_str)
    maintainers = split_users(maint_str)
    writer_str = fields.get("Writer", "")
    writers = split_users(writer_str)
    if not owners:
        errors.append("- Owner（管理员）至少 1 人")
    elif len(owners) > 2:
        errors.append(f"- Owner（管理员）严格控制在 1-2 人（当前 {len(owners)} 人）")
    if len(maintainers) < 2:
        errors.append("- Maintainer（维护者）控制在 2-3 人（当前不足 2 人）")
    elif len(maintainers) > 3:
        errors.append(f"- Maintainer（维护者）控制在 2-3 人（当前 {len(maintainers)} 人）")

    # 组织成员校验：仅 private 仓库强制（private collaborator 必须是组织成员）
    # public 仓库允许 outside collaborator（邀请制），不阻断，仅提示
    role_users = []
    for u in owners:
        role_users.append((u, "Owner"))
    for u in maintainers:
        role_users.append((u, "Maintainer"))
    for u in writers:
        role_users.append((u, "Writer"))
    if visibility == "private":
        org_members = get_org_members()
        non_members = [(u, role) for u, role in role_users if u and u not in org_members]
        if non_members:
            detail = "、".join(f"`{u}`({role})" for u, role in non_members)
            errors.append(f"- 以下角色用户不是组织成员（private 仓库 collaborator 须为组织成员，请先加入组织后再申请）：{detail}")

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
