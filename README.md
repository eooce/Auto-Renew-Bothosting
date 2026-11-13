## 🚀 Bot-hosting 自动续期（GitHub Actions）

这是一个基于 GitHub Actions 的自动化脚本，用于定时登录自动续期 [Bot-hosting](https://bot-hosting.net) 服务。

⚠️ 有cf盾,太垃圾的机房节点可能过不了，建议用稍微干净点的节点,[B2proxy住宅代理](https://www.b2proxy.com/signup?code=0F5133)

━━━━━━━━━━━━━━━━━━━━━━

### 之前用Discord Token登录的方式仍然可用，Discord token有时会变化，用账号密码更稳定。

━━━━━━━━━━━━━━━━━━━━━━

### 🔐 Secrets 配置说明

| Secret 名称         | 是否必填 | 说明                                              |
|---------------------|----------|---------------------------------------------------|
| EMAIL              | ✅ 必填  | 登录和通知使用的Email,必须填写                          |
| PASSWORD           | ✅ 必填  | 登录密码,必填,在控制台右上角头像里去设置                 |
| NODE_LINK          | ❌ 可选  | 代理链接（如 vless:// vmess:// trojan:// hysteria2:// tuic:// anytls:// socks5:// )|
| MP_URL             | ❌ 可选  | MoviePilot 访问地址，如 `mp.example.com`（不写协议默认走 https），需与 MP_APIKEY 一起配置 |
| MP_APIKEY          | ❌ 可选  | MoviePilot UrlNotify 插件的 apikey（用于发送通知）                 |
| MP_CHANNEL         | ❌ 可选  | 通知渠道（Wechat/Feishu/Telegram/Slack 等），不填则使用插件默认配置    |
| MP_MTYPE           | ❌ 可选  | 消息类型（如 Plugin），不填则使用插件默认配置                        |

> 通知通过 MoviePilot 的 `/api/v1/plugin/UrlNotify/send` 接口发送，默认由插件侧转发到企业微信。

━━━━━━━━━━━━━━━━━━━━━━

## 部署步骤
1：fork 本项目，在actions菜单允许工作流

2：在`setting`➡`secrets and variables`➡`Actions` 里添加上方必填的secrets

3：去actions菜单手动试运行工作流,根据自己的服务到期日期自行在[renew.yml](.github/workflows/renew.yml)里调整cron运行时间


## 注意事项
* 必填变量必须要填写
* NODE_LINK支持的代理协议有：vmess,vless,hysteria2,tuic,anytls,socks5等
* 自动续期不代表可以无底线的薅羊毛,不建议多账号
* cron运行时间不一定准确,得根据实际到期时间修改,可在设置里暂停actions功能再开启

## ⚠️ 免责声明
* 本程序仅供学习了解, 非盈利目的，如转载须注明来源。
* 使用本程序必循遵守部署服务器所在地、所在国家和用户所在国家的法律法规, 程序作者不对使用者任何不当行为负责。
