#!/usr/bin/env python3

"""

huaweicloud 建仓机器人 — 按 GOAT 建仓流程文档 v1.1

支持 9 种仓库类型 → 4 个等级初始化（2~17 项）

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


def normalize_repo_type_combo(combo):
    """将英文表单的组合选项映射为内部统一的中文组合。

    英文示例: Product/SDK、Sample/Lab/Sample、Documentation/Docs/Dataset、Internal/Internal Config
    """
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
    # 去空格比较，容忍差异
    norm = combo.replace(" ", "")
    for en, zh in mapping:
        if norm == en.replace(" ", ""):
            return zh
    return combo





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




# ─── LICENSE 全文模板 ───

LICENSE_APACHE2 = """                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.

      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.

      "Licensor" shall mean the copyright owner or entity authorized by
      the copyright owner that is granting the License.

      "Legal Entity" shall mean the union of the acting entity and all
      other entities that control, are controlled by, or are under common
      control with that entity. For the purposes of this definition,
      "control" means (i) the power, direct or indirect, to cause the
      direction or management of such entity, whether by contract or
      otherwise, or (ii) ownership of fifty percent (50%) or more of the
      outstanding shares, or (iii) beneficial ownership of such entity.

      "You" (or "Your") shall mean an individual or Legal Entity
      exercising permissions granted by this License.

      "Source" form shall mean the preferred form for making modifications,
      including but not limited to software source code, documentation
      source, and configuration files.

      "Object" form shall mean any form resulting from mechanical
      transformation or translation of a Source form, including but
      not limited to compiled object code, generated documentation,
      and conversions to other media types.

      "Work" shall mean the work of authorship, whether in Source or
      Object form, made available under the License, as indicated by a
      copyright notice that is included in or attached to the work
      (an example is provided in the Appendix below).

      "Derivative Works" shall mean any work, whether in Source or Object
      form, that is based on (or derived from) the Work and for which the
      editorial revisions, annotations, elaborations, or other modifications
      represent, as a whole, an original work of authorship. For the purposes
      of this License, Derivative Works shall not include works that remain
      separable from, or merely link (or bind by name) the references of,
      the Work.

      "Contribution" shall mean any work of authorship, including
      the original version of the Work and any modifications or additions
      to that Work or Derivative Works thereof, that is intentionally
      submitted to Licensor for inclusion in the Work by the copyright owner
      or by an individual or Legal Entity authorized to submit on behalf of
      the copyright owner. For the purposes of this definition, "submitted"
      means any form of electronic, verbal, or written communication sent
      to the Licensor or its representatives, including but not limited to
      communication on electronic mailing lists, source code control systems,
      and issue tracking systems that are managed by, or on behalf of, the
      Licensor for the purpose of discussing and improving the Work, but
      excluding communication that is conspicuously marked or otherwise
      designated in writing by the copyright owner as "Not a Contribution."

      "Contributor" shall mean Licensor and any individual or Legal Entity
      on behalf of whom a Contribution has been received by Licensor and
      subsequently incorporated within the Work.

   2. Grant of Copyright License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      copyright license to reproduce, prepare Derivative Works of,
      publicly display, publicly perform, sublicense, and distribute the
      Work and such Derivative Works in Source or Object form.

   3. Grant of Patent License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      (except as stated in this section) patent license to make, have made,
      use, offer to sell, sell, import, and otherwise transfer the Work,
      where such license applies only to those patent claims licensable
      by such Contributor that are necessarily infringed by their
      Contribution(s) alone or by combination of their Contribution(s)
      with the Work to which such Contribution(s) was submitted. If You
      institute patent litigation against any entity (including a
      cross-claim or counterclaim in a lawsuit) alleging that the Work
      or a Contribution incorporated within the Work constitutes direct
      or contributory patent infringement, then any patent licenses
      granted to You under this License for that Work shall terminate
      as of the date such litigation is filed.

   4. Redistribution. You may reproduce and distribute copies of the
      Work or Derivative Works thereof in any medium, with or without
      modifications, and in Source or Object form, provided that You
      meet the following conditions:

      (a) You must give any other recipients of the Work or
          Derivative Works a copy of this License; and

      (b) You must cause any modified files to carry prominent notices
          stating that You changed the files; and

      (c) You must retain, in the Source form of any Derivative Works
          that You distribute, all copyright, patent, trademark, and
          attribution notices from the Source form of the Work,
          excluding those notices that do not pertain to any part of
          the Derivative Works; and

      (d) If the Work includes a "NOTICE" text file as part of its
          distribution, then any Derivative Works that You distribute must
          include a readable copy of the attribution notices contained
          within such NOTICE file, excluding those notices that do not
          pertain to any part of the Derivative Works, in at least one
          of the following places: within a NOTICE text file distributed
          as part of the Derivative Works; within the Source form or
          documentation, if provided along with the Derivative Works; or,
          within a display generated by the Derivative Works, if and
          wherever such third-party attribution notices normally appear.
          The content of the NOTICE file is for informational purposes only
          and does not modify the License. You may add Your own attribution
          notices within Derivative Works that You distribute, alongside
          or as an addendum to the NOTICE text from the Work, provided
          that such additional attribution notices cannot be construed
          as modifying the License.

      You may add Your own copyright statement to Your modifications and
      may provide additional or different license terms and conditions
      for use, reproduction, or distribution of Your modifications, or
      for any such Derivative Works as a whole, provided Your use,
      reproduction, and distribution of the Work otherwise complies with
      the conditions stated in this License.

   5. Submission of Contributions. Unless You explicitly state otherwise,
      any Contribution intentionally submitted for inclusion in the Work
      by You to the Licensor shall be under the terms and conditions of
      this License, without any additional terms or conditions.
      Notwithstanding the above, nothing herein shall supersede or modify
      the terms of any separate license agreement you may have executed
      with Licensor regarding such Contributions.

   6. Trademarks. This License does not grant permission to use the trade
      names, trademarks, service marks, or product names of the Licensor,
      except as required for reasonable and customary use in describing the
      origin of the Work and reproducing the content of the NOTICE file.

   7. Disclaimer of Warranty. Unless required by applicable law or
      agreed to in writing, Licensor provides the Work (and each
      Contributor provides its Contributions) on an "AS IS" BASIS,
      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
      implied, including, without limitation, any warranties or conditions
      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
      PARTICULAR PURPOSE. You are solely responsible for determining the
      appropriateness of using or redistributing the Work and assume any
      risks associated with Your exercise of permissions under this License.

   8. Limitation of Liability. In no event and under no legal theory,
      whether in tort (including negligence), contract, or otherwise,
      unless required by applicable law (such as deliberate and grossly
      negligent acts) or agreed to in writing, shall any Contributor be
      liable to You for damages, including any direct, indirect, special,
      incidental, or consequential damages of any character arising as a
      result of this License or out of the use or inability to use the
      Work (including but not limited to damages for loss of goodwill,
      work stoppage, computer failure or malfunction, or any and all
      other commercial damages or losses), even if such Contributor
      has been advised of the possibility of such damages.

   9. Accepting Warranty or Additional Liability. While redistributing
      the Work or Derivative Works thereof, You may choose to offer,
      and charge a fee for, acceptance of support, warranty, indemnity,
      or other liability obligations and/or rights consistent with this
      License. However, in accepting such obligations, You may act only
      on Your own behalf and on Your sole responsibility, not on behalf
      of any other Contributor, and only if You agree to indemnify,
      defend, and hold each Contributor harmless for any liability
      incurred by, or claims asserted against, such Contributor by reason
      of your accepting any such warranty or additional liability.

   END OF TERMS AND CONDITIONS

   Copyright 2024 huaweicloud

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""

