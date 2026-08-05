# 🤖 Repository Requests

社区贡献者在此仓库提交 Issue 来申请在 `huaweicloud` 组织下创建新仓库。

## 工作流程

```
贡献者提交建仓 Issue
        ↓
机器人自动处理
        ↓
├── 验证仓库名称
├── 检查是否重名
├── 创建仓库
├── 初始化社区治理配置
│   ├── CONTRIBUTING.md
│   ├── SECURITY.md
│   ├── .github/dependabot.yml
│   ├── .github/stale.yml
│   ├── .github/ISSUE_TEMPLATE/
│   ├── .github/workflows/triage-issue.yml
│   └── 标签体系
├── 启用安全功能
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
| 仓库名称 | ✅ | 小写字母、数字、连字符 |
| 仓库描述 | ✅ | 简要描述用途 |
| 可见性 | ✅ | public / private |
| 主要编程语言 | ✅ | Python/TypeScript/Go/Java/Rust/C++/Shell/Other |
| 开源许可证 | ✅ | Apache-2.0/MIT/GPL-3.0/BSD-3-Clause/无 |
| Topics | ❌ | 逗号分隔的标签 |
| 申请理由 | ✅ | 为什么需要这个仓库 |

## 状态标签

| 标签 | 含义 |
|------|------|
| `status/pending` | 等待处理 |
| `status/in-progress` | 正在处理 |
| `status/completed` | 已完成 |
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
