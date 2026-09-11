# shanten-lens-marketplace

向听镜插件市场的静态索引仓库。仓库只登记插件来源并生成市场索引；插件源码和安装包由各插件仓库自行维护，通过 GitHub Releases 发布。

## 工作方式

```text
插件仓库发布 Release
  → 更新自己的 marketplace/update.json
  → 本仓库 GitHub Actions 定期读取更新清单
  → 下载并校验插件 ZIP
  → 生成 public/registry.json
  → 提交到 main 分支并通过 GitHub Raw 提供市场索引
```

插件首次收录、仓库迁移、维护者变更和下架需要 Pull Request。普通版本更新不需要修改本仓库。

## 仓库结构

```text
.
├─ marketplace.json              # 市场自身信息
├─ plugins/                      # 已审核的插件来源登记
│  └─ com.example.plugin.json
├─ public/
│  └─ registry.json              # 由 GitHub Actions 生成
├─ scripts/
│  └─ build_registry.py          # 索引生成与安装包校验
├─ schemas/                      # JSON Schema
│  ├─ marketplace.schema.json
│  ├─ plugin-source.schema.json
│  ├─ plugin-update.schema.json
│  └─ registry.schema.json
└─ templates/
   ├─ plugin-source.json         # 提交到本仓库的登记模板
   └─ update.json                # 放到插件仓库的更新清单模板
```

## 收录一个插件

1. 插件仓库必须公开，并使用 GitHub Release 发布 ZIP。
2. ZIP 根目录必须直接包含 `plugin.json`。
3. 插件仓库应提供稳定地址的 `marketplace/update.json`。
4. 复制 `templates/plugin-source.json` 为 `plugins/<plugin-id>.json`。
5. 填写真实信息并提交 Pull Request。

示例：

```json
{
  "schemaVersion": 1,
  "id": "com.example.packet-filter",
  "repository": "https://github.com/example/shanten-lens-packet-filter",
  "updateManifestUrl": "https://raw.githubusercontent.com/example/shanten-lens-packet-filter/main/marketplace/update.json",
  "owners": ["example"],
  "status": "active"
}
```

`owners` 用于审核后续登记信息变更。

## 插件仓库格式

推荐目录：

```text
plugin-repository/
├─ plugin.json
├─ backend/
├─ frontend/
├─ marketplace/
│  └─ update.json
└─ .github/workflows/release.yml
```

每次发布时，插件仓库自己的 Action 应构建 `plugin.zip`、计算 SHA-256、上传 Release，并更新 `marketplace/update.json`：

```json
{
  "schemaVersion": 1,
  "id": "com.example.packet-filter",
  "version": "1.3.0",
  "downloadUrl": "https://github.com/example/shanten-lens-packet-filter/releases/download/v1.3.0/plugin.zip",
  "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "size": 1258291,
  "releaseNotes": "增加规则导入功能。",
  "releaseNotesUrl": "https://github.com/example/shanten-lens-packet-filter/releases/tag/v1.3.0",
  "publishedAt": "2026-09-10T09:00:00Z"
}
```

首版只发布最新稳定版本，不定义测试频道、多平台包或版本历史。

## 固定规则

- 来源登记 ID、更新清单 ID、ZIP 内 `plugin.json.id` 必须一致。
- `downloadUrl` 必须是登记仓库中的 GitHub Release 资源。
- 版本必须使用 SemVer，且新版本必须高于市场中的现有版本。
- 同一版本不得更换 SHA-256；内容变化必须发布新版本。
- ZIP 不得包含绝对路径、`..`、符号链接或其他路径穿越内容。
- 市场展示的名称和作者以 ZIP 内 `plugin.json` 为准。
- 更新校验失败时保留上一个有效版本。
- `deprecated` 插件仍可展示，但应提示停止维护。
- `blocked` 插件禁止新安装，但客户端不得擅自删除用户本地文件。

## 第三方市场

第三方维护者可以 fork 本仓库格式，修改 `marketplace.json`，并通过 GitHub Raw 提供自己的 `public/registry.json`。向听镜通过索引 URL 添加第三方市场，例如：

```text
https://raw.githubusercontent.com/<owner>/<repository>/main/public/registry.json
```

## 索引更新

GitHub Actions 每 6 小时检查一次插件更新，也可手动触发。索引内容发生变化时，Action 会更新并提交 `public/registry.json`；单个插件校验失败时保留其上一个有效版本。