LICENSE_MIT = """MIT License

Copyright (c) 2024 huaweicloud

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

LICENSE_BSD3 = """BSD 3-Clause License

Copyright (c) 2024 huaweicloud

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

LICENSE_TEXTS = {
    "Apache-2.0": LICENSE_APACHE2,
    "MIT": LICENSE_MIT,
    "BSD-3-Clause": LICENSE_BSD3,
}




def get_license_text(license_name):
    """返回指定许可证的全文（默认 Apache-2.0）"""
    return LICENSE_TEXTS.get(license_name, LICENSE_APACHE2)





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


# ─── README 模板（英文版，9套） ───

README_TEMPLATES_EN = {

    "SDK": """# {name}

[![License](https://img.shields.io/badge/License-{license}-blue.svg)](LICENSE)



{description}



## Installation

```bash

pip install {name}

```



## API Reference

TBD



## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)



## License

This project is licensed under the {license} license.

""",

    "Terraform Provider": """# {name}

[![License](https://img.shields.io/badge/License-{license}-blue.svg)](LICENSE)



{description}



## Provider Configuration

```hcl

provider "{name}" {{

  # configuration

}}

```



## Resource / DataSource List

TBD



## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

""",

    "GitHub Action": """# {name}

[![License](https://img.shields.io/badge/License-{license}-blue.svg)](LICENSE)



{description}



## Inputs

| Input | Type | Required | Default | Description |

|-------|------|----------|---------|-------------|



## Outputs

| Output | Description |

|--------|-------------|



## Usage Example

```yaml

- uses: huaweicloud/{name}@v1

  with:

    param: value

```



## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

""",

    "框架集成": """# {name}

[![License](https://img.shields.io/badge/License-{license}-blue.svg)](LICENSE)



{description}



## Quick Start

```bash

pip install {name}

```



## Configuration

TBD



## Version Compatibility

| Version | Compatible Language / Framework | Status |

|---------|--------------------------------|--------|



## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

""",

    "Exporter / Plugin": """# {name}

[![License](https://img.shields.io/badge/License-{license}-blue.svg)](LICENSE)



{description}



## Deployment

```bash

docker run -d --name {name} huaweicloud/{name}:latest

```



## Metrics

TBD



## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

""",

    "IoT SDK": """# {name}

[![License](https://img.shields.io/badge/License-{license}-blue.svg)](LICENSE)



{description}



## Hardware Requirements

TBD



## Device Connection Example

```python

from {name} import Device

device = Device("device-id")

device.connect()

```



## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

""",

    "示例 / Lab / Sample": """# {name}



{description}



## Prerequisites

- Language environment

- Dependencies installed



## Run Steps

```bash

# Run the sample

```



## Screenshots / Output

TBD

""",

    "文档 / 数据集": """# {name}



{description}



## Content

TBD



## Usage

TBD

""",

    "内部配置": """# {name}



{description}



> Internal configuration repository



## Purpose

TBD



## Usage

TBD

""",

}





