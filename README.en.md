# 🤖 Repository Requests

> **Language:** English | [中文](./README.md)

Community contributors submit an Issue in this repository to request the creation of a new repository under the `huaweicloud` organization.

## Workflow

```
Contributor submits repo-creation Issue
        ↓
Bot processes automatically
        ↓
├── Form validation (repo name / type match / Topics≥3 / role counts)
├── Approved → create repository
├── Initialize community governance files
│   ├── README.md / LICENSE / CONTRIBUTING.md / SECURITY.md
│   ├── .github/CODEOWNERS
│   ├── .github/workflows/ci.yml / triage-issue.yml
│   ├── .github/workflows/status-transition.yml / sync-to-gitcode.yml
│   ├── .github/ISSUE_TEMPLATE/ + PULL_REQUEST_TEMPLATE.md
│   └── Label system
├── Configure repo-level Secrets (BOT_TOKEN / GITCODE_TOKEN)
├── Enable branch protection (public repos only)
├── GitCode sync (metadata consistent)
└── Close Issue
```

## How to Request a Repository

1. Go to [Issues](../../issues) → New Issue
2. Select the **🏗️ Create Repository Request** template
3. Fill in the form
4. The bot will process it automatically

## Request Fields

| Field | Required | Description |
|-------|:---:|------|
| Init Language | ✅ | 中文 / English, determines init template language |
| Repository Type | ✅ | Combined option (category / project): Product/SDK, Sample/Lab/Sample, etc. (9 options) |
| Repository Name | ✅ | Lowercase letters, digits, hyphens, ≤100 chars |
| Description | ✅ | Brief description of purpose |
| Visibility | ✅ | public / private |
| License | ✅ | Apache-2.0 (recommended) / MIT / BSD-3-Clause (user choice for Product only; others forced to Apache-2.0) |
| Topics Tags | ✅ | Comma or newline separated, **at least 3**, each matching `[a-z0-9][a-z0-9.-]*` |
| Owner (Admin) | ✅ | GitHub usernames, strictly 1-2 people |
| Maintainer | ✅ | GitHub usernames, 2-3 people |
| Writer | | Optional |
| Justification | ✅ | Why this repository is needed |

## Status Labels

| Label | Meaning |
|-------|---------|
| `status/pending` | Validation passed, awaiting approval |
| `status/approved` | Approved, triggers repo creation |
| `status/declined` | Rejected |
| `status/completed` | Repository created |
| `status/in-progress` | Processing |
| `status/failed` | Processing failed |

## Permissions

The bot needs the following permissions to create repositories:
- Organization-level repository creation permission
- Configured via `BOT_TOKEN` secret (PAT with `repo` and `admin:org` scopes)

## Local Development

```bash
# Test scripts
python3 scripts/repo_creator.py
```
