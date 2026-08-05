#!/usr/bin/env python3

"""

huaweicloud 建仓机器人 — 按 GOAT 建仓流程文档 v1.1

支持 9 种仓库类型 → 4 个等级初始化（2~14 项）

"""



import json, os, re, time, sys

import urllib.request, urllib.error



ORG = os.environ.get("ORG_NAME", "huaweicloud")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

EVENT_PATH = os.environ.get("GITHUB_EVENT_PATH", "")



GITCODE_ORG = os.environ.get("GITCODE_ORG", "huaweicloud")

GITCODE_USERNAME = os.environ.get("GITCODE_USERNAME", "")

GITCODE_TOKEN = os.environ.get("GITCODE_TOKEN", "")



FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")

GITCODE_API = "https://api.gitcode.com/api/v5"

GC_HEADERS = {"PRIVATE-TOKEN": GITCODE_TOKEN, "Content-Type": "application/json"}



FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")

FEISHU_ADMIN_OPEN_ID = os.environ.get("FEISHU_ADMIN_OPEN_ID", "")



GITHUB_API = "https://api.github.com"

BOT_HEADERS = {"Authorization": f"Bearer {BOT_TOKEN}", "Accept": "application/vnd.github+json"}

GH_HEADERS = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}



# ─── 类型→等级映射 ───

PRODUCT_TYPES = ["SDK", "Terraform Provider", "GitHub Action", "框架集成", "Exporter / Plugin", "IoT SDK"]

SAMPLE_TYPES = ["示例 / Lab / Sample"]

DOCS_TYPES = ["文档 / 数据集"]

INTERNAL_TYPES = ["内部配置"]

# 一级分类 → 允许的二级类型
CATEGORY_TYPES = {
    "产品项目": PRODUCT_TYPES,
    "示例教程": SAMPLE_TYPES,
    "文档数据": DOCS_TYPES,
    "内部配置": INTERNAL_TYPES,
}


def parse_repo_type_combo(combo):
    """拆分组合选项 '一级分类 / 二级类型'，容忍有无空格差异。

    返回 (category, type)；无法识别时返回 (None, combo)。
    """
    combo = (combo or "").strip()
    for cat in CATEGORY_TYPES:
        if combo.startswith(cat):
            rest = combo[len(cat):].lstrip(" /　").strip()
            if rest:
                return cat, rest
            return cat, CATEGORY_TYPES[cat][0]
    return None, combo





def api(method, path, token=None, data=None):

    headers = BOT_HEADERS if token == "bot" else GH_HEADERS

    url = f"{GITHUB_API}{path}"

    body = json.dumps(data).encode() if data else None

    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:

        with urllib.request.urlopen(req, timeout=30) as resp:

            if resp.status == 204:

                return None

            return json.loads(resp.read())

    except urllib.error.HTTPError as e:

        err = e.read().decode()[:500]

        print(f"API {method} {path}: {e.code} {err}")

        return None





def load_event():

    with open(EVENT_PATH) as f:

        return json.load(f)





def gitcode_api(method, path, data=None):

    """调用 GitCode API（GitLab 兼容）"""

    if not GITCODE_TOKEN:

        print("GITCODE_TOKEN not set, skipping GitCode API")

        return None

    url = f"{GITCODE_API}{path}"

    body = json.dumps(data).encode() if data else None

    req = urllib.request.Request(url, data=body, headers=GC_HEADERS, method=method)

    try:

        with urllib.request.urlopen(req, timeout=30) as resp:

            if resp.status == 204:

                return None

            return json.loads(resp.read())

    except urllib.error.HTTPError as e:

        err = e.read().decode()[:500]

        print(f"GitCode API {method} {path}: {e.code} {err}")

        return None





