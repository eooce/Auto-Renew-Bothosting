## 🚀 Bot-hosting 自动续期（GitHub Actions）

这是一个基于 GitHub Actions 的自动化脚本，用于定时登录自动续期 [Bot-hosting](https://bot-hosting.net) 服务。

━━━━━━━━━━━━━━━━━━━━━━

### 🔐 Secrets 配置说明

| Secret 名称         | 是否必填 | 说明                                              |
|---------------------|----------|---------------------------------------------------|
| EMAIL              | ❌ 可选  | 用于通知使用的Email,可随意填写                          |
| SESSION_TOKEN      | ✅ 必填  | Bot-hosting session_token，cookie里获取               |
| GH_TOKEN           | ✅ 必填  | GitHub(classic) toekn,用于自动更新session_token,以ghp_xxx开头|
| NODE_LINK          | ❌ 可选  | 完整代理链接（如 vless:// vmess:// trojan:// hysteria2:// tuic:// anytls:// socks5:// )|
| TG_BOT_TOKEN       | ❌ 可选  | Telegram Bot Token（用于发送通知）                      |
| TG_CHAT_ID         | ❌ 可选  | Telegram Chat ID（接收通知的用户或群组 ID）               |

━━━━━━━━━━━━━━━━━━━━━━

## 部署步骤
1：fork 本项目，在actions菜单允许工作流

2：在`setting`➡`secrets and variables`➡`Actions` 里添加上方必填的secrets

3：去actions菜单手动试运行工作流,根据自己的服务到期日期自行在[renew.yml](.github/workflows/renew.yml)里调整cron运行时间

### SESSION_TOKEN 获取
登录你的账号,按F12或页面空白处 右键➡检查➡选择应用程序或appcations 找到对应的字段点击获取对应的值，详情如图
<img width="1200" height="600" alt="image" src="https://github.com/user-attachments/assets/e532b0d6-9f12-45fd-8af9-69e1029a1a92" />

DISCORD_TOKEN 获取（用于 SESSION_TOKEN 失效后备用登录
浏览器登录 Discord（网页版）
按 F12 打开开发者工具 ➡ 网络 ➡ 点击任意频道 ➡ 选择左侧的任意api
找到名为 authorization字段 的 值，即为discord token,详情如图所示

<a href="https://tc.alex.nyc.mn/api/cfile/AgACAgUAAxkDAAIQDGqSWecr3R_i5PkBqwLlqSffxV_0AAK6D2sbYqyZVLSba2E03K7vAQADAgADeQADPQQ" target="_blank"><img src="https://tc.alex.nyc.mn/api/cfile/AgACAgUAAxkDAAIQDGqSWecr3R_i5PkBqwLlqSffxV_0AAK6D2sbYqyZVLSba2E03K7vAQADAgADeQADPQQ"></a>

作用：当 SESSION_TOKEN 过期导致登录失败时，脚本会自动使用 Discord Token 走 OAuth 流程重新登录，并自动更新 SESSION_TOKEN Secret，实现永久免维护。

### 获取 `GH_TOKEN`(GitHub Personal Access Token)
1：点击GitHub 账户右上角头像 → Settings（设置）。

2：左侧菜单底部点击 Developer settings（开发者设置）。

3：点击 Personal access tokens → Tokens (classic)。

4：点击 Generate new token → Generate new token (classic)。

填写信息：
- Note：起一个描述性名称（如 my-token）。
- Expiration：选择过期时间（建议选No expiration永不过期）。
- Select scopes：勾选所需权限（不知道如何勾选就全部勾选）。
- 点击 Generate token，立即复制并妥保存生成的 token（离开页面后不能再查看）。

## 注意事项
* 必填变量必须要填写
* NODE_LINK支持的代理协议有：vmess,vless,hysteria2,tuic,anytls,socks5等
* 自动续期不代表可以无底线的薅羊毛,不建议多账号
* cron运行时间不一定准确,得根据实际到期时间修改,可在设置里暂停actions功能再开启

## ⚠️ 免责声明
* 本程序仅供学习了解, 非盈利目的，如转载须注明来源。
* 使用本程序必循遵守部署服务器所在地、所在国家和用户所在国家的法律法规, 程序作者不对使用者任何不当行为负责。
