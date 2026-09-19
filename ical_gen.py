"""
iCal 日历生成器
将课表数据转换为 Apple Calendar 可订阅的 .ics 格式文件
"""

from datetime import datetime, timedelta
import hashlib

from icalendar import Calendar, Event, vText


# 节次时间映射（正德职业技术学院标准作息）
# 上午: 1-2节 8:00-9:40 | 3-4节 10:20-12:00
# 下午: 5-6节 14:00-15:40 | 7-8节 15:50-17:30
# 晚上: 9-10节 18:30-20:10
PERIOD_TIMES = {
    1: ("08:00", "08:45"),
    2: ("08:55", "09:40"),
    3: ("10:20", "11:05"),
    4: ("11:15", "12:00"),
    5: ("14:00", "14:45"),
    6: ("14:55", "15:40"),
    7: ("15:50", "16:35"),
    8: ("16:45", "17:30"),
    9: ("18:30", "19:15"),
    10: ("19:25", "20:10"),
}


# 调课彩圈「最影响上课」优先级：换教室 > 调时间 > 换教师
ADJUST_MARKER_PRIORITY = {"🔴": 3, "🔵": 2, "🟠": 1}


DAY_MAP_ICAL = {
    "MO": "MO",
    "TU": "TU",
    "WE": "WE",
    "TH": "TH",
    "FR": "FR",
    "SA": "SA",
    "SU": "SU",
}


def generate_ical(courses, semester_start, school_name="正德职业技术学院", sync_time=None):
    """根据课表数据生成 iCal 日历

    Args:
        courses: list of dict, 课表数据
        semester_start: datetime, 学期第一周周一日期
        school_name: str, 学校名称
        sync_time: str, 同步时间标记（如 "06:00"），显示在每个事件描述末尾

    Returns:
        bytes: .ics 文件内容
    """
    cal = Calendar()
    cal.add("prodid", f"-//Course Schedule//{school_name}//CN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", f"课表 - {school_name}")
    cal.add("x-wr-caldesc", f"{school_name} 课程表（自动更新）")
    cal.add("x-wr-timezone", "Asia/Shanghai")
    cal.add("x-published-ttl", "PT12H")

    # 时区组件
    cal.add_component(_build_timezone())

    now = datetime.now()

    for course in courses:
        events = _course_to_events(course, semester_start, sync_time=sync_time)
        for evt in events:
            cal.add_component(evt)

    return cal.to_ical()


def _build_timezone():
    """构建 Asia/Shanghai 时区组件"""
    from icalendar import Timezone, TimezoneStandard, TimezoneDaylight

    tz = Timezone()
    tz.add("tzid", "Asia/Shanghai")
    tz.add("x-lic-location", "Asia/Shanghai")

    std = TimezoneStandard()
    std.add("dtstart", datetime(1970, 1, 1, 0, 0, 0))
    std.add("tzoffsetfrom", timedelta(hours=8))
    std.add("tzoffsetto", timedelta(hours=8))
    std.add("tzname", "CST")
    tz.add_component(std)

    return tz