def create_gitcode_repo(repo_name, description, private=False):

    """在 GitCode 上创建同名仓库（v5 API），元数据与 GitHub 保持一致。

    若仓库已存在则用 PATCH 更新元数据（描述、可见性），确保两边一致。
    """

    data = {

        "name": repo_name,

        "path": repo_name,

        "description": description or "",

        "private": private,

    }

    result = gitcode_api("POST", f"/orgs/{GITCODE_ORG}/repos", data)

    if result and "id" in result:

        gitcode_url = result.get("html_url", f"https://gitcode.com/{GITCODE_ORG}/{repo_name}")

        print(f"GitCode repo created: {gitcode_url}")

        return gitcode_url

    # 仓库可能已存在 → 更新元数据保持一致
    existing = gitcode_api("GET", f"/repos/{GITCODE_ORG}/{repo_name}")

    if existing and "id" in existing:

        patch = {"description": description or "", "private": private}

        updated = gitcode_api("PATCH", f"/repos/{GITCODE_ORG}/{repo_name}", patch)

        if updated and "id" in updated:

            gitcode_url = updated.get("html_url", f"https://gitcode.com/{GITCODE_ORG}/{repo_name}")

            print(f"GitCode repo metadata updated: {gitcode_url}")

            return gitcode_url

    print(f"Failed to create GitCode repo")

    return None





# ─── 许可证策略 ───

def get_license(repo_category, user_choice):

    if repo_category == "产品项目":

        choice_map = {"Apache-2.0（推荐）": "Apache-2.0", "Apache-2.0": "Apache-2.0", "MIT": "MIT", "BSD-3-Clause": "BSD-3-Clause"}

        return choice_map.get(user_choice, "Apache-2.0")

    return "Apache-2.0"





# ─── README 模板（9套） ───

README_TEMPLATES = {

    "SDK": """# {name}

[![License](https://img.shields.io/badge/License-{license}-blue.svg)](LICENSE)



{description}



## 安装

```bash

pip install {name}

```



## API 参考

待补充



## 贡献

查看 [CONTRIBUTING.md](CONTRIBUTING.md)



## 许可证

本项目使用 {license} 许可证。

""",

    "Terraform Provider": """# {name}

[![License](https://img.shields.io/badge/License-{license}-blue.svg)](LICENSE)



{description}



## Provider 配置

```hcl

provider "{name}" {{

  # 配置项

}}

```



## Resource / DataSource 列表

待补充



## 贡献

查看 [CONTRIBUTING.md](CONTRIBUTING.md)

""",

    "GitHub Action": """# {name}

[![License](https://img.shields.io/badge/License-{license}-blue.svg)](LICENSE)



{description}



## Inputs

| 参数 | 类型 | 必需 | 默认值 | 说明 |

|------|------|------|--------|------|



## Outputs

| 输出 | 说明 |

|------|------|



## 使用示例

```yaml

- uses: huaweicloud/{name}@v1

  with:

    param: value

```



## 贡献

查看 [CONTRIBUTING.md](CONTRIBUTING.md)

""",

    "框架集成": """# {name}

[![License](https://img.shields.io/badge/License-{license}-blue.svg)](LICENSE)



{description}



## 快速集成

```bash

pip install {name}

```



## 配置说明

待补充



## 版本兼容

| 版本 | 兼容语言 / 框架 | 状态 |

|------|----------------|------|



## 贡献

查看 [CONTRIBUTING.md](CONTRIBUTING.md)

""",

    "Exporter / Plugin": """# {name}

[![License](https://img.shields.io/badge/License-{license}-blue.svg)](LICENSE)



{description}



## 部署方式

```bash

docker run -d --name {name} huaweicloud/{name}:latest

```



## 指标说明

待补充



## 贡献

查看 [CONTRIBUTING.md](CONTRIBUTING.md)

""",

    "IoT SDK": """# {name}

[![License](https://img.shields.io/badge/License-{license}-blue.svg)](LICENSE)



{description}



## 硬件要求

待补充



## 设备接入示例

```python

from {name} import Device

device = Device("device-id")

device.connect()

```



## 贡献

查看 [CONTRIBUTING.md](CONTRIBUTING.md)

""",

    "示例 / Lab / Sample": """# {name}



{description}



## 前置条件

- 语言环境

- 依赖安装



## 运行步骤

```bash

# 运行示例

```



## 效果展示

待补充

""",

    "文档 / 数据集": """# {name}



{description}



## 内容说明

待补充



## 使用方式

待补充

""",

    "内部配置": """# {name}



{description}



> 内部配置仓库



## 用途

待补充



## 使用方式

待补充

""",

}





def make_readme(name, repo_type, license_name, description):

    tmpl = README_TEMPLATES.get(repo_type, README_TEMPLATES["SDK"])

    return tmpl.format(name=name, license=license_name, description=description)





# ─── 文件模板 ───

