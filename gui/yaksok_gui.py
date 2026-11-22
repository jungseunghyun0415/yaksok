"""약속 데스크톱 화면 (CustomTkinter). PyCharm에서 이 파일을 Run하면 창이 열린다.

메인 창  : 왼쪽 = 이름 · 바로가기 · 내 약 일정 / 가운데 = 달력 · 선택한 날 / 오른쪽 = 복약 일정 설정
약 검색  : 제품명·성분으로 검색, AI 쉬운 설명
사진 창  : 카메라 또는 사진 파일 → AI가 이름 읽기 → 맞는지 확인 → 약 정보
"""
import calendar
import mimetypes
import queue
import re
import sys
import tempfile
import threading
import os
import tkinter.font as tkfont
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ai_analyzer import generate_medicine_guide  # noqa: E402
from drug_db import clean_name, info_text, search, search_any  # noqa: E402
from schedule_store import in_period, load_schedule, save_schedule, storage_mode  # noqa: E402
import main as reminder  # noqa: E402  알림 로직(src/main.py)을 화면에서도 그대로 쓴다
import settings_store  # noqa: E402

ctk.set_appearance_mode("light")

# 색: 중간 발표 자료와 같은 청록 계열
PRIMARY, DARK, ACCENT = "#028090", "#0B4F5C", "#F2705E"
BG, CARD, BORDER = "#F3F6F7", "#FFFFFF", "#DDE6E8"
TEXT, MUTED = "#1B2B30", "#6B8F97"
TINT, TINT_HOVER = "#D6EFEB", "#BFE5DF"
CELL, CELL_HOVER = "#F2F5F6", "#E3EAEC"

NO_DUR = "(조회된 병용 주의 데이터가 없습니다)"
WEEK = ["일", "월", "화", "수", "목", "금", "토"]
DEFAULT_TIMES = {1: ["09:00"], 2: ["09:00", "21:00"], 3: ["08:00", "13:00", "19:00"],
                 4: ["08:00", "12:00", "17:00", "21:00"], 5: ["07:00", "10:00", "13:00", "16:00", "19:00"],
                 6: ["07:00", "10:00", "13:00", "16:00", "19:00", "22:00"]}
FAMILY = "TkDefaultFont"


