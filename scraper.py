"""
正德职业技术学院 正方教务系统 课表爬虫
教务系统地址: https://jwxt.zdxy.cn
"""

import json
import re
import time
from datetime import datetime

import requests
from zf_rsa import encrypt_password


class JwxtScraper:
    """正方教务系统 V5 爬虫"""

    BASE_URL = "https://jwxt.zdxy.cn"
    LOGIN_URL = f"{BASE_URL}/jwglxt/xtgl/login_slogin.html"
    PUBLIC_KEY_URL = f"{BASE_URL}/jwglxt/xtgl/login_getPublicKey.html"
    # 个人课表查询 (gnmkdm=N253508)
    SCHEDULE_INDEX_URL = f"{BASE_URL}/jwglxt/kbcx/xskbcx_cxXskbcxIndex.html?gnmkdm=N253508&layout=default"
    SCHEDULE_URL = f"{BASE_URL}/jwglxt/kbcx/xskbcx_cxXsgrkb.html"
    # 教学班调课详情页（服务端会把调课记录渲染进 modelList）
    ADJUST_DETAIL_URL = f"{BASE_URL}/jwglxt/kbdy/xskbdy_cxJxbtkjlView.html"

    # 中文星期 -> iCal 星期码
    CN_DAY_MAP = {"一": "MO", "二": "TU", "三": "WE", "四": "TH",
                  "五": "FR", "六": "SA", "日": "SU", "天": "SU"}

    def __init__(self, username, password, base_url=None):
        self.username = username
        self.password = password
        # 允许按学校覆盖教务系统根地址（默认值是示例，换学校时必须改）
        if base_url:
            self.BASE_URL = base_url.rstrip("/")
        self.LOGIN_URL = f"{self.BASE_URL}/jwglxt/xtgl/login_slogin.html"
        self.PUBLIC_KEY_URL = f"{self.BASE_URL}/jwglxt/xtgl/login_getPublicKey.html"
        self.SCHEDULE_INDEX_URL = (
            f"{self.BASE_URL}/jwglxt/kbcx/xskbcx_cxXskbcxIndex.html"
            f"?gnmkdm=N253508&layout=default"
        )
        self.SCHEDULE_URL = f"{self.BASE_URL}/jwglxt/kbcx/xskbcx_cxXsgrkb.html"
        self.ADJUST_DETAIL_URL = f"{self.BASE_URL}/jwglxt/kbdy/xskbdy_cxJxbtkjlView.html"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/jwglxt/xtgl/login_slogin.html",
        })
        self.logged_in = False

    def _get_csrftoken_and_cookies(self):
        """从登录页获取 CSRF token 和初始 cookies"""
        resp = self.session.get(self.LOGIN_URL, timeout=15)
        resp.encoding = 'utf-8'
        html = resp.text

        # 提取 csrftoken
        match = re.search(r'name="csrftoken"\s+value="([^"]+)"', html)
        csrftoken = match.group(1) if match else ""

        # 提取公钥（备用）
        pub_match = re.search(r'var\s+loginPublicKey\s*=\s*"([^"]*)"', html)
        if pub_match:
            # 公钥有时也在页面中
            pass

        return csrftoken

    def _get_public_key(self):
        """获取 RSA 公钥"""
        resp = self.session.get(
            self.PUBLIC_KEY_URL,
            headers={"Referer": self.LOGIN_URL},
            timeout=15
        )
        data = resp.json()
        return {
            "modulus": data["modulus"],
            "exponent": data["exponent"],
        }

    def _rsa_encrypt(self, plaintext, public_key):
        """RSA 加密密码（使用与教务系统前端完全一致的 zf_rsa 算法）"""
        return encrypt_password(plaintext, public_key["modulus"], public_key["exponent"])

    def login(self):
        """登录教务系统"""
        try:
            # 1. 获取 CSRF token
            csrftoken = self._get_csrftoken_and_cookies()
            if not csrftoken:
                raise Exception("无法获取 CSRF token")

            # 2. 获取 RSA 公钥
            pub_key = self._get_public_key()

            # 3. 加密密码
            encrypted_pw = self._rsa_encrypt(self.password, pub_key)
            csrf_encrypted = self._rsa_encrypt(csrftoken, pub_key)

            # 4. 构造登录请求
            login_data = {
                "csrftoken": csrftoken,
                "yhm": self.username,
                "mm": encrypted_pw,
                "language": "zh_CN",
                "_": str(int(time.time() * 1000)),
            }

            # 5. 提交登录
            t = int(time.time() * 1000)
            resp = self.session.post(
                self.LOGIN_URL + f"?time={t}",
                data=login_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "text/html, application/xhtml+xml, */*",
                    "Referer": self.LOGIN_URL,
                },
                timeout=15,
            )

            # 正方V5登录成功返回的是HTML页面（非JSON），检查是否包含用户信息
            if self.username in resp.text:
                self.logged_in = True
                return True, "登录成功"

            # 检查是否有错误提示
            tips_match = re.search(r'id="tips"[^>]*>([^<]*)', resp.text)
            if tips_match and tips_match.group(1).strip():
                msg = tips_match.group(1).strip()
                return False, msg

            # 尝试解析JSON响应（某些版本的教务系统返回JSON）
            try:
                result = resp.json()
                if result.get("status") == "1" or result.get("result") == "success":
                    self.logged_in = True
                    return True, "登录成功"
                else:
                    msg = result.get("msg", result.get("message", "登录失败"))
                    return False, msg
            except:
                pass

            return False, "登录失败：未知错误"

        except requests.RequestException as e:
            return False, f"网络请求失败: {e}"
        except Exception as e:
            return False, f"登录异常: {e}"

    def _get_current_semester(self):
        """获取当前学年学期信息"""
        now = datetime.now()
        year = now.year
        month = now.month

        # 第一学期：9月 - 次年1月
        # 第二学期：2月 - 7月
        if month >= 9:
            xnm = year  # 学年
            xqm = "3"   # 第一学期
        elif month >= 2:
            xnm = year - 1
            xqm = "12"  # 第二学期
        else:
            xnm = year - 1
            xqm = "3"

        return str(xnm), xqm

    DAY_MAP = {1: "MO", 2: "TU", 3: "WE", 4: "TH", 5: "FR", 6: "SA", 7: "SU"}

    def fetch_schedule(self, xnm=None, xqm=None):
        """获取个人课表数据（从 kbList 解析详细排课）

        Args:
            xnm: 学年，如 "2025" 表示 2025-2026 学年
            xqm: 学期，"3"=第一学期, "12"=第二学期

        Returns:
            list: 排课条目列表，每项包含课程名、教师、教室、星期、节次、周次等
        """
        if not self.logged_in:
            ok, msg = self.login()
            if not ok:
                raise Exception(f"登录失败: {msg}")

        if xnm is None:
            xnm, xqm = self._get_current_semester()

        # 先访问个人课表页面获取session上下文
        self.session.get(self.SCHEDULE_INDEX_URL, timeout=15)

        # 个人课表查询参数
        t = int(time.time() * 1000)
        params = {
            "xnm": xnm,
            "xqm": xqm,
            "gnmkdm": "N253508",
            "_search": "false",
            "nd": str(t),
            "queryModel.showCount": "200",
            "queryModel.currentPage": "1",
            "queryModel.sortName": "",
            "queryModel.sortOrder": "asc",
            "time": str(t),
        }

        resp = self.session.post(
            self.SCHEDULE_URL,
            data=params,
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.SCHEDULE_INDEX_URL,
            },
            timeout=15,
        )
        data = resp.json()

        # kbList 包含每个排课时段的详细信息
        kb_list = data.get("kbList", [])
        if not kb_list:
            return []

        courses = self._parse_kb_list(kb_list)
        self._attach_adjust_details(courses)
        return courses

    def _fetch_adjust_records(self, jxb_id):
        """拉取某教学班的调课记录（原/现 教室、教师、星期、节次、原因）

        Returns:
            list[dict]: modelList 解析结果，失败返回 []
        """
        try:
            resp = self.session.get(
                self.ADJUST_DETAIL_URL,
                params={"gnmkdm": "N253508", "jxb_id": jxb_id},
                headers={"Referer": self.SCHEDULE_INDEX_URL},
                timeout=15,
            )
            m = re.search(r'modelList\s*=\s*eval\((\[.*?\])\s*\)', resp.text, re.S)
            if not m:
                return []
            return json.loads(m.group(1))
        except Exception:
            return []

    # 按「变化类型」配色：换教室最影响上课，其次调时间，最后换教师
    MARKER_LOCATION = "🔴"   # 换教室
    MARKER_TIME = "🔵"       # 调时间 / 调周次
    MARKER_TEACHER = "🟠"    # 换教师
    MARKER_DEFAULT = "🔴"    # 未识别的调整
    MARKER_PRIORITY = {"🔴": 3, "🔵": 2, "🟠": 1}

    # 调课覆盖该排课组「过半周次」即视为长期/既定变更（如整学期换教师、
    # 从第 2 周起换教室），不再逐周标记——课表本身已是最新状态。
    # 只有影响少数周的临时调整（如仅第 1 周换教师）才逐周标记。
    ADJUST_WHOLE_RATIO = 0.5

    @staticmethod
    def _build_adjust_text(rec):
        """把一条调课记录转成 (文案, 标记颜色)，只列发生变化的项

        例：('调整教室 2306→2406（教室音响不响）', '🔴')
        """
        parts = []
        kinds = set()

        def _s(key):
            return (rec.get(key) or "").strip()

        # 教室
        if _s("ycdmc") != _s("xcdmc"):
            parts.append(f"调整教室 {_s('ycdmc') or '?'}→{_s('xcdmc') or '?'}")
            kinds.add("loc")
        # 教师
        if _s("yjsxm") != _s("xjsxm"):
            parts.append(f"更换教师 {_s('yjsxm') or '?'}→{_s('xjsxm') or '?'}")
            kinds.add("teacher")
        # 时间（星期 + 节次）
        y_time = f"{_s('yxqj')} {_s('yjc')}".strip()
        x_time = f"{_s('xxqj')} {_s('xjc')}".strip()
        if y_time != x_time:
            parts.append(f"调整时间 {y_time}→{x_time}")
            kinds.add("time")
        # 周次
        if _s("yzcd") != _s("xzcd"):
            parts.append(f"调整周次 {_s('yzcd')}→{_s('xzcd')}")
            kinds.add("time")

        text = "；".join(parts) if parts else "有调课调整"
        reason = _s("tkyy")
        if reason:
            text += f"（{reason}）"

        if "loc" in kinds:
            marker = JwxtScraper.MARKER_LOCATION
        elif "time" in kinds:
            marker = JwxtScraper.MARKER_TIME
        elif "teacher" in kinds:
            marker = JwxtScraper.MARKER_TEACHER
        else:
            marker = JwxtScraper.MARKER_DEFAULT
        return text, marker

    def _attach_adjust_details(self, courses):
        """按「周次范围」精确分发调课详情，只挂到真正受影响的那几周

        判定规则（对齐用户诉求）：
        1. 调课若覆盖该 (教学班, 星期, 节次) 组的**全部周次** → 属于既定变更，
           课表本身已是最新状态，**不标记**（如体育Ⅲ 整学期换教师）
        2. 调课只影响**部分周次** → 临时调整，**精确标记到受影响的周**
           （如毛概仅第 1 周因教师节座谈会换教师，就只标第 1 周）

        结果写入 course["adjust_by_week"] = {周次: [(文案, 颜色), ...]}
        """
        # 1) 拉取每个教学班的调课记录（同一 jxb_id 只请求一次）
        cache = {}
        for c in courses:
            if not c.get("is_adjusted"):
                continue
            jid = c.get("jxb_id") or c.get("course_id")
            if not jid:
                continue
            if jid not in cache:
                cache[jid] = self._fetch_adjust_records(jid)

        # 2) 按 (jxb_id, 星期, 节次) 汇总该组覆盖的全部周次
        groups = {}
        for c in courses:
            jid = c.get("jxb_id") or c.get("course_id")
            if not jid:
                continue
            key = (jid, c.get("day"), tuple(c.get("periods", ())))
            groups.setdefault(key, set()).update(c.get("weeks", []))

        # 3) 逐条匹配：只保留「局部调整」，并精确到周
        for c in courses:
            c["adjust_by_week"] = {}
            c["adjust_text"] = ""
            c["adjust_marker"] = ""
            if not c.get("is_adjusted"):
                continue
            jid = c.get("jxb_id") or c.get("course_id")
            if not jid:
                continue

            my_periods = tuple(c.get("periods", ()))
            all_weeks = groups.get((jid, c.get("day"), my_periods), set())

            for rec in cache.get(jid, []):
                # 位置匹配：调课后的「星期 + 节次」要跟本条排课一致
                rec_day = self.CN_DAY_MAP.get((rec.get("xxqj") or "").strip())
                rec_periods = self._parse_periods(
                    str(rec.get("xjc", "")).replace("第", "").replace("节", "")
                )
                if rec_day != c.get("day") or rec_periods != my_periods:
                    continue

                # 该调课记录影响的周次：优先「现周次」，缺失时退回「原周次」
                rec_weeks = set(self._parse_weeks(
                    (rec.get("xzcd") or "").strip() or (rec.get("yzcd") or "").strip()
                ))
                if not rec_weeks:
                    continue  # 周次缺失，宁可不标，也不污染整个学期

                # 覆盖该组过半周次 → 长期/既定变更，不逐周标记
                if all_weeks:
                    covered = len(rec_weeks & all_weeks)
                    if covered >= len(all_weeks) * self.ADJUST_WHOLE_RATIO:
                        continue

                hit = set(c.get("weeks", [])) & rec_weeks
                if not hit:
                    continue

                text, marker = self._build_adjust_text(rec)
                for w in hit:
                    c["adjust_by_week"].setdefault(w, []).append((text, marker))

            # 汇总字段（供自检 / 调试查看）
            if c["adjust_by_week"]:
                texts, markers = [], []
                for w in sorted(c["adjust_by_week"]):
                    for t, mk in c["adjust_by_week"][w]:
                        texts.append(t)
                        markers.append(mk)
                c["adjust_text"] = " / ".join(dict.fromkeys(texts))
                c["adjust_marker"] = max(
                    markers, key=lambda m: self.MARKER_PRIORITY.get(m, 0)
                )

    def _parse_kb_list(self, kb_list):
        """解析 kbList 为标准的排课条目格式"""
        courses = []

        for item in kb_list:
            if not isinstance(item, dict):
                continue

            course_name = item.get("kcmc", "").strip()
            teacher = item.get("xm", "").strip()
            location = item.get("cdmc", "").strip() or "待定"
            building = item.get("lh", "").strip()
            full_location = f"{building}{location}" if building else location

            # 星期几: xqj is 1-7 (可能是字符串)
            xqj = int(item.get("xqj", 0))
            day_code = self.DAY_MAP.get(xqj, "MO")

            # 节次: "1-2", "1-2节", "3-4节", "5-6节", "5-8节" 等
            jcs = item.get("jcs", "").strip().replace("节", "")
            periods = self._parse_periods(jcs)

            # 周次: "1-5周,8-9周,11-14周,17周"
            zcd = item.get("zcd", "").strip()
            weeks = self._parse_weeks(zcd)

            # 其他信息
            category = item.get("kclb", "").strip()
            credits = item.get("xf", "")
            xslxbj = item.get("xslxbj", "").strip()
            jxb_id = item.get("jxb_id", "")

            # 教学类型符号: ★=理论, ☆=实验, ■=实训, ◆=上机, @=线上
            type_map = {"★": "理论", "☆": "实验", "■": "实训", "◆": "上机", "@": "线上"}
            course_type = type_map.get(xslxbj, "")

            # 调课检测
            is_adjusted = item.get("jxbsftkbj", "0") == "1"
            oldjc = item.get("oldjc", "")
            oldzc = item.get("oldzc", "")

            if not course_name:
                continue

            # 调课信息
            adjusted_info = {}
            if is_adjusted:
                adjusted_info = {
                    "is_adjusted": True,
                    "oldjc": oldjc,
                    "oldzc": oldzc,
                }

            # 构建唯一ID
            uid_parts = [course_name, teacher, day_code, jcs, zcd]
            uid = "|".join(uid_parts)

            courses.append({
                "name": course_name,
                "teacher": teacher or "未知教师",
                "location": full_location,
                "day": day_code,
                "weeks": weeks,
                "periods": periods,
                "course_id": jxb_id or course_name,
                "category": category,
                "credits": credits,
                "course_type": course_type,
                "uid": uid,
                "jxb_id": jxb_id,
                "is_adjusted": is_adjusted,
                "adjusted_info": adjusted_info,
                "adjust_text": "",
                "adjust_marker": "",
            })

        return courses

    @staticmethod
    def _parse_weeks(weeks_str):
        """解析周次字符串为周次列表

        Args:
            weeks_str: "1-18周" / "第7周" / "1-5周,8-9周" 等

        Returns:
            list: [1, 2, 3, ...]，空字符串返回空列表（不默认全周）
        """
        if not weeks_str:
            return []

        # 移除标注（单）、（双）等
        weeks_str = re.sub(r'[（(][^)）]*[)）]', '', weeks_str)

        weeks = []
        for part in weeks_str.split(','):
            # 用正则抽取所有数字，免去"周/第"等中文字符造成 int() 失败
            numbers = re.findall(r'\d+', part)
            if not numbers:
                continue
            if len(numbers) >= 2:
                start, end = int(numbers[0]), int(numbers[-1])
                if end >= start:
                    weeks.extend(range(start, end + 1))
            else:
                weeks.append(int(numbers[0]))

        return sorted(set(weeks)) if weeks else []

    @staticmethod
    def _parse_periods(periods_str):
        """解析节次字符串

        Args:
            periods_str: "1-2" 或 "3-4" 等

        Returns:
            tuple: (start_period, end_period) 如 (1, 2)
        """
        if not periods_str:
            return (1, 2)

        if "-" in periods_str:
            try:
                parts = periods_str.split("-")
                return (int(parts[0]), int(parts[1]))
            except (ValueError, TypeError):
                pass

        try:
            p = int(periods_str)
            return (p, p)
        except (ValueError, TypeError):
            return (1, 2)

    def test_connection(self):
        """测试连接是否正常"""
        try:
            resp = self.session.get(self.LOGIN_URL, timeout=10)
            return resp.status_code == 200, "连接正常" if resp.status_code == 200 else f"返回 {resp.status_code}"
        except requests.RequestException as e:
            return False, f"连接失败: {e}"