CONTRIBUTING_MD = """# Contributing to {name}



## 开发环境搭建

见 README。



## 提交规范

使用约定式提交：`feat:`, `fix:`, `docs:`, `style:`, `refactor:`, `test:`, `chore:`



## PR 流程

1. Fork 仓库

2. 创建分支 `feat/xxx`

3. 提交代码

4. 发起 Pull Request

5. 至少 2 人 Review + CI 通过后合并



## Issue 规范

使用 Bug Report / Feature Request 模板

"""



SECURITY_MD = """# Security Policy



## 报告安全漏洞

如发现安全漏洞，请发送邮件至 huaweicloud@huawei.com，**不要在公开 Issue 中披露**。



## 支持版本

| 版本 | 支持状态 |

|------|---------|

| 最新 | ✅ 活跃支持 |

"""



COC_MD = """# Contributor Covenant Code of Conduct



## 我们的承诺

为了营造一个开放和友好的环境，我们承诺尊重所有参与者。



## 我们的标准

- 使用友好和包容的语言

- 尊重不同的观点和经验

- 建设性地接受批评



## 执行

违规行为可报告至项目维护者。

"""



BUG_REPORT_YML = """name: Bug Report

description: 报告一个 bug

labels: ["type/bug"]

body:

  - type: textarea

    attributes:

      label: 描述

      description: 发生了什么

    validations:

      required: true

  - type: textarea

    attributes:

      label: 复现步骤

  - type: textarea

    attributes:

      label: 期望行为

  - type: textarea

    attributes:

      label: 环境信息

"""



FEATURE_YML = """name: Feature Request

description: 请求一个新功能

labels: ["type/feature"]

body:

  - type: textarea

    attributes:

      label: 描述

      description: 你希望添加什么功能

    validations:

      required: true

  - type: textarea

    attributes:

      label: 使用场景

"""



CONFIG_YML = """blank_issues_enabled: false

"""



PR_TEMPLATE = """## 变更说明





## 关联 Issue

Fixes #



## 测试

- [ ] 单元测试通过

- [ ] 手动测试通过

"""



CI_WORKFLOW = """name: CI
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run linter
        run: |
          echo "Running lint checks..."
          # Python: pip install ruff && ruff check .
          # JS: npx eslint .
          # Go: golangci-lint run .
  test:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: |
          echo "Running tests..."
          # Python: pip install pytest && pytest
          # JS: npm test
          # Go: go test ./...
  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build
        run: |
          echo "Build successful"
"""

CODEOWNERS_MD = """# CODEOWNERS - auto-assign PR reviewers
* @huaweiclouddev
"""

TRIAGE_WORKFLOW = """name: Issue Triage

on:

  issues:

    types: [opened]

permissions:

  issues: write

  contents: read

jobs:

  triage:

    runs-on: ubuntu-latest

    steps:

      - uses: huaweicloud/.github/actions/issue-bot@main

        env:

          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

"""



SYNC_WORKFLOW = f"""name: Sync to GitCode

on:

  push:

    branches: [main]

permissions:

  contents: read

jobs:

  sync:

    runs-on: ubuntu-latest

    steps:

      - uses: actions/checkout@v4

        with:

          fetch-depth: 0

      - run: |

          git remote add gitcode https://oauth2:${{{{ secrets.GITCODE_TOKEN }}}}@gitcode.com/{GITCODE_ORG}/${{{{ github.event.repository.name }}}}.git || true

          git push gitcode main --force

"""