# ---------------------------------------------------------------- 작은 도구들
def pick_family(root) -> str:
    fams = set(tkfont.families(root))
    for f in ("Malgun Gothic", "Apple SD Gothic Neo", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR"):
        if f in fams:
            return f
    return "TkDefaultFont"


def font(size=13, bold=False):
    return ctk.CTkFont(family=FAMILY, size=size, weight="bold" if bold else "normal")


def card(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER, **kw)


def label(parent, text="", size=13, bold=False, color=TEXT, **kw):
    return ctk.CTkLabel(parent, text=text, font=font(size, bold), text_color=color, **kw)


def entry(parent, placeholder="", **kw):
    return ctk.CTkEntry(parent, placeholder_text=placeholder, fg_color="white", border_color=BORDER,
                        text_color=TEXT, height=34, corner_radius=8, font=font(13), **kw)


STYLES = {
    "primary": dict(fg_color=PRIMARY, hover_color=DARK, text_color="white"),
    "ghost": dict(fg_color="transparent", hover_color=TINT, text_color=PRIMARY, border_width=1, border_color=PRIMARY),
    "danger": dict(fg_color="transparent", hover_color="#FDE7E3", text_color=ACCENT, border_width=1, border_color=ACCENT),
    "plain": dict(fg_color=CELL, hover_color=CELL_HOVER, text_color=TEXT),
}


def button(parent, text, command, kind="primary", **kw):
    kw.setdefault("height", 34)
    return ctk.CTkButton(parent, text=text, command=command, corner_radius=8, font=font(13, kind == "primary"),
                         **STYLES[kind], **kw)


def textbox(parent, **kw):
    return ctk.CTkTextbox(parent, fg_color="#FAFCFC", border_width=1, border_color=BORDER, text_color=TEXT,
                          corner_radius=10, font=font(13), wrap="word", **kw)


def set_text(box, text: str):
    box.configure(state="normal")
    box.delete("1.0", "end")
    box.insert("end", text)
    box.configure(state="disabled")


def short_name(row: dict) -> str:
    return clean_name(row["제품명"])[:60]


def make_guide(row: dict) -> str:
    """약 데이터의 사실만 AI에게 넘겨 쉬운 안내문을 만든다."""
    return generate_medicine_guide(short_name(row), info_text(row), NO_DUR)


def bring_front(win):
    win.lift()
    win.attributes("-topmost", True)
    win.after(250, lambda: win.attributes("-topmost", False))
    win.focus_force()


def capture_from_camera() -> str | None:
    """카메라 미리보기 창을 띄우고 스페이스바로 촬영한다. 취소하면 None."""
    import cv2  # 카메라를 쓸 때만 필요 (pip install opencv-python)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("카메라를 열 수 없어요.")
    path = str(Path(tempfile.gettempdir()) / "yaksok_capture.jpg")
    result = None
    title = "Space = capture / Esc = cancel"
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            cv2.imshow(title, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == 32:
                cv2.imwrite(path, frame)
                result = path
                break
            if key == 27:
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
    return result


# ---------------------------------------------------------------- 메인 창
class YaksokApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        global FAMILY
        FAMILY = pick_family(self)
        settings_store.apply(settings_store.load())  # 설정 창에서 저장해 둔 키·주소를 환경변수로 옮긴다
        self.load_failed = False
        self.title("약속 · 복약 일정 관리")
        self.geometry("1240x760")
        self.minsize(1120, 700)
        self.configure(fg_color=BG)

        self.today = date.today()
        self.selected = self.today
        self.view = (self.today.year, self.today.month)
        self.data = {"medicines": []}
        self.time_entries: list = []
        self.match_rows: list[dict] = []

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build_header()
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=18, pady=(14, 0))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=30, uniform="col")
        body.grid_columnconfigure(1, weight=36, uniform="col")
        body.grid_columnconfigure(2, weight=34, uniform="col")
        self._build_left(body)
        self._build_middle(body)
        self._build_right(body)
        label(self, "※ 본 서비스의 안내는 의학적 조언이 아니며, 정확한 상담은 약사·의사와 진행하세요.   "
                    "한 사람 기준 시연용이에요. 실제 이름과 복약 정보는 입력하지 마세요.",
              11, color=MUTED).grid(row=2, column=0, pady=8)
        self.reload()
        self.select_day(self.today)

    # ----- 공통
    def run_bg(self, work, done):
        """오래 걸리는 일(AI 호출)을 따로 돌려서 창이 멈추지 않게 한다."""
        q: queue.Queue = queue.Queue()

        def target():
            try:
                q.put(("ok", work()))
            except Exception as e:  # noqa: BLE001
                q.put(("err", e))

        threading.Thread(target=target, daemon=True).start()

        def poll():
            try:
                kind, val = q.get_nowait()
            except queue.Empty:
                self.after(100, poll)
                return
            done(kind, val)

        self.after(100, poll)

    def reload(self):
        try:
            self.data = load_schedule()
            self.load_failed = False
        except Exception as e:  # noqa: BLE001
            # 불러오기에 실패한 채로 저장하면 GitHub의 기존 일정을 덮어쓸 수 있어서 저장을 막는다
            self.load_failed = True
            self.data = {"medicines": []}
            messagebox.showerror("약속", f"일정을 불러오지 못했어요. 설정(GitHub 연동)을 확인해 주세요.\n{e}")
        name = self.data.get("user_name", "")
        if name:
            self.name_entry.delete(0, "end")
            self.name_entry.insert(0, name)
        self.refresh_all()

    def save(self, message: str) -> bool:
        if self.load_failed:
            messagebox.showwarning("약속", "일정을 불러오지 못한 상태라 저장을 막았어요.\n설정에서 GitHub 연동을 확인한 뒤 다시 시도해 주세요.")
            return False
        try:
            save_schedule(self.data, message)
            return True
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("약속", f"저장하지 못했어요.\n{e}")
            return False

    @property
    def meds(self) -> list[dict]:
        return self.data["medicines"]

    # ----- 화면 만들기
    def _build_header(self):
        bar = ctk.CTkFrame(self, fg_color=DARK, corner_radius=0, height=66)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(bar, text="Rx", width=42, height=42, corner_radius=12, fg_color=PRIMARY, text_color="white",
                     font=font(16, True)).grid(row=0, column=0, rowspan=2, padx=(20, 12), pady=12)
        label(bar, "약속", 20, True, "white").grid(row=0, column=1, sticky="sw", pady=(10, 0))
        label(bar, "복용 알림 · AI 병용 주의 안내", 12, color="#A7D8D2").grid(row=1, column=1, sticky="nw")
        self.greet = label(bar, "", 14, True, "white")
        self.greet.grid(row=0, column=2, rowspan=2, sticky="e", padx=16)
        self.status_label = label(bar, "", 12, color="#A7D8D2")
        self.status_label.grid(row=0, column=3, rowspan=2, padx=(0, 12))
        ctk.CTkButton(bar, text="설정", width=64, height=32, corner_radius=8, font=font(13), fg_color="transparent",
                      border_width=1, border_color="#A7D8D2", text_color="white", hover_color=PRIMARY,
                      command=self.open_settings).grid(row=0, column=4, rowspan=2, padx=(0, 20))

    def _build_left(self, body):
        col = ctk.CTkFrame(body, fg_color="transparent")
        col.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        col.grid_rowconfigure(2, weight=1)
        col.grid_columnconfigure(0, weight=1)

        prof = card(col)
        prof.grid(row=0, column=0, sticky="ew")
        prof.grid_columnconfigure(0, weight=1)
        label(prof, "프로필", 14, True).grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 4))
        self.name_entry = entry(prof, "이름 또는 닉네임")
        self.name_entry.grid(row=1, column=0, sticky="ew", padx=(14, 6), pady=(0, 14))
        button(prof, "저장", self.save_name, "plain", width=64).grid(row=1, column=1, padx=(0, 14), pady=(0, 14))

        act = card(col)
        act.grid(row=1, column=0, sticky="ew", pady=10)
        act.grid_columnconfigure(0, weight=1)
        label(act, "약 알아보기", 14, True).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 6))
        button(act, "약 검색하기", self.open_search, height=40).grid(row=1, column=0, sticky="ew", padx=14)
        button(act, "사진으로 알아보기", self.open_photo, "ghost", height=40).grid(row=2, column=0, sticky="ew", padx=14, pady=(8, 14))

        lst = card(col)
        lst.grid(row=2, column=0, sticky="nsew")
        lst.grid_rowconfigure(1, weight=1)
        lst.grid_columnconfigure(0, weight=1)
        label(lst, "내 약 일정", 14, True).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))
        self.list_frame = ctk.CTkScrollableFrame(lst, fg_color="transparent")
        self.list_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 8))

    def _build_middle(self, body):
        col = ctk.CTkFrame(body, fg_color="transparent")
        col.grid(row=0, column=1, sticky="nsew", padx=8)
        col.grid_rowconfigure(1, weight=1)
        col.grid_columnconfigure(0, weight=1)

        cal = card(col)
        cal.grid(row=0, column=0, sticky="ew")
        nav = ctk.CTkFrame(cal, fg_color="transparent")
        nav.pack(fill="x", padx=14, pady=(12, 4))
        nav.grid_columnconfigure(1, weight=1)
        button(nav, "‹", lambda: self.shift_month(-1), "plain", width=34).grid(row=0, column=0)
        self.month_label = label(nav, "", 16, True)
        self.month_label.grid(row=0, column=1)
        button(nav, "›", lambda: self.shift_month(1), "plain", width=34).grid(row=0, column=2)
        button(nav, "오늘", self.go_today, "ghost", width=48).grid(row=0, column=3, padx=(8, 0))

        grid = ctk.CTkFrame(cal, fg_color="transparent")
        grid.pack(fill="x", padx=12, pady=(2, 6))
        for i in range(7):
            grid.grid_columnconfigure(i, weight=1, uniform="d")
            color = ACCENT if i == 0 else (PRIMARY if i == 6 else MUTED)
            label(grid, WEEK[i], 12, True, color).grid(row=0, column=i, pady=(0, 4))
        self.cells = []
        for r in range(6):
            row = []
            for i in range(7):
                b = ctk.CTkButton(grid, text="", height=38, corner_radius=8, font=font(13), border_width=0)
                b.grid(row=r + 1, column=i, padx=2, pady=2, sticky="ew")
                row.append(b)
            self.cells.append(row)
        legend = ctk.CTkFrame(cal, fg_color="transparent")
        legend.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkLabel(legend, text="", width=14, height=14, corner_radius=4, fg_color=TINT).pack(side="left")
        label(legend, "복용일", 11, color=MUTED).pack(side="left", padx=(4, 12))
        ctk.CTkLabel(legend, text="", width=14, height=14, corner_radius=4, fg_color=CARD, border_width=2,
                     border_color=ACCENT).pack(side="left")
        label(legend, "오늘", 11, color=MUTED).pack(side="left", padx=(4, 12))
        ctk.CTkLabel(legend, text="", width=14, height=14, corner_radius=4, fg_color=PRIMARY).pack(side="left")
        label(legend, "선택", 11, color=MUTED).pack(side="left", padx=4)

        day = card(col)
        day.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        day.grid_columnconfigure(0, weight=1)
        day.grid_rowconfigure(1, weight=1)
        self.day_label = label(day, "", 15, True)
        self.day_label.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 2))
        self.day_frame = ctk.CTkScrollableFrame(day, fg_color="transparent")
        self.day_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 8))

    def _build_right(self, body):
        form = card(body)
        form.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=1)
        label(form, "복약 일정 설정", 14, True).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 0))
        label(form, "달력에서 날짜를 누르면 시작일이 정해져요.", 11, color=MUTED).grid(row=1, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 8))

        label(form, "약 이름", 12, True, MUTED).grid(row=2, column=0, columnspan=2, sticky="w", padx=16)
        row = ctk.CTkFrame(form, fg_color="transparent")
        row.grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=(2, 4))
        row.grid_columnconfigure(0, weight=1)
        self.drug_entry = entry(row, "예: 가네카정")
        self.drug_entry.grid(row=0, column=0, sticky="ew")
        self.drug_entry.bind("<Return>", lambda e: self.find_names())
        button(row, "찾기", self.find_names, "plain", width=56).grid(row=0, column=1, padx=(6, 0))
        self.match_box = ctk.CTkComboBox(form, values=["(찾기를 누르면 약 데이터에서 골라요)"], state="readonly", height=34,
                                         corner_radius=8, border_color=BORDER, fg_color="white", button_color=PRIMARY,
                                         button_hover_color=DARK, text_color=TEXT, font=font(12), dropdown_font=font(12),
                                         command=self.pick_match)
        self.match_box.grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))
        self.match_box.set("(찾기를 누르면 약 데이터에서 골라요)")

        label(form, "시작일", 12, True, MUTED).grid(row=5, column=0, sticky="w", padx=(16, 4))
        label(form, "종료일", 12, True, MUTED).grid(row=5, column=1, sticky="w", padx=(4, 16))
        self.start_entry = entry(form, "2026-11-20")
        self.start_entry.grid(row=6, column=0, sticky="ew", padx=(16, 4), pady=(2, 6))
        self.end_entry = entry(form, "2026-11-26")
        self.end_entry.grid(row=6, column=1, sticky="ew", padx=(4, 16), pady=(2, 6))
        self.period_seg = ctk.CTkSegmentedButton(form, values=["3일", "7일", "14일", "30일"], command=self.set_period,
                                                 selected_color=PRIMARY, selected_hover_color=DARK, unselected_color=CELL,
                                                 unselected_hover_color=CELL_HOVER, text_color=TEXT, font=font(12), height=30)
        self.period_seg.grid(row=7, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))
        self.period_seg.set("7일")

        label(form, "하루 복용 횟수", 12, True, MUTED).grid(row=8, column=0, columnspan=2, sticky="w", padx=16)
        self.count_seg = ctk.CTkSegmentedButton(form, values=["1", "2", "3", "4", "5", "6"], command=self.build_times,
                                                selected_color=PRIMARY, selected_hover_color=DARK, unselected_color=CELL,
                                                unselected_hover_color=CELL_HOVER, text_color=TEXT, font=font(12), height=32)
        self.count_seg.grid(row=9, column=0, columnspan=2, sticky="ew", padx=16, pady=(2, 10))
        self.count_seg.set("2")

        label(form, "복용 시간 (24시간 형식)", 12, True, MUTED).grid(row=10, column=0, columnspan=2, sticky="w", padx=16)
        self.times_frame = ctk.CTkFrame(form, fg_color="transparent")
        self.times_frame.grid(row=11, column=0, columnspan=2, sticky="ew", padx=12, pady=(2, 6))
        for i in range(3):
            self.times_frame.grid_columnconfigure(i, weight=1, uniform="t")
        self.build_times("2")

        form.grid_rowconfigure(12, weight=1)
        button(form, "일정 저장", self.save_med, height=42).grid(row=13, column=0, columnspan=2, sticky="sew", padx=16, pady=16)

    # ----- 새로 그리기
    def refresh_all(self):
        name = self.data.get("user_name", "").strip()
        self.greet.configure(text=f"{name}님, 안녕하세요" if name else "")
        self.refresh_status()
        self.draw_list()
        self.draw_calendar()
        self.draw_day()

    def refresh_status(self):
        """알림 채널과 일정 저장 위치가 어떻게 연결돼 있는지 상단에 보여준다."""
        ch = reminder.channels()
        store = "GitHub 연동" if storage_mode() == "GitHub 레포" else "이 컴퓨터에만 저장"
        text = (("알림: " + "·".join(ch)) if ch else "알림 채널 미설정") + f"   |   저장: {store}"
        self.status_label.configure(text=text, text_color="#A7D8D2" if ch else "#FFB4A8")

    def draw_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        if not self.meds:
            label(self.list_frame, "등록된 일정이 없어요.\n가운데 달력에서 날짜를 누르고\n오른쪽에서 설정해 보세요.", 12,
                  color=MUTED, justify="left").pack(anchor="w", padx=8, pady=8)
        for i, m in enumerate(self.meds):
            item = ctk.CTkFrame(self.list_frame, fg_color=CELL, corner_radius=10)
            item.pack(fill="x", pady=4, padx=2)
            item.grid_columnconfigure(0, weight=1)
            period = f"{m['start_date']} ~ {m['end_date']}" if m.get("start_date") else "기간 제한 없음"
            label(item, m["name"], 13, True, anchor="w", justify="left", wraplength=160).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))
            label(item, f"하루 {len(m['times'])}회 · {' '.join(m['times'])}", 12, color=MUTED, anchor="w", wraplength=190, justify="left").grid(row=1, column=0, sticky="w", padx=12)
            label(item, period, 12, color=MUTED, anchor="w").grid(row=2, column=0, sticky="w", padx=12, pady=(0, 10))
            acts = ctk.CTkFrame(item, fg_color="transparent")
            acts.grid(row=0, column=1, rowspan=3, padx=8)
            button(acts, "알림 테스트", lambda i=i: self.test_notify(i), "ghost", width=76, height=28).pack(pady=(0, 4))
            button(acts, "삭제", lambda i=i: self.delete_med(i), "danger", width=76, height=28).pack()

    def draw_calendar(self):
        y, m = self.view
        self.month_label.configure(text=f"{y}년 {m}월")
        weeks = calendar.Calendar(firstweekday=6).monthdayscalendar(y, m)
        for r in range(6):
            for i in range(7):
                b = self.cells[r][i]
                if r >= len(weeks):  # 그 달에 없는 주(5주짜리 달의 마지막 줄)는 자리를 비운다
                    b.grid_remove()
                    continue
                b.grid()
                day = weeks[r][i]
                if not day:
                    b.configure(text="", state="disabled", fg_color="transparent", border_width=0, hover=False)
                    continue
                d = date(y, m, day)
                if d == self.selected:
                    colors = dict(fg_color=PRIMARY, hover_color=DARK, text_color="white")
                elif any(in_period(x, d) for x in self.meds):
                    colors = dict(fg_color=TINT, hover_color=TINT_HOVER, text_color=DARK)
                else:
                    colors = dict(fg_color=CELL, hover_color=CELL_HOVER, text_color=TEXT)
                b.configure(text=str(day), state="normal", hover=True, command=lambda d=d: self.select_day(d),
                            border_width=2 if d == self.today else 0, border_color=ACCENT, **colors)

    def draw_day(self):
        d = self.selected
        self.day_label.configure(text=f"{d.month}월 {d.day}일 ({WEEK[(d.weekday() + 1) % 7]}) 복용 일정")
        for w in self.day_frame.winfo_children():
            w.destroy()
        todays = [x for x in self.meds if in_period(x, d)]
        if not todays:
            label(self.day_frame, "이 날 복용할 약이 없어요.", 12, color=MUTED).pack(anchor="w", padx=8, pady=6)
        for x in todays:
            row = ctk.CTkFrame(self.day_frame, fg_color=CELL, corner_radius=10)
            row.pack(fill="x", pady=3, padx=2)
            label(row, x["name"], 13, True, anchor="w").pack(anchor="w", padx=12, pady=(8, 0))
            chips = ctk.CTkFrame(row, fg_color="transparent")
            chips.pack(anchor="w", padx=10, pady=(2, 8))
            for t in x["times"]:
                ctk.CTkLabel(chips, text=t, font=font(12, True), text_color=DARK, fg_color=TINT, corner_radius=8,
                             width=52, height=24).pack(side="left", padx=2)

    def build_times(self, value=None):
        try:
            n = int(value or self.count_seg.get())
        except ValueError:
            n = 2
        for w in self.times_frame.winfo_children():
            w.destroy()
        self.time_entries = []
        for i, t in enumerate(DEFAULT_TIMES[n]):
            cell = ctk.CTkFrame(self.times_frame, fg_color="transparent")
            cell.grid(row=i // 3, column=i % 3, padx=4, pady=3, sticky="ew")
            label(cell, f"{i + 1}회차", 11, color=MUTED).pack(anchor="w")
            e = entry(cell, "09:00")
            e.insert(0, t)
            e.pack(fill="x")
            self.time_entries.append(e)

    # ----- 동작
    def select_day(self, d: date):
        self.selected = d
        self.view = (d.year, d.month)
        self.start_entry.delete(0, "end")
        self.start_entry.insert(0, d.isoformat())
        self.set_period(self.period_seg.get() or "7일")
        self.draw_calendar()
        self.draw_day()

    def set_period(self, value: str):
        n = int(value.replace("일", ""))
        try:
            start = date.fromisoformat(self.start_entry.get().strip())
        except ValueError:
            start = self.selected
        self.end_entry.delete(0, "end")
        self.end_entry.insert(0, (start + timedelta(days=n - 1)).isoformat())

    def shift_month(self, delta: int):
        y, m = self.view
        m += delta
        if m < 1:
            y, m = y - 1, 12
        elif m > 12:
            y, m = y + 1, 1
        self.view = (y, m)
        self.draw_calendar()

    def go_today(self):
        self.select_day(self.today)

    def save_name(self):
        self.data["user_name"] = self.name_entry.get().strip()
        if self.save("이름 저장"):
            self.refresh_all()

    def find_names(self):
        q = self.drug_entry.get()
        self.match_rows = search(q, 8) if q.strip() else []
        if self.match_rows:
            self.match_box.configure(values=[short_name(r) for r in self.match_rows])
            self.match_box.set("약 데이터에서 찾았어요. 골라 주세요")
        else:
            self.match_box.configure(values=["(없음)"])
            self.match_box.set("찾은 약이 없어요. 이름을 그대로 저장할 수 있어요")

    def pick_match(self, value: str):
        for r in self.match_rows:
            if short_name(r) == value:
                self.drug_entry.delete(0, "end")
                self.drug_entry.insert(0, value)
                return

    def save_med(self):
        name = self.drug_entry.get().strip()
        if not name:
            return messagebox.showwarning("약속", "약 이름을 입력해 주세요.")
        try:
            start = date.fromisoformat(self.start_entry.get().strip())
            end = date.fromisoformat(self.end_entry.get().strip())
        except ValueError:
            return messagebox.showwarning("약속", "날짜는 2026-11-20 형식으로 입력해 주세요.")
        if end < start:
            return messagebox.showwarning("약속", "종료일은 시작일보다 같거나 늦어야 해요.")
        times = [e.get().strip() for e in self.time_entries]
        for t in times:
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
                return messagebox.showwarning("약속", f"시간은 09:00처럼 입력해 주세요. ({t})")
        if len(set(times)) != len(times):
            return messagebox.showwarning("약속", "복용 시간이 겹쳐요. 서로 다른 시간으로 정해 주세요.")
        self.meds.append({"name": name, "times": sorted(times), "start_date": start.isoformat(), "end_date": end.isoformat()})
        if self.save(f"일정 추가: {name}"):
            self.drug_entry.delete(0, "end")
            self.match_box.configure(values=["(찾기를 누르면 약 데이터에서 골라요)"])
            self.match_box.set("(찾기를 누르면 약 데이터에서 골라요)")
            self.refresh_all()
            where = ("GitHub에도 저장했어요. 알림(Actions)에 반영돼요." if storage_mode() == "GitHub 레포"
                     else "이 컴퓨터에만 저장됐어요. 알림(Actions)에 반영하려면 설정에서 GitHub 연동을 켜세요.")
            messagebox.showinfo("약속", f"'{name}' 일정을 저장했어요.\n{where}")

    def delete_med(self, i: int):
        item = self.meds[i]
        if messagebox.askyesno("약속", f"'{item['name']}' 일정을 삭제할까요?"):
            self.meds.pop(i)
            if self.save(f"일정 삭제: {item['name']}"):
                self.refresh_all()

    def test_notify(self, i: int):
        """main.py의 알림 로직으로 이 약의 알림을 지금 바로 보내 본다."""
        med = self.meds[i]
        if not reminder.channels():
            if messagebox.askyesno("약속", "알림 채널이 설정되지 않았어요. 설정 창을 열까요?"):
                self.open_settings()
            return
        data = {"user_name": self.data.get("user_name", ""), "medicines": [med]}
        self.status_label.configure(text="알림을 보내는 중...", text_color="#A7D8D2")

        def done(kind, val):
            self.refresh_status()
            if kind == "err":
                return messagebox.showerror("약속", f"알림을 보내지 못했어요.\n{val}")
            if val["failed"]:
                return messagebox.showerror("약속", "알림을 보내지 못했어요.\n" + "\n".join(val["errors"]))
            msg = f"'{med['name']}' 알림을 보냈어요. ({', '.join(val['channels'])})"
            if val["warnings"]:
                msg += "\n\n참고:\n" + "\n".join(val["warnings"])
            elif not os.environ.get("GEMINI_API_KEY"):
                msg += "\n\n참고: Gemini 키가 없어 AI 안내문이 기본 문구로 갔을 수 있어요."
            messagebox.showinfo("약속", msg)

        self.run_bg(lambda: reminder.process(data, datetime.now(reminder.KST), test_mode=True), done)

    def open_settings(self):
        SettingsWindow(self)

    def add_to_form(self, name: str):
        """검색·사진 창에서 고른 약을 '약 이름' 칸에 채운다."""
        self.drug_entry.delete(0, "end")
        self.drug_entry.insert(0, name)
        bring_front(self)

    def open_search(self):
        SearchWindow(self)

    def open_photo(self):
        PhotoWindow(self)


# ---------------------------------------------------------------- 설정 창
class SettingsWindow(ctk.CTkToplevel):
    SECTIONS = [
        ("AI 안내문 (Gemini)", "안내문과 사진 읽기에 필요해요.", [("GEMINI_API_KEY", "Gemini API 키", True)]),
        ("알림 채널", "하나 이상 입력하세요. 둘 다 입력하면 둘 다 보내요.", [
            ("DISCORD_WEBHOOK_URL", "디스코드 웹훅 주소", True), ("EMAIL_USER", "이메일 주소 (Gmail)", False),
            ("EMAIL_PASSWORD", "이메일 앱 비밀번호 (16자리)", True), ("EMAIL_TO", "받는 이메일 (비우면 나에게)", False)]),
        ("GitHub 연동", "켜면 일정을 저장할 때 레포의 data/medicines.json도 함께 바뀌어 Actions 알림에 반영돼요.", [
            ("GITHUB_REPO", "레포 (예: 계정/yaksok)", False), ("GITHUB_TOKEN", "접근 토큰 (이 레포만, Contents 읽기·쓰기)", True)]),
    ]

    def __init__(self, app: YaksokApp):
        super().__init__(app)
        self.app = app
        self.title("설정")
        self.geometry("620x760")
        self.configure(fg_color=BG)
        self.saved = settings_store.load()
        self.entries: dict = {}
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 0))
        for title, hint, fields in self.SECTIONS:
            c = card(body)
            c.pack(fill="x", pady=6, padx=4)
            label(c, title, 14, True).pack(anchor="w", padx=16, pady=(12, 0))
            label(c, hint, 11, color=MUTED, wraplength=520, justify="left").pack(anchor="w", padx=16, pady=(0, 6))
            for key, text, secret in fields:
                label(c, text, 12, True, MUTED).pack(anchor="w", padx=16)
                placeholder = "환경변수로 설정됨" if key in os.environ and key not in self.saved else ""
                e = entry(c, placeholder, show="•" if secret else "")
                if key in self.saved:
                    e.insert(0, self.saved[key])
                e.pack(fill="x", padx=16, pady=(2, 8))
                self.entries[key] = e
            ctk.CTkFrame(c, height=4, fg_color="transparent").pack()
        label(body, "입력한 값은 이 컴퓨터의 사용자 폴더(.yaksok/settings.json)에만 저장되고 GitHub에는 올라가지 않아요.",
              11, color=MUTED, wraplength=540, justify="left").pack(anchor="w", padx=8, pady=6)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=16, pady=12)
        button(bar, "저장", self.save, width=90).pack(side="left")
        self.test_btn = button(bar, "연결 테스트", self.test, "ghost", width=110)
        self.test_btn.pack(side="left", padx=8)
        button(bar, "닫기", self.destroy, "plain", width=80).pack(side="right")
        self.after(200, lambda: bring_front(self))

    def values(self) -> dict:
        return {k: e.get().strip() for k, e in self.entries.items()}

    def save(self, quiet: bool = False):
        vals = self.values()
        settings_store.save(vals)
        settings_store.apply(vals, previous=self.saved)
        self.saved = settings_store.load()
        self.app.reload()  # GitHub 연동이 바뀌었을 수 있어 일정을 다시 불러온다
        if not quiet:
            messagebox.showinfo("약속", "설정을 저장했어요.", parent=self)

    def test(self):
        """저장한 설정으로 테스트 알림을 보내고, GitHub 연동도 확인한다."""
        self.save(quiet=True)
        user = self.app.data.get("user_name", "")
        self.test_btn.configure(state="disabled", text="확인하는 중...")

        def work():
            out = []
            if reminder.channels():
                failed = reminder.notify("연결 테스트", f"{datetime.now(reminder.KST):%H:%M}", user,
                                         "알림이 정상적으로 연결됐어요. 이 메시지가 보이면 설정이 끝난 거예요.")
                out.append(f"알림 전송 성공 ({', '.join(reminder.channels())})" + (f"\n일부 실패: {failed}" if failed else ""))
            else:
                out.append("알림 채널이 입력되지 않았어요.")
            if storage_mode() == "GitHub 레포":
                load_schedule()
                out.append("GitHub 레포 연결 확인 완료")
            return "\n".join(out)

        def done(kind, val):
            self.test_btn.configure(state="normal", text="연결 테스트")
            (messagebox.showinfo if kind == "ok" else messagebox.showerror)("약속", val if kind == "ok" else f"연결에 실패했어요.\n{val}", parent=self)

        self.app.run_bg(work, done)