def make_readme(name, repo_type, license_name, description, lang="zh"):

    if lang == "en":

        tmpl = README_TEMPLATES_EN.get(repo_type, README_TEMPLATES_EN["SDK"])

    else:

        tmpl = README_TEMPLATES.get(repo_type, README_TEMPLATES["SDK"])

    return tmpl.format(name=name, license=license_name, description=description)





# ─── 文件模板 ───

CONTRIBUTING_MD_EN = """# Contributing to {name}



## Development Setup

See README.



## Commit Convention

Use conventional commits: `feat:`, `fix:`, `docs:`, `style:`, `refactor:`, `test:`, `chore:`



## Pull Request Workflow

1. Fork the repository

2. Create a branch `feat/xxx`

3. Commit your changes

4. Open a Pull Request

5. At least 2 reviewers approve and CI passes before merge



## Issue Guidelines

Use the Bug Report / Feature Request templates

"""



SECURITY_MD_EN = """# Security Policy



## Reporting Security Vulnerabilities

If you discover a security vulnerability, please send an email to huaweicloud@huawei.com. **Do NOT disclose it in a public Issue.**



## Supported Versions

| Version | Supported |

|---------|-----------|

| Latest  | Active support |

"""



COC_MD_EN = """# Contributor Covenant Code of Conduct



## Our Pledge

We as members, contributors, and leaders pledge to make participation in our community a harassment-free experience for everyone.



## Our Standards

- Use welcoming and inclusive language

- Respect differing viewpoints and experiences

- Accept constructive criticism gracefully



## Enforcement

Instances of abusive behavior may be reported to the project maintainers.

"""



BUG_REPORT_YML_EN = """name: Bug Report

description: Report a bug

labels: ["type/bug"]

body:

  - type: textarea

    attributes:

      label: Description

      description: What happened

    validations:

      required: true

  - type: textarea

    attributes:

      label: Steps to Reproduce

  - type: textarea

    attributes:

      label: Expected Behavior

  - type: textarea

    attributes:

      label: Environment

"""



