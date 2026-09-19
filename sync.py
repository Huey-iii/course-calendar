"""
课表同步主脚本 · GitHub Actions 版

从环境变量读取配置（账号密码走 GitHub Secrets），
登录教务系统 -> 抓取课表 -> 生成 calendar.ics。

用法: python sync.py
"""

import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper import JwxtScraper
from ical_gen import generate_ical


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        print(f"::error::缺少环境变量 {name}")
        sys.exit(1)
    return value


def mask(s):
    """脱敏显示，避免账号泄露到日志"""
    if not s:
        return "(空)"
    if len(s) <= 4:
        return "*" * len(s)
    return s[:2] + "*" * (len(s) - 4) + s[-2:]


def write_summary(lines):
    """写入 GitHub Actions 的 Job Summary（如果可用）"""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass


def main():
    print("=" * 56)
    print("  课表同步 · GitHub Actions")
    print("=" * 56)

    username = env("JW_USERNAME", required=True)
    password = env("JW_PASSWORD", required=True)
    base_url = env("JW_BASE_URL", "https://jwxt.zdxy.cn")
    semester_start_str = env("SEMESTER_START", "2026-09-07")
    school_name = env("SCHOOL_NAME", "正德职业技术学院")
    output_file = env("OUTPUT_FILE", "calendar.ics")
    min_events = int(env("MIN_EVENTS", "60"))

    print(f"  教务系统 : {base_url}")
    print(f"  学号     : {mask(username)}")
    print(f"  开学日期 : {semester_start_str}")
    print(f"  输出文件 : {output_file}")
    print()

    # ---------- 抓取 ----------
    scraper = JwxtScraper(username, password, base_url=base_url)

    ok, msg = scraper.login()
    if not ok:
        print(f"::error::登录教务系统失败: {msg}")
        write_summary([f"## 课表同步失败", "", f"- 原因：登录教务系统失败 — {msg}"])
        sys.exit(1)
    print(f"✅ 登录成功（{msg}）")

    courses = scraper.fetch_schedule()
    if not courses:
        print("::error::登录成功但未获取到任何课程")
        write_summary([f"## 课表同步失败", "", "- 原因：登录成功但返回 0 条课程"])
        sys.exit(1)

    adjusted = [c for c in courses if c.get("is_adjusted")]
    marker_count = {}
    for c in courses:
        mk = c.get("adjust_marker") or ""
        if mk:
            marker_count[mk] = marker_count.get(mk, 0) + 1

    print(f"✅ 获取到 {len(courses)} 条课程（带调课标记 {len(adjusted)} 条）")
    for mk, cnt in sorted(marker_count.items()):
        print(f"     {mk} × {cnt}")

    # ---------- 生成 ----------
    try:
        semester_start = datetime.strptime(semester_start_str, "%Y-%m-%d")
    except ValueError:
        print(f"::error::SEMESTER_START 格式错误: {semester_start_str}")
        sys.exit(1)

    china_tz = timezone(timedelta(hours=8))
    now_cn = datetime.now(china_tz)
    # 带上日期，方便在日历里精准判断数据的新旧
    sync_time = now_cn.strftime("%Y-%m-%d %H:%M")

    ical_data = generate_ical(
        courses, semester_start, school_name=school_name, sync_time=sync_time
    )

    with open(output_file, "wb") as f:
        f.write(ical_data)

    text = ical_data.decode("utf-8")
    n_events = text.count("BEGIN:VEVENT")
    print(f"✅ 已生成 {output_file}: {len(ical_data)} bytes / {n_events} 个事件")
    print(f"   同步标记 : （{sync_time} 同步）")

    # ---------- 安全闸门 ----------
    # 防止"抓取不完整却把线上覆盖成残缺版本"
    if n_events < min_events:
        print(f"::error::事件数异常（{n_events} < {min_events}），判定为抓取不完整，已中止，不覆盖线上")
        write_summary([
            "## 课表同步已中止",
            "",
            f"- 抓取到课程 {len(courses)} 条，但只生成 {n_events} 个事件（阈值 {min_events}）",
            "- 已保护性中止，**未覆盖线上文件**",
        ])
        sys.exit(1)

    write_summary([
        "## 课表同步成功",
        "",
        f"| 项目 | 数值 |",
        f"|---|---|",
        f"| 课程条数 | {len(courses)} |",
        f"| 日历事件 | {n_events} |",
        f"| 文件大小 | {len(ical_data):,} bytes |",
        f"| 调课标记 | {len(adjusted)} 条 |",
        f"| 同步时刻 | {sync_time} (北京时间) |",
    ])

    print()
    print("✅ 全部完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
