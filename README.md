# Telegram 群 XP 等级系统 (Python + 官方 Bot API + SQLite)

这是一个默认静默运行的 Telegram 群活跃度系统：
- 仅统计群普通消息
- 5 秒内多条消息只算 1 条
- 每日按最高档位实时补差发放 XP（当天最高 +5）
- 连续 7 天每天 >=10 条，达成当天 +5（可循环）
- 等级曲线：XP_total(L)=0.2L^2+18L，范围 Lv.1~Lv.114
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

## 4. 指令

- `/rank`：显示本群 TopN，若调用者不在 TopN，会附加显示调用者自身排名。
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