FEATURE_YML_EN = """name: Feature Request

description: Request a new feature

labels: ["type/feature"]

body:

  - type: textarea

    attributes:

      label: Description

      description: What feature would you like to add

    validations:

      required: true

  - type: textarea

    attributes:

      label: Use Case

"""



PR_TEMPLATE_EN = """## Change Summary



## Related Issue

Fixes #



## Testing

- [ ] Unit tests passed

- [ ] Manual testing passed

"""



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

      - name: Checkout .github org repo

        uses: actions/checkout@v4

        with:

          repository: ${{ github.repository_owner }}/.github

          path: .github-repo

          ref: main

          token: ${{ secrets.BOT_TOKEN }}

      - name: Set up Python

        uses: actions/setup-python@v5

        with:

          python-version: '3.12'

      - name: Run Issue Bot

        env:

          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

          GITHUB_EVENT_PATH: ${{ github.event_path }}

          GITHUB_EVENT_NAME: ${{ github.event_name }}

          GITHUB_REPOSITORY: ${{ github.repository }}

        run: python3 .github-repo/actions/issue-bot/issue_bot.py

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



# 类型标签（统一使用 type/feature，不用 type/enhancement）
LABELS_TYPE = ["type/bug", "type/feature", "type/question", "type/documentation"]

# 优先级标签
LABELS_PRIORITY = ["priority/critical", "priority/high", "priority/medium", "priority/low"]

# 状态标签
LABELS_STATUS = ["status/pending", "status/triaged", "status/in-progress", "status/resolved",
                 "status/completed", "status/stale", "status/blocked"]

# 领域标签
LABELS_AREA = ["area/api", "area/web", "area/ci-cd", "area/sdk", "area/security",
               "area/performance", "area/database"]

# SLA / 自动化标签
LABELS_SLA = ["sla/breach", "sla/warning", "escalation"]

# 机器人 / 社区标签
LABELS_COMMUNITY = ["agent/triaged", "good first issue", "help wanted"]

# 产品级完整标签（28 个）
LABELS_PRODUCT = (LABELS_TYPE + LABELS_PRIORITY + LABELS_STATUS + LABELS_AREA
                  + LABELS_SLA + LABELS_COMMUNITY)

# 示例级标签（type + priority，8 个）
LABELS_SAMPLE = LABELS_TYPE + LABELS_PRIORITY





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




def setup_repo_secrets(repo):
    """为新仓库配置仓库级 secrets（BOT_TOKEN 等），确保注入的 workflow 可访问。

    组织级 secret 对新建仓库传播有延迟/限制，因此建仓时显式写入仓库级 secrets。
    使用 GitHub Actions secrets 加密流程（公钥 + nacl sealed box）。
    """
    try:
        import base64
        from nacl import encoding, public

        secrets_map = {}
        if BOT_TOKEN:
            secrets_map["BOT_TOKEN"] = BOT_TOKEN
        if GITCODE_TOKEN:
            secrets_map["GITCODE_TOKEN"] = GITCODE_TOKEN

        for name, value in secrets_map.items():
            # 获取仓库 public key
            key_data = api("GET", f"/repos/{ORG}/{repo}/actions/secrets/public-key", "bot")
            if not key_data or "key" not in key_data:
                print(f"[{repo}] Failed to get public key for secret {name}")
                continue
            pub_key_b64 = key_data["key"]
            key_id = key_data["key_id"]

            # 用 nacl sealed box 加密
            pub_key = public.PublicKey(pub_key_b64, encoding.Base64Encoder())
            sealed_box = public.SealedBox(pub_key)
            encrypted = sealed_box.encrypt(value.encode("utf-8"))
            enc_b64 = base64.b64encode(encrypted).decode("utf-8")

            result = api("PUT", f"/repos/{ORG}/{repo}/actions/secrets/{name}", "bot",
                         {"encrypted_value": enc_b64, "key_id": key_id})
            print(f"[{repo}] Secret {name} configured")
    except Exception as e:
        print(f"[{repo}] setup_repo_secrets failed: {e}")





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