def _course_to_events(course, semester_start, sync_time=None):
    """将一门课程的排课条目转换为 iCal Event 列表

    Args:
        course: 单条排课记录
        semester_start: 学期第一周周一日期
        sync_time: 同步时间标记（如 "06:00"），会作为一行附加到描述末尾
    """
    events = []
    day_code = course.get("day", "MO")
    weeks = course.get("weeks", [])
    periods = course.get("periods", (1, 2))
    name = course.get("name", "未知课程")
    teacher = course.get("teacher", "")
    location = course.get("location", "")
    course_id = course.get("course_id", "")
    category = course.get("category", "")
    credits = course.get("credits", "")
    course_type = course.get("course_type", "")
    # 调课信息按周挂载：{周次: [(文案, 彩圈), ...]}，只有受影响的周才有内容
    adjust_by_week = course.get("adjust_by_week") or {}

    # 如果 semester_start 是 date 而不是 datetime，转为 datetime
    if not isinstance(semester_start, datetime):
        from datetime import time
        semester_start = datetime.combine(semester_start, time.min)

    # 计算起始时间
    start_hhmm, end_hhmm = _get_period_time_range(periods)
    start_h, start_m = map(int, start_hhmm.split(":"))
    end_h, end_m = map(int, end_hhmm.split(":"))

    # 星期偏移（0=周一, 1=周二, ...）
    day_offset = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
    offset = day_offset.get(day_code, 0)

    for week_num in weeks:
        # 该周对应日期的偏移: (week_num - 1) * 7 + day_offset
        day_delta = timedelta(days=(week_num - 1) * 7 + offset)
        event_date = semester_start + day_delta

        dtstart = event_date.replace(hour=start_h, minute=start_m, second=0)
        dtend = event_date.replace(hour=end_h, minute=end_m, second=0)

        # 本周的调课信息（多数周为空；只有局部调整的那几周才有）
        week_adjs = adjust_by_week.get(week_num) or []
        if week_adjs:
            week_texts = [t for t, _ in week_adjs]
            week_marker = max(
                (mk for _, mk in week_adjs),
                key=lambda m: ADJUST_MARKER_PRIORITY.get(m, 0),
            )
        else:
            week_texts, week_marker = [], ""

        event = Event()
        # 调课标记：课程名后仅跟一个彩圈，视觉轻量（详情见描述最后一行）
        title_suffix = f" {week_marker}" if week_texts else ""
        event.add("summary", f"{name}{title_suffix}")

        event.add("dtstart", dtstart)
        event.add("dtend", dtend)

        # 地点
        if location:
            event.add("location", vText(location))

        # 描述
        desc_parts = [f"课程: {name}"]
        if teacher:
            desc_parts.append(f"教师: {teacher}")
        if location:
            desc_parts.append(f"教室: {location}")
        if category:
            cat_text = category
            if credits:
                cat_text += f" ({credits}学分)"
            if course_type:
                cat_text += f" [{course_type}]"
            desc_parts.append(f"类别: {cat_text}")
        desc_parts.append(f"时间: 第{week_num}周 第{periods[0]}-{periods[1]}节")

        # 末尾加一行同步时间标记（默认全角括号、浅色不易察觉）
        if sync_time:
            desc_parts.append(f"（{sync_time} 同步）")

        # 调课详情放描述最后一行（仅本周受调课影响时才加）
        if week_texts:
            desc_parts.append(f"{week_marker} {' / '.join(week_texts)}")

        event.add("description", "\n".join(desc_parts))

        # 透明（不占时间，日历中不会显示为忙碌）
        event.add("transp", "TRANSPARENT")

        # 课程分类
        if category:
            event.add("categories", vText(category))

        # UID（保证唯一，便于日历更新识别）
        uid_str = f"{course_id}|{name}|{week_num}|{day_code}|{periods[0]}-{periods[1]}"
        uid_hash = hashlib.md5(uid_str.encode()).hexdigest()
        event.add("uid", f"{uid_hash}@course-calendar")

        # 提醒（课前15分钟提醒）
        from icalendar import Alarm
        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add("description", f"即将上课: {name} (@{location})" if location else f"即将上课: {name}")
        alarm.add("trigger", timedelta(minutes=-15))
        event.add_component(alarm)

        events.append(event)

    return events


def _get_period_time_range(periods):
    """获取节次的时间范围

    Args:
        periods: (start, end) 如 (1, 2)

    Returns:
        (start_time, end_time): ("08:00", "09:40")
    """
    start, end = periods
    start_time = PERIOD_TIMES.get(start, ("08:00", "08:00"))[0]
    end_time = PERIOD_TIMES.get(end, ("08:00", "08:00"))[1]
    return start_time, end_time


def update_calendar(courses, semester_start, output_path="calendar.ics"):
    """生成并保存 .ics 文件"""
    ical_data = generate_ical(courses, semester_start)
    with open(output_path, "wb") as f:
        f.write(ical_data)
    return output_path


# ====== 测试 ======
if __name__ == "__main__":
    # 用模拟数据测试
    from datetime import date

    test_courses = [
        {
            "name": "高等数学A(一)",
            "teacher": "李教授",
            "location": "教1-201",
            "day": "MO",
            "weeks": list(range(1, 19)),
            "periods": (1, 2),
            "course_id": "MATH101",
            "class_name": "计算机2401",
        },
        {
            "name": "大学物理B",
            "teacher": "王老师",
            "location": "实验楼302",
            "day": "WE",
            "weeks": list(range(1, 19)),
            "periods": (3, 4),
            "course_id": "PHY201",
            "class_name": "计算机2401",
        },
        {
            "name": "程序设计基础",
            "teacher": "陈老师",
            "location": "机房A-305",
            "day": "FR",
            "weeks": list(range(1, 17)),
            "periods": (5, 6),
            "course_id": "CS101",
            "class_name": "计算机2401",
        },
    ]

    start = date(2026, 2, 23)  # 第二学期周一
    path = update_calendar(test_courses, start)
    print(f"Generated: {path}")
