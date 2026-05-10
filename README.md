# astrbot_plugin_guardian — Bot 守护者插件

> 全天候监测群内辱骂行为，自动拉黑 + QQ 邮件通知 + 控制台管理界面  
> 适配 **AstrBot 4.24.x**

---

## ✨ 功能一览

| 功能 | 说明 |
|------|------|
| 🔍 全天监测 | 监听群内**所有消息**（非@Bot 和 @Bot 两种场景同时覆盖） |
| 🤖 辱骂检测 | 多策略模糊匹配（直接包含 / 去空格 / 滑动窗口相似度） |
| 🚫 自动拉黑 | 检测到辱骂后立即加入内部黑名单，功能全部禁用 |
| 🔇 自动禁言 | 可配置：在群内自动禁言（需 Bot 管理员权限） |
| 👢 自动踢出 | 可配置：自动踢出群聊（需 Bot 管理员权限） |
| 📧 邮件通知 | 拉黑后向被拉黑者的 QQ 邮箱发送通知，告知申诉方式 |
| 📋 控制台展示 | 每次黑名单变动均在 AstrBot 控制台打印完整列表 |
| 🛠️ 命令管理 | 通过 `/guardian` 命令查看/手动拉黑/解除/管理关键词 |

---

## 📁 安装方法

1. 将整个 `astrbot_plugin_guardian/` 文件夹放入 AstrBot 的插件目录：
   ```
   data/plugins/astrbot_plugin_guardian/
   ```
2. 在 AstrBot 控制台 → 插件 → 重载插件，或重启 AstrBot。
3. 在插件配置中填写 QQ 邮箱信息（可选，不填则跳过邮件通知）。

---

## ⚙️ 配置说明

在 AstrBot 控制台的插件配置页面或直接编辑 `_conf_schema.json` 修改：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `bot_name` | `Monika` | Bot 的名字 |
| `keywords` | 见下方 | 内置辱骂关键词列表 |
| `fuzzy_threshold` | `0.75` | 模糊匹配阈值（0~1，越低越宽松） |
| `admin_email` | `carenb666@foxmail.com` | 管理员邮箱（用于申诉） |
| `qq_email` | `""` | 发件 QQ 邮箱（如 `123@qq.com`） |
| `qq_email_auth_code` | `""` | QQ 邮箱**授权码**（非QQ密码） |
| `auto_mute` | `true` | 是否自动禁言 |
| `mute_duration` | `2592000` | 禁言时长（秒），30天 |
| `auto_kick` | `false` | 是否自动踢出群聊 |

### 获取 QQ 邮箱授权码
1. 打开 QQ 邮箱网页版 → 设置 → 账户
2. 开启「POP3/SMTP 服务」
3. 按提示生成授权码，填入 `qq_email_auth_code`

---

## 💬 命令使用

所有命令以 `/guardian` 开头，建议只有管理员使用。

### 黑名单管理
```
/guardian list                  # 查看黑名单列表（控制台同步刷新）
/guardian block 123456789       # 手动拉黑 QQ 号
/guardian block 123456789 原因  # 手动拉黑并备注原因
/guardian unblock 123456789     # 解除黑名单
```

### 关键词管理
```
/guardian kw list               # 查看全部关键词
/guardian kw add 臭bot          # 添加自定义关键词
/guardian kw remove 臭bot       # 删除自定义关键词
/guardian kw clear              # 清空所有自定义关键词
```

### 其他
```
/guardian status                # 查看插件运行状态
/guardian test 你这个废物bot     # 测试某段文字是否会触发检测
/guardian help                  # 显示帮助
```

---

## 🔍 检测逻辑

```
收到群消息
    ├── 发送者在黑名单？ → 拦截并提示 + 阻断 LLM
    └── 不在黑名单？
            ├── 场景A：用户 @Bot + 消息含辱骂关键词 → 拉黑
            └── 场景B：普通消息（不@Bot）+ 消息含辱骂关键词 → 拉黑
```

**模糊匹配策略（三重）：**
1. 直接字符串包含（最快）
2. 去空格后匹配（防止 `傻 逼` 绕过）
3. 滑动窗口相似度（防止谐音/近似词绕过）

---

## ⚠️ 注意事项

1. **Bot 需要群管理员权限** 才能使用禁言/踢出功能（`auto_mute` / `auto_kick`）。
2. 如果使用的不是 **OneBot (aiocqhttp/NakuruProject)** 协议端，禁言/踢出功能可能无效，但内部黑名单和邮件通知仍然正常工作。
3. QQ 邮箱发件需要对方的 QQ 号邮箱能正常接收，若对方关闭了 QQ 邮箱，邮件可能无法送达。
4. 模糊阈值建议保持在 `0.70~0.80`，过低容易误判正常消息。
5. 黑名单数据保存在插件目录下的 `guardian_data.json`，请勿手动删除。

---

## 📝 数据文件

`guardian_data.json` 格式：
```json
{
  "blacklist": {
    "123456789": {
      "reason": "群聊中辱骂（关键词「傻逼」）：你这个傻逼bot",
      "time": "2024-01-01 12:00:00",
      "group_id": "987654321"
    }
  },
  "custom_keywords": ["臭bot", "蠢东西"]
}
```

---

## 🗑️ 卸载

删除 `data/plugins/astrbot_plugin_guardian/` 目录即可，数据文件随插件目录一并删除。