def setup_branch_protection(repo, private):
    """为仓库配置 main 分支保护。

    仅 public 仓库启用（private 仓库受 GitHub Free 计划限制无法配置分支保护）。
    配置：2 人 Approve、Code Owner Review、过期 Review 作废、严格 CI 检查。
    """
    if private:
        print(f"[{repo}] Private repo, skip branch protection (Free plan limitation)")
        return

    branch = "main"
    # 确认分支存在（新仓库默认 main）
    br = api("GET", f"/repos/{ORG}/{repo}/branches/{branch}", "bot")
    if not br or "name" not in br:
        print(f"[{repo}] Branch {branch} not found, skip protection")
        return

    payload = {
        "required_status_checks": {
            "strict": True,
            "contexts": ["lint", "test", "build"],
        },
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "required_approving_review_count": 2,
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True,
        },
        "restrictions": None,
    }
    result = api("PUT", f"/repos/{ORG}/{repo}/branches/{branch}/protection", "bot", payload)
    print(f"[{repo}] Branch protection configured (2 approve + codeowner + strict CI)")



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
    # 同时支持中英文表单字段

    lines = body.split("\n")

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



    # 组合选项格式: "一级分类 / 二级类型"，拆分出分类与类型（容忍空格差异）
    # 支持英文表单组合（Product/SDK 等），映射为内部统一的中文分类与类型
    repo_type_combo = fields.get("仓库类型", "产品项目 / SDK")

    repo_type_combo = normalize_repo_type_combo(repo_type_combo)

    repo_category, repo_type = parse_repo_type_combo(repo_type_combo)

    if not repo_type:

        repo_type = "SDK"

    # 初始化语言（中英文表单均可选择）
    lang_raw = (fields.get("初始化语言", "") or "").strip()

    init_lang = "en" if lang_raw.lower().startswith("english") else "zh"

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



    # init files（按语言选择模板）

    readme = make_readme(repo_name, repo_type, license_name, description, lang=init_lang)

    create_file(repo_name, "README.md", readme, "Init README")

    create_file(repo_name, "LICENSE", get_license_text(license_name), f"Add {license_name} license")
    # L1 基线: CODEOWNERS（所有等级）
    create_file(repo_name, ".github/CODEOWNERS", CODEOWNERS_MD, "Add CODEOWNERS")

    contributing_md = CONTRIBUTING_MD_EN if init_lang == "en" else CONTRIBUTING_MD
    security_md = SECURITY_MD_EN if init_lang == "en" else SECURITY_MD
    coc_md = COC_MD_EN if init_lang == "en" else COC_MD
    bug_yaml = BUG_REPORT_YML_EN if init_lang == "en" else BUG_REPORT_YML
    feature_yaml = FEATURE_YML_EN if init_lang == "en" else FEATURE_YML
    pr_template = PR_TEMPLATE_EN if init_lang == "en" else PR_TEMPLATE




    if level in ("product", "sample"):
        # L1 增强: CI + CONTRIBUTING（产品/示例需要 CI 验证）
        create_file(repo_name, ".github/workflows/ci.yml", CI_WORKFLOW, "Add CI workflow")

        create_file(repo_name, "CONTRIBUTING.md", contributing_md.format(name=repo_name), "Add contributing guide")

    if level == "product":

        create_file(repo_name, "SECURITY.md", security_md, "Add security policy")

        create_file(repo_name, "CODE_OF_CONDUCT.md", coc_md, "Add code of conduct")

    if level in ("product", "sample"):

        create_file(repo_name, ".github/ISSUE_TEMPLATE/bug_report.yml", bug_yaml, "Add bug template")

        create_file(repo_name, ".github/ISSUE_TEMPLATE/feature_request.yml", feature_yaml, "Add feature template")

        create_file(repo_name, ".github/ISSUE_TEMPLATE/config.yml", CONFIG_YML, "Add issue config")

        create_file(repo_name, ".github/PULL_REQUEST_TEMPLATE.md", pr_template, "Add PR template")

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

    # 配置仓库级 secrets（BOT_TOKEN），确保 triage 等 workflow 可访问 .github action
    setup_repo_secrets(repo_name)



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



    # configure branch protection (public repos only)
    setup_branch_protection(repo_name, private=(visibility == "private"))

    # create GitCode mirror (metadata consistent with GitHub)
    gitcode_url = create_gitcode_repo(repo_name, description, private=(visibility == "private"))



    # close issue

    init_count = {"product": 17, "sample": 11, "docs": 5, "internal": 4}[level]

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

