# 课表自动同步

正德职业技术学院教务系统课表 → iCal 日历订阅文件，由 GitHub Actions 定时自动更新。

## 工作原理

```
GitHub Actions（每 2 小时，仅白天）
      ↓ 登录教务系统
      ↓ 抓取课表 + 调课记录
      ↓ 生成 calendar.ics
      ↓ 提交回本仓库
```

运行在 GitHub 的服务器上，**不依赖任何一台个人电脑开机**。

## 需要的配置

在仓库 `Settings → Secrets and variables → Actions` 中配置：

### Secrets（必填）

| 名称 | 说明 |
|---|---|
| `JW_USERNAME` | 教务系统学号 |
| `JW_PASSWORD` | 教务系统密码 |
| `JW_BASE_URL` | 教务系统地址，如 `https://jwxt.zdxy.cn` |

### Variables（可选，不填则用下面的默认值）

| 名称 | 默认值 | 说明 |
|---|---|---|
| `SEMESTER_START` | `2026-09-07` | 第 1 周的周一日期 |
| `SCHOOL_NAME` | `正德职业技术学院` | 日历显示名称 |

## 手动触发

`Actions` → 左侧 `课表同步` → 右侧 `Run workflow`。

## 日程频率

在 `.github/workflows/sync.yml` 的 `cron` 一行修改。当前为 `0 0-14/2 * * *`，
即 UTC 时间 0/2/4/…/14 点，对应**北京时间 8:00 ~ 22:00 每 2 小时一次**。

## 安全阀

若抓取到的事件数低于 `MIN_EVENTS`（默认 60），脚本会**主动中止且不覆盖**
`calendar.ics`，避免把线上文件刷成残缺版本。

## 调课标记

| 标记 | 含义 |
|---|---|
| 🔴 | 换教室 |
| 🔵 | 调时间 / 调周次 |
| 🟠 | 换教师 |

标记会追加在日历事件的标题末尾，详细变化写在事件备注的最后一行。
