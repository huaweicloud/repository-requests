# 🤖 Repository Requests

社区贡献者在此仓库提交 Issue 来申请在 `huaweicloud` 组织下创建新仓库。

## 工作流程

```
贡献者提交建仓 Issue
        ↓
机器人自动处理
        ↓
├── 表单校验（仓库名称 / 类型匹配 / Topics≥3 / 角色人数）
├── 审批通过 → 创建仓库
├── 初始化社区治理配置
│   ├── README.md / LICENSE / CONTRIBUTING.md / SECURITY.md
│   ├── .github/CODEOWNERS
│   ├── .github/workflows/ci.yml / triage-issue.yml
│   ├── .github/workflows/status-transition.yml / sync-to-gitcode.yml
│   ├── .github/ISSUE_TEMPLATE/ + PULL_REQUEST_TEMPLATE.md
│   └── 标签体系
├── 配置仓库级 Secrets（BOT_TOKEN / GITCODE_TOKEN）
├── 开启分支保护（仅 public 仓库）
├── GitCode 同步建仓（元数据一致）
└── 关闭 Issue
```

## 如何申请建仓

1. 点击 [Issues](../../issues) → New Issue
2. 选择 **🏗️ 新建仓库申请** 模板
3. 填写表单信息
4. 提交后机器人将自动处理

## 申请字段

| 字段 | 必填 | 说明 |
|------|------|------|
| 初始化语言 | ✅ | 中文 / English，决定仓库初始化模板语言 |
| 仓库类型 | ✅ | 组合选项（一级分类 / 具体项目）：产品项目/SDK、示例教程/示例/Lab/Sample 等 9 项 |
| 仓库名称 | ✅ | 小写字母、数字、连字符，≤100字符 |
| 仓库描述 | ✅ | 简要描述用途 |
| 可见性 | ✅ | public / private |
| 开源许可证 | ✅ | Apache-2.0(推荐)/MIT/BSD-3-Clause（仅产品项目使用用户选择，其余强制 Apache-2.0） |
| Topics 标签 | ✅ | 逗号或换行分隔，**至少 3 个**，每个匹配 `[a-z0-9][a-z0-9.-]*` |
| Owner（管理员） | ✅ | GitHub 用户名，严格控制在 1-2 人 |
| Maintainer（维护者） | ✅ | GitHub 用户名，控制在 2-3 人 |
| Writer（写入者） | | 可选 |
| 申请理由 | ✅ | 为什么需要这个仓库 |

## 状态标签

| 标签 | 含义 |
|------|------|
| `status/pending` | 已通过校验，等待审批 |
| `status/approved` | 已批准，触发建仓 |
| `status/declined` | 已拒绝 |
| `status/completed` | 建仓完成 |
| `status/in-progress` | 正在处理 |
| `status/failed` | 处理失败 |

## 权限说明

机器人需要以下权限来创建仓库：
- 组织级别的仓库创建权限
- 通过 `BOT_TOKEN` secret 配置（需要 `repo` 和 `admin:org` scope 的 PAT）

## 本地开发

```bash
# 测试脚本
python3 scripts/repo_creator.py
```
