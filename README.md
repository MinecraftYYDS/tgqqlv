# Telegram 群 XP 等级系统 (Python + 官方 Bot API + SQLite)

这是一个默认静默运行的 Telegram 群活跃度系统：
- 仅统计群普通消息
- 5 秒内多条消息只算 1 条
- 每日按最高档位实时补差发放 XP（当天最高 +5）
- 连续 7 天每天 >=10 条，达成当天 +5（可循环）
- 等级曲线：幂函数 `3 * (level-1)^1.3`（范围 Lv.1~Lv.114，低等级更快，高等级逐步变难）
- 标签策略：仅覆盖空 tag 或 `Lv.` 前缀 tag；其他 tag 视为特殊头衔，不覆盖
- 等级头衔：可配置区间头衔，排行榜展示为 `Lv.x | [等级头衔]`
- 仅响应 `/rank`（其余默认静默）

## 1. 环境准备

1. Python 3.11+
2. 在 BotFather 获取 token
3. 将机器人加入目标群并提升为管理员，赋予 `can_manage_tags` 权限

## 2. 安装与配置

```bash
pip install -r requirements.txt
```

复制环境变量：

```bash
cp .env.example .env
```

Windows PowerShell 也可直接设置：

```powershell
$env:BOT_TOKEN="<your-token>"
$env:TOP_N="10"
$env:POLL_TIMEOUT="30"
$env:LOG_LEVEL="INFO"
$env:DB_PATH="xp_bot.sqlite3"
```

## 3. 启动

```bash
python -m src.main
```

### 3.1 批量导入加分

支持通过文本文件一次性给多人加 XP：

```bash
python -m src.main -add add_xp.txt --chat-id -1001234567890
```

批量扣分用法（同一文件格式）：

```bash
python -m src.main -del del_xp.txt --chat-id -1001234567890
```

文件格式（推荐两列，配合 `--chat-id` 使用）：

```text
# user_id xp
12345678 5
23456789 20
[34567890] [10]
```

也支持三列（每行自带 `chat_id`）：

```text
# chat_id user_id xp
-1001234567890 12345678 5
-1001234567890 23456789 20
```

说明：
- 空行和 `#` 开头行会被忽略。
- 分隔符支持空格、Tab 或逗号。
- 文件中的 XP 仅允许正整数；`-add` 表示加分，`-del` 表示按该数值扣分。
- `-del` 扣分不会把 XP 扣到 0 以下；会自动重算等级（可能降级）。
- `-del` 遇到不存在的用户会跳过并统计为 skipped。
- 可加 `--dry-run` 先校验不落库；可用 `--reason custom_reason` 自定义日志原因。

## 4. 指令

- 所有指令回复都会引用触发该指令的那条消息。
- `/rank`：显示本群 TopN，若调用者不在 TopN，会附加显示调用者自身排名；统一显示用户名（不带 `@`）。
- `/my`：显示个人信息（当前 XP、当前等级、距离下一级所需 XP、进度条）；触发时会先按当前 XP 重算等级并刷新头衔。

自动清理：
- 群内触发 `/my` 或 `/rank` 后，用户发出的命令消息和机器人回复都会在 10 秒后自动删除（需要机器人具备删除消息权限）。
- `/setlvtag 1-10 [新手] 11-20 [进阶] ...`：设置等级头衔区间。

说明：
- 群内执行 `/setlvtag`：仅群管理员可设置，作用于当前群。
- 私聊执行 `/setlvtag`：仅 `OWNER_ID` 对应用户可设置，作为全局默认规则（用于未设置群规则的群）。

## 5. 数据表

- `users`：按群用户累计 XP、等级、连续活跃状态
- `daily_stats`：按群用户按日计数、当日最高档位、5 秒合并时间戳
- `xp_logs`：XP 变动流水

## 6. 说明

- 当前实现为 Long Polling 单进程版本，适合先验证规则。
- 若后续需要高并发或多实例部署，可再升级到 Webhook + 外部队列/锁。