STATUS_TRANSITION_WORKFLOW = """name: Status Transition
on:
  pull_request:
    types: [opened, synchronize, reopened, closed]
  issues:
    types: [closed, reopened]
permissions:
  issues: write
  contents: read
jobs:
  link-pr-to-issue:
    if: github.event.pull_request
    runs-on: ubuntu-latest
    steps:
      - uses: actions/github-script@v7
        with:
          script: |
            const prBody = context.payload.pull_request.body || '';
            const issueMatches = prBody.match(/(?:close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved)\s+#(\d+)/gi) || [];
            for (const match of issueMatches) {
              const issueNumber = parseInt(match.match(/#(\d+)/)[1]);
              try {
                const { data: issue } = await github.rest.issues.get({
                  owner: context.repo.owner, repo: context.repo.repo, issue_number: issueNumber
                });
                const labels = (issue.labels || []).map(l => l.name);
                const newLabels = labels
                  .filter(l => !l.startsWith('status/'))
                  .concat('status/in-progress');
                await github.rest.issues.update({
                  owner: context.repo.owner, repo: context.repo.repo,
                  issue_number: issueNumber, labels: [...new Set(newLabels)]
                });
              } catch (e) { console.log(`Failed: ${e.message}`); }
            }
  mark-resolved:
    if: github.event.pull_request && github.event.action == 'closed' && github.event.pull_request.merged
    runs-on: ubuntu-latest
    steps:
      - uses: actions/github-script@v7
        with:
          script: |
            const prBody = context.payload.pull_request.body || '';
            const issueMatches = prBody.match(/(?:close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved)\s+#(\d+)/gi) || [];
            for (const match of issueMatches) {
              const issueNumber = parseInt(match.match(/#(\d+)/)[1]);
              try {
                const { data: issue } = await github.rest.issues.get({
                  owner: context.repo.owner, repo: context.repo.repo, issue_number: issueNumber
                });
                const labels = (issue.labels || []).map(l => l.name);
                const newLabels = labels
                  .filter(l => !l.startsWith('status/'))
                  .concat('status/resolved');
                await github.rest.issues.update({
                  owner: context.repo.owner, repo: context.repo.repo,
                  issue_number: issueNumber, labels: [...new Set(newLabels)]
                });
              } catch (e) { console.log(`Failed: ${e.message}`); }
            }
  mark-completed:
    if: github.event.issue && github.event.action == 'closed'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/github-script@v7
        with:
          script: |
            const labels = (context.payload.issue.labels || []).map(l => l.name);
            const newLabels = labels
              .filter(l => !l.startsWith('status/'))
              .concat('status/completed');
            await github.rest.issues.update({
              owner: context.repo.owner, repo: context.repo.repo,
              issue_number: context.issue.number, labels: [...new Set(newLabels)]
            });
"""

DEPENDABOT = """version: 2

updates:

  - package-ecosystem: "github-actions"

    directory: "/"

    schedule:

      interval: "weekly"

"""



LABELS_PRODUCT = ["type/bug", "type/enhancement", "type/question", "type/documentation",

                  "priority/critical", "priority/high", "priority/medium", "priority/low",

                  "status/pending", "status/in-progress", "status/blocked",

                  "good first issue", "help wanted", "agent/triaged"]

LABELS_SAMPLE = LABELS_PRODUCT[:8]





def create_file(repo, path, content, message):

    data = {"message": message, "content": b64(content)}

    existing = api("GET", f"/repos/{ORG}/{repo}/contents/{path}", "bot")

    if existing and "sha" in existing:

        data["sha"] = existing["sha"]

    api("PUT", f"/repos/{ORG}/{repo}/contents/{path}", "bot", data)





def b64(s):

    import base64

    return base64.b64encode(s.encode()).decode()





def create_labels(repo, labels):

    for name in labels:

        api("POST", f"/repos/{ORG}/{repo}/labels", "bot", {"name": name, "color": "ededed"})





def enable_security(repo, level):

    """开启安全告警 + 自动修复（Dependabot alerts / automated security fixes）"""

    if level == "internal":

        print(f"Internal repo, skip security alerts")

        return



    # Dependabot vulnerability alerts

    api("PUT", f"/repos/{ORG}/{repo}/vulnerability-alerts", "bot")

    print(f"[{repo}] Dependabot vulnerability alerts enabled")



    # Automated security fixes (Dependabot security updates)

    api("PUT", f"/repos/{ORG}/{repo}/automated-security-fixes", "bot")

    print(f"[{repo}] Automated security fixes enabled")