# ---------------------------------------------------------------- 약 검색 창
class SearchWindow(ctk.CTkToplevel):
    def __init__(self, app: YaksokApp):
        super().__init__(app)
        self.app = app
        self.title("약 검색")
        self.geometry("680x760")
        self.configure(fg_color=BG)
        self.results: list[dict] = []
        self.rows: list = []
        self.sel = -1
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        top = card(self)
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        top.grid_columnconfigure(0, weight=1)
        label(top, "약 검색", 16, True).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 0))
        label(top, "제품명 또는 주성분으로 검색할 수 있어요.", 12, color=MUTED).grid(row=1, column=0, columnspan=2, sticky="w", padx=16)
        self.q = entry(top, "예: 가네카정, 시메티콘")
        self.q.grid(row=2, column=0, sticky="ew", padx=(16, 6), pady=14)
        self.q.bind("<Return>", lambda e: self.do_search())
        button(top, "검색", self.do_search, width=72).grid(row=2, column=1, padx=(0, 16))

        self.status = label(self, "", 12, color=MUTED)
        self.status.grid(row=1, column=0, sticky="w", padx=20)
        self.list_frame = ctk.CTkScrollableFrame(self, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER, height=200)
        self.list_frame.grid(row=2, column=0, sticky="nsew", padx=16, pady=6)

        bottom = card(self)
        bottom.grid(row=3, column=0, sticky="nsew", padx=16, pady=(6, 16))
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_rowconfigure(1, weight=1)
        btns = ctk.CTkFrame(bottom, fg_color="transparent")
        btns.grid(row=0, column=0, sticky="w", padx=14, pady=12)
        self.ai_btn = button(btns, "AI 쉬운 설명 보기", self.explain)
        self.ai_btn.pack(side="left")
        button(btns, "내 일정에 추가", self.add, "ghost").pack(side="left", padx=8)
        self.detail = textbox(bottom, height=210)
        self.detail.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        set_text(self.detail, "")
        self.after(200, lambda: (bring_front(self), self.q.focus_set()))

    def do_search(self):
        q = self.q.get()
        self.results, self.sel = [], -1
        self.draw_rows()
        set_text(self.detail, "")
        if len(clean_name(q)) < 2:
            self.status.configure(text="두 글자 이상 입력해 주세요.")
            return
        try:
            self.results = search_any(q, 10)
        except FileNotFoundError:
            self.status.configure(text="약 데이터(data/drug_info_clean.csv)를 찾지 못했어요.")
            return
        if not self.results:
            self.status.configure(text="검색 결과가 없어요. 이름을 다르게 써 보거나 약사에게 확인해 주세요.")
            return
        self.status.configure(text=f"검색 결과 {len(self.results)}건")
        self.draw_rows()
        self.select(0)

    def draw_rows(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        self.rows = []
        for i, r in enumerate(self.results):
            row = ctk.CTkFrame(self.list_frame, fg_color=CELL, corner_radius=10)
            row.pack(fill="x", pady=3, padx=2)
            a = label(row, short_name(r), 13, True, anchor="w", justify="left", wraplength=560)
            a.pack(anchor="w", padx=12, pady=(8, 0))
            b = label(row, f"{clean_name(r['업체명'])}  ·  {clean_name(r['주성분'])[:40]}", 12, color=MUTED, anchor="w")
            b.pack(anchor="w", padx=12, pady=(0, 8))
            for w in (row, a, b):
                w.bind("<Button-1>", lambda e, i=i: self.select(i))
            self.rows.append(row)

    def select(self, i: int):
        self.sel = i
        for j, row in enumerate(self.rows):
            row.configure(fg_color=TINT if j == i else CELL)
        r = self.results[i]
        set_text(self.detail, f"제품명: {clean_name(r['제품명'])}\n제조사: {clean_name(r['업체명'])}\n주성분: {clean_name(r['주성분'])}\n\n"
                              "'AI 쉬운 설명 보기'를 누르면 위 정보를 바탕으로 쉽게 풀어 설명해 줘요.")

    def current(self):
        return self.results[self.sel] if 0 <= self.sel < len(self.results) else None

    def explain(self):
        row = self.current()
        if not row:
            return messagebox.showinfo("약속", "먼저 약을 골라 주세요.")
        self.ai_btn.configure(state="disabled", text="만드는 중...")
        set_text(self.detail, "안내문을 만드는 중이에요...")

        def done(kind, val):
            self.ai_btn.configure(state="normal", text="AI 쉬운 설명 보기")
            set_text(self.detail, val if kind == "ok" else f"안내문을 만들지 못했어요.\n{val}")

        self.app.run_bg(lambda: make_guide(row), done)

    def add(self):
        row = self.current()
        if not row:
            return messagebox.showinfo("약속", "먼저 약을 골라 주세요.")
        self.app.add_to_form(short_name(row))
        self.destroy()


# ---------------------------------------------------------------- 사진 창
class PhotoWindow(ctk.CTkToplevel):
    def __init__(self, app: YaksokApp):
        super().__init__(app)
        self.app = app
        self.title("사진으로 알아보기")
        self.geometry("680x800")
        self.configure(fg_color=BG)
        self.path: str | None = None
        self.candidates: list[dict] = []
        self.preview = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        top = card(self)
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        label(top, "사진으로 약 알아보기", 16, True).pack(anchor="w", padx=16, pady=(14, 0))
        label(top, "약 포장지의 제품명이 보이게 찍거나, 사진 파일을 골라 주세요.", 12, color=MUTED).pack(anchor="w", padx=16)
        row = ctk.CTkFrame(top, fg_color="transparent")
        row.pack(anchor="w", padx=16, pady=14)
        button(row, "카메라로 찍기", self.from_camera, "ghost").pack(side="left")
        button(row, "사진 파일 고르기", self.from_file, "ghost").pack(side="left", padx=8)

        mid = card(self)
        mid.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        self.img_label = ctk.CTkLabel(mid, text="(사진이 여기에 보여요)", text_color=MUTED, height=200, fg_color="#FAFCFC", corner_radius=10, font=font(12))
        self.img_label.pack(fill="x", padx=14, pady=(14, 8))
        self.read_btn = button(mid, "약 이름 읽기", self.read_name, state="disabled")
        self.read_btn.pack(anchor="w", padx=14, pady=(0, 6))
        self.status = label(mid, "", 12, color=MUTED, anchor="w", justify="left", wraplength=600)
        self.status.pack(fill="x", padx=14, pady=(0, 6))
        self.confirm = ctk.CTkFrame(mid, fg_color="transparent")
        self.confirm.pack(fill="x", padx=14, pady=(0, 12))

        bottom = card(self)
        bottom.grid(row=2, column=0, sticky="nsew", padx=16, pady=(8, 16))
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_rowconfigure(0, weight=1)
        self.detail = textbox(bottom, height=180)
        self.detail.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        set_text(self.detail, "")
        self.after(200, lambda: bring_front(self))

    def set_image(self, path: str):
        self.path = path
        self.read_btn.configure(state="normal")
        self.status.configure(text="")
        for w in self.confirm.winfo_children():
            w.destroy()
        set_text(self.detail, "")
        try:
            from PIL import Image

            img = Image.open(path)
            img.thumbnail((600, 220))
            self.preview = ctk.CTkImage(light_image=img, size=img.size)
            self.img_label.configure(image=self.preview, text="")
        except Exception:  # noqa: BLE001  (Pillow가 없어도 동작은 한다)
            self.img_label.configure(image=None, text=f"사진 선택됨: {Path(path).name}")

    def from_file(self):
        p = filedialog.askopenfilename(parent=self, title="약 사진 고르기", filetypes=[("사진", "*.jpg *.jpeg *.png *.webp")])
        if p:
            self.set_image(p)

    def from_camera(self):
        try:
            p = capture_from_camera()
        except ImportError:
            return messagebox.showinfo("약속", "카메라를 쓰려면 터미널에서 pip install opencv-python 을 먼저 실행해 주세요.\n지금은 '사진 파일 고르기'를 쓰면 돼요.")
        except Exception as e:  # noqa: BLE001
            return messagebox.showerror("약속", str(e))
        if p:
            self.set_image(p)

    def read_name(self):
        from photo_identify import identify_drug_from_image

        path = self.path
        mime = mimetypes.guess_type(path)[0] or "image/jpeg"
        self.read_btn.configure(state="disabled", text="읽는 중...")
        self.status.configure(text="사진을 읽는 중이에요...")

        def work():
            with open(path, "rb") as f:
                return identify_drug_from_image(f.read(), mime)

        def done(kind, val):
            self.read_btn.configure(state="normal", text="약 이름 읽기")
            if kind == "err":
                self.status.configure(text=f"사진을 읽지 못했어요.\n{val}")
                return
            if not val["name"]:
                self.status.configure(text="사진에서 제품명을 읽지 못했어요. 글자가 잘 보이게 다시 찍어 주세요.")
                return
            self.status.configure(text=f"AI가 읽은 이름: {val['name']}")
            self.show_candidates(val["name"])

        self.app.run_bg(work, done)

    def show_candidates(self, name: str):
        for w in self.confirm.winfo_children():
            w.destroy()
        self.candidates = search(name, 5)
        if not self.candidates:
            self.status.configure(text=self.status.cget("text") + "\n약 데이터에서 이 약을 찾지 못했어요. 약사에게 확인해 주세요.")
            return
        label(self.confirm, "이 약이 맞나요? 맞는 약을 골라 주세요.", 13, True).pack(anchor="w", pady=(0, 4))
        values = [short_name(r) for r in self.candidates] + ["해당 없음"]
        self.box = ctk.CTkComboBox(self.confirm, values=values, state="readonly", height=34, corner_radius=8, border_color=BORDER,
                                   fg_color="white", button_color=PRIMARY, button_hover_color=DARK, text_color=TEXT,
                                   font=font(12), dropdown_font=font(12))
        self.box.pack(fill="x", pady=(0, 8))
        self.box.set(values[0])
        row = ctk.CTkFrame(self.confirm, fg_color="transparent")
        row.pack(anchor="w")
        button(row, "약 정보 보기", self.explain).pack(side="left")
        button(row, "내 일정에 추가", self.add, "ghost").pack(side="left", padx=8)

    def chosen(self):
        value = self.box.get()
        for r in self.candidates:
            if short_name(r) == value:
                return r
        messagebox.showinfo("약속", "맞는 약이 없다면 다시 찍거나 약사에게 확인해 주세요.")
        return None

    def explain(self):
        row = self.chosen()
        if not row:
            return
        set_text(self.detail, "안내문을 만드는 중이에요...")

        def done(kind, val):
            set_text(self.detail, val if kind == "ok" else f"안내문을 만들지 못했어요.\n{val}")

        self.app.run_bg(lambda: make_guide(row), done)

    def add(self):
        row = self.chosen()
        if row:
            self.app.add_to_form(short_name(row))
            self.destroy()


def main():
    YaksokApp().mainloop()


if __name__ == "__main__":
    main()