def validate_repo_name(name):

    return bool(re.match(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$', name)) and len(name) <= 100





def validate_topics(topics_str):

    topics = re.split(r'[,\n]+', topics_str.strip())

    valid = []

    for t in topics:

        t = t.strip().lower()

        if re.match(r'^[a-z0-9][a-z0-9.-]*$', t):

            valid.append(t)

    return valid





def assign_role(repo, role, users):

    if not users:

        return

    role_map = {"owner": "admin", "maintainer": "maintain", "writer": "push"}

    perm = role_map.get(role, "push")

    for user in users:

        api("PUT", f"/repos/{ORG}/{repo}/collaborators/{user}", "bot", {"permission": perm})





def notify_feishu(repo_name, repo_type, url, author, gitcode_url=None):

    if not all([FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_ADMIN_OPEN_ID]):

        return

    try:

        token_resp = json.loads(urllib.request.urlopen(

            urllib.request.Request("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",

                                   data=json.dumps({"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}).encode(),

                                   headers={"Content-Type": "application/json"}), timeout=10).read())

        token = token_resp.get("tenant_access_token", "")

        if not token:

            return



        card = {

            "config": {"wide_screen_mode": True},

            "header": {"title": {"tag": "plain_text", "content": "  仓库创建成功"}, "template": "turquoise"},

            "elements": [

                {"tag": "markdown", "content": f"**{author}** 申请的仓库已创建"},

                {"tag": "div", "fields": [

                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**仓库名称**\n{repo_name}"}},

                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**类型**\n{repo_type}"}},

                ]},

                {"tag": "div", "fields": [

                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**GitHub**\n[点击打开]({url})"}},

                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**GitCode**\n[点击打开]({gitcode_url or '创建失败'})"}},

                ]},

                {"tag": "action", "actions": [

                    {"tag": "button", "text": {"tag": "plain_text", "content": "查看 GitHub 仓库"}, "type": "primary", "url": url},

                ]},

                {"tag": "note", "elements": [{"tag": "plain_text", "content": "huaweicloud Repo Creator"}]}

            ]

        }

        urllib.request.urlopen(urllib.request.Request(

            f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",

            data=json.dumps({"receive_id": FEISHU_ADMIN_OPEN_ID, "msg_type": "interactive",

                             "content": json.dumps(card, ensure_ascii=False)}).encode(),

            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}), timeout=10)

        print("Feishu notification sent")

    except Exception as e:

        print(f"Feishu notification failed: {e}")





def get_init_level(repo_category):

    """根据一级分类确定初始化等级"""

    if repo_category == "产品项目":

        return "product"

    elif repo_category == "示例教程":

        return "sample"

    elif repo_category == "文档数据":

        return "docs"

    else:

        return "internal"





def main():

    event = load_event()

    issue = event.get("issue", {})

    issue_number = issue.get("number", 0)

    labels = [l["name"] for l in issue.get("labels", [])]

    title = issue.get("title", "")



    if "status/approved" not in labels:

        print("Not approved, skipping")

        return



    body = issue.get("body", "")

    author = issue.get("user", {}).get("login", "")



    # parse form fields (section header -> next line is value)

    lines = body.split("\n")

    fields = {}

    for i, line in enumerate(lines):

        for prefix in ["### 仓库类型", "### 仓库名称", "### 仓库描述", "### 可见性",

                        "### 开源许可证", "### Topics 标签", "### Owner", "### Maintainer",

                        "### Writer", "### 申请理由"]:

            if line.startswith(prefix):

                key = prefix.replace("### ", "").strip()

                # value is on the next non-empty line

                for j in range(i + 1, min(i + 3, len(lines))):

                    val = lines[j].strip()

                    if val and not val.startswith("###") and not val.startswith("_"):

                        fields[key] = val

                        break

                break



    # 组合选项格式: "一级分类 / 二级类型"，拆分出分类与类型（容忍空格差异）
    repo_type_combo = fields.get("仓库类型", "产品项目 / SDK")

    repo_category, repo_type = parse_repo_type_combo(repo_type_combo)

    if not repo_type:

        repo_type = "SDK"

    repo_name = fields.get("仓库名称", "").strip().lower()

    description = fields.get("仓库描述", "")

    visibility = fields.get("可见性", "public").lower()

    license_choice = fields.get("开源许可证", "Apache-2.0")

    topics_raw = fields.get("Topics 标签", "")

    owner_str = fields.get("Owner", "")

    maintainer_str = fields.get("Maintainer", "")

    writer_str = fields.get("Writer", "")

    justification = fields.get("申请理由", "")



    print(f"Processing Issue #{issue_number}: {title}")

    print(f"Type: {repo_type}, Name: {repo_name}")



    if not validate_repo_name(repo_name):

        api("POST", f"/repos/{ORG}/repository-requests/issues/{issue_number}/comments", "gh",

            {"body": f"  **仓库名称格式错误**：`{repo_name}` 不符合规范（小写字母+数字+连字符，≤100字符）"})

        print(f"FAIL: invalid repo name '{repo_name}'")

        sys.exit(1)

    # 一级分类与二级类型匹配校验（容忍空格差异）
    if repo_category not in CATEGORY_TYPES:
        api("POST", f"/repos/{ORG}/repository-requests/issues/{issue_number}/comments", "gh",
            {"body": f"  **仓库类型（一级）无效**：`{repo_category}` 必须是 产品项目/示例教程/文档数据/内部配置 之一"})
        print(f"FAIL: invalid category '{repo_category}'")
        sys.exit(1)
    if repo_type.replace(" ", "") not in [t.replace(" ", "") for t in CATEGORY_TYPES[repo_category]]:
        allowed = ", ".join(CATEGORY_TYPES[repo_category])
        api("POST", f"/repos/{ORG}/repository-requests/issues/{issue_number}/comments", "gh",
            {"body": f"  **类型不匹配**：一级分类 `{repo_category}` 应搭配二级类型（{allowed}），当前选择了 `{repo_type}`"})
        print(f"FAIL: category '{repo_category}' does not match type '{repo_type}'")
        sys.exit(1)



    topics = validate_topics(topics_raw)

    if len(topics) < 3:

        api("POST", f"/repos/{ORG}/repository-requests/issues/{issue_number}/comments", "gh",

            {"body": f"  **Topics 不足**：至少需要 3 个合法标签（当前 {len(topics)} 个，有效: {', '.join(topics) or '无'}）"})

        print(f"FAIL: topics < 3 (got {len(topics)}: {topics})")

        sys.exit(1)

    # 角色人数校验：Owner 1-2 人，Maintainer 2-3 人
    owners = [u.strip() for u in re.split(r'[,\n]+', owner_str) if u.strip()]
    maintainers = [u.strip() for u in re.split(r'[,\n]+', maintainer_str) if u.strip()]
    if not owners:
        api("POST", f"/repos/{ORG}/repository-requests/issues/{issue_number}/comments", "gh",
            {"body": "  **Owner 缺失**：Owner（管理员）至少 1 人"})
        print("FAIL: owner < 1")
        sys.exit(1)
    if len(owners) > 2:
        api("POST", f"/repos/{ORG}/repository-requests/issues/{issue_number}/comments", "gh",
            {"body": f"  **Owner 超配**：Owner（管理员）严格控制在 1-2 人（当前 {len(owners)} 人）"})
        print(f"FAIL: owner > 2 (got {len(owners)})")
        sys.exit(1)
    if len(maintainers) < 2:
        api("POST", f"/repos/{ORG}/repository-requests/issues/{issue_number}/comments", "gh",
            {"body": "  **Maintainer 不足**：Maintainer（维护者）控制在 2-3 人（当前不足 2 人）"})
        print("FAIL: maintainer < 2")
        sys.exit(1)
    if len(maintainers) > 3:
        api("POST", f"/repos/{ORG}/repository-requests/issues/{issue_number}/comments", "gh",
            {"body": f"  **Maintainer 超配**：Maintainer（维护者）控制在 2-3 人（当前 {len(maintainers)} 人）"})
        print(f"FAIL: maintainer > 3 (got {len(maintainers)})")
        sys.exit(1)



    # check duplicate

    existing = api("GET", f"/repos/{ORG}/{repo_name}", "bot")

    if existing and "id" in existing:

        api("POST", f"/repos/{ORG}/repository-requests/issues/{issue_number}/comments", "gh",

            {"body": f"  **仓库已存在**：`{ORG}/{repo_name}` 已存在"})

        print(f"FAIL: repo already exists '{repo_name}'")

        sys.exit(1)



    license_name = get_license(repo_category, license_choice)

    level = get_init_level(repo_category)



    # create repo

    create_data = {

        "name": repo_name,

        "description": description,

        "private": visibility == "private",

        "auto_init": True,

        "has_issues": True,

        "has_projects": False,

        "has_wiki": False,

        "allow_squash_merge": True,

        "allow_merge_commit": False,

        "allow_rebase_merge": False,

    }

    result = api("POST", f"/orgs/{ORG}/repos", "bot", create_data)

    if not result or "id" not in result:

        print(f"Failed to create repo: {result}")

        return



    repo_url = result["html_url"]

    print(f"Repo created: {repo_url}")



    # init files

    readme = make_readme(repo_name, repo_type, license_name, description)

    create_file(repo_name, "README.md", readme, "Init README")

    create_file(repo_name, "LICENSE", f"{license_name} License\n", f"Add {license_name} license")
    # PR standards (all levels): CI + CODEOWNERS
    create_file(repo_name, ".github/workflows/ci.yml", CI_WORKFLOW, "Add CI workflow")
    create_file(repo_name, ".github/CODEOWNERS", CODEOWNERS_MD, "Add CODEOWNERS")




    if level in ("product", "sample"):

        create_file(repo_name, "CONTRIBUTING.md", CONTRIBUTING_MD.format(name=repo_name), "Add contributing guide")

    if level == "product":

        create_file(repo_name, "SECURITY.md", SECURITY_MD, "Add security policy")

        create_file(repo_name, "CODE_OF_CONDUCT.md", COC_MD, "Add code of conduct")

    if level in ("product", "sample"):

        create_file(repo_name, ".github/ISSUE_TEMPLATE/bug_report.yml", BUG_REPORT_YML, "Add bug template")

        create_file(repo_name, ".github/ISSUE_TEMPLATE/feature_request.yml", FEATURE_YML, "Add feature template")

        create_file(repo_name, ".github/ISSUE_TEMPLATE/config.yml", CONFIG_YML, "Add issue config")

        create_file(repo_name, ".github/PULL_REQUEST_TEMPLATE.md", PR_TEMPLATE, "Add PR template")

    if level == "product":

        create_file(repo_name, ".github/dependabot.yml", DEPENDABOT, "Add dependabot config")

        create_file(repo_name, ".github/workflows/triage-issue.yml", TRIAGE_WORKFLOW, "Add triage workflow")

        create_file(repo_name, ".github/workflows/sync-to-gitcode.yml", SYNC_WORKFLOW, "Add GitCode sync workflow")
        create_file(repo_name, ".github/workflows/status-transition.yml", STATUS_TRANSITION_WORKFLOW, "Add status transition workflow")



    # labels

    if level == "product":

        create_labels(repo_name, LABELS_PRODUCT)

    elif level == "sample":

        create_labels(repo_name, LABELS_SAMPLE)



    # topics

    api("PUT", f"/repos/{ORG}/{repo_name}/topics", "bot",

        {"names": topics[:20]})



    # security alerts + auto-fix

    enable_security(repo_name, level)



    # roles

    writers = [u.strip() for u in re.split(r'[,\n]+', writer_str) if u.strip()]



    for u in owners:

        assign_role(repo_name, "owner", [u])

    for u in maintainers:

        if u not in owners:

            assign_role(repo_name, "maintainer", [u])

    for u in writers:

        if u not in owners and u not in maintainers:

            assign_role(repo_name, "writer", [u])



    # create GitCode mirror (metadata consistent with GitHub)
    gitcode_url = create_gitcode_repo(repo_name, description, private=(visibility == "private"))



    # close issue

    init_count = {"product": 14, "sample": 7, "docs": 3, "internal": 2}[level]

    lines = [

        f"##  建仓完成",

        f"",

        f"| 项目 | 详情 |",

        f"|------|------|",

        f"| GitHub | [{ORG}/{repo_name}]({repo_url}) |",

    ]

    if gitcode_url:

        lines.append(f"| GitCode | [{GITCODE_ORG}/{repo_name}]({gitcode_url}) |")

    lines += [

        f"| 类型 | {repo_type}（{level} 级） |",

        f"| 许可证 | {license_name} |",

        f"| 初始化 | {init_count} 项 |",

        f"| 可见性 | {visibility} |",

    ]

    comment = "\n".join(lines)



    api("POST", f"/repos/{ORG}/repository-requests/issues/{issue_number}/comments", "gh", {"body": comment})

    api("POST", f"/repos/{ORG}/repository-requests/issues/{issue_number}/labels", "gh", {"labels": ["status/completed"]})

    api("PATCH", f"/repos/{ORG}/repository-requests/issues/{issue_number}", "gh", {"state": "closed"})



    notify_feishu(repo_name, repo_type, repo_url, author, gitcode_url)



    print("Done.")





if __name__ == "__main__":

    main()

