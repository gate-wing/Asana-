# -*- coding: utf-8 -*-
"""
Asana リマインダー（制作・更新プロジェクト用）

10分ごとに Asana をチェックし、下記2種類のポップアップを画面右上に出す常駐ツール。
どちらも「OK」を押すまで消えず、放置しても10分ごとに最新情報へ更新される。

  ① チーム内確認待ちアラート
     Status＝「チーム内確認待ち」が しきい値（既定2件）以上でポップアップ。
     17時以降は1件でも通知し、×で閉じても0件になるまで出し続ける。

  ② 今日の時間指定タスク対応アラート
     今日期日 × 名前に指定キーワード（AM/17時/ASAP/流し込み/表示確認 等）
     を含むタスクが 1件以上でポップアップ。
     ただし「流し込み」「表示確認」は担当者が割り当てられたら通知しない。

設定はすべて隣の config.ini。アクセストークンもそこに保存する。
追加ライブラリ不要（Python標準機能のみ）。
"""

import os
import sys
import re
import json
import shutil
import configparser
import urllib.request
import urllib.parse
import urllib.error
import tkinter as tk
from datetime import datetime

# ---- 実行フォルダ（config.ini / ログの置き場所）----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")       # 各自：トークンだけ（Git管理外）
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.ini")   # 全員共通：git配布される設定
LOG_PATH = os.path.join(BASE_DIR, "asana_reminder.log")

API_BASE = "https://app.asana.com/api/1.0"


def log(message):
    """簡単なログ出力（トラブル時の確認用。トークンは書き込まない）"""
    line = "[{}] {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), message)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_config():
    """設定を読み込む。
      ・共通設定（キーワード/しきい値/通知時間など）は settings.ini（全員共通・git配布）
      ・個人のトークンは config.ini（各自・Git管理外）
    settings.ini を優先し、そこに無いキーだけ config.ini で補う。
    これにより settings.ini を git pull で配れば、config.ini を各自で編集しなくても
    全員に共通設定が行き渡る（旧バージョンで config.ini に設定を書いていても互換で動く）。
    ※トークンは settings.ini からは絶対に読まない（GitHubに上げないため）。"""
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError("config.ini が見つかりません: " + CONFIG_PATH)

    user = configparser.ConfigParser()       # config.ini（トークン。旧版では設定も）
    user.read(CONFIG_PATH, encoding="utf-8")
    common = configparser.ConfigParser()     # settings.ini（共通設定。無ければ空）
    common.read(SETTINGS_PATH, encoding="utf-8")

    def get(section, option, fallback=None):
        """settings.ini を優先し、無ければ config.ini から取る（旧版互換）"""
        if common.has_option(section, option):
            return common.get(section, option)
        if user.has_option(section, option):
            return user.get(section, option)
        return fallback

    def get_int(section, option, fallback):
        v = get(section, option, None)
        try:
            return int(str(v).strip()) if v is not None and str(v).strip() != "" else fallback
        except ValueError:
            return fallback

    def get_float(section, option, fallback):
        v = get(section, option, None)
        try:
            return float(str(v).strip()) if v is not None and str(v).strip() != "" else fallback
        except ValueError:
            return fallback

    def get_bool(section, option, fallback):
        v = get(section, option, None)
        if v is None or str(v).strip() == "":
            return fallback
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    keywords_raw = get("today_alert", "keywords", "") or ""
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]

    # このキーワードを含むタスクは、担当者が割り当てられたら通知しない
    assignee_optional_raw = get(
        "today_alert", "assignee_optional_keywords", "流し込み,表示確認") or ""
    assignee_optional = [k.strip() for k in assignee_optional_raw.split(",") if k.strip()]

    cfg = {
        # ★トークンは config.ini からのみ（settings.ini からは読まない）
        "token": (user.get("asana", "token", fallback="") or "").strip(),
        "workspace_gid": (get("settings", "workspace_gid", "") or "").strip(),
        "project_gid": (get("settings", "project_gid", "") or "").strip(),
        "status_field_gid": (get("settings", "status_field_gid", "") or "").strip(),
        "status_value_gid": (get("settings", "status_value_gid", "") or "").strip(),
        "threshold": get_int("settings", "threshold", 5),
        "evening_hour": get_int("settings", "evening_hour", 17),
        "evening_threshold": get_int("settings", "evening_threshold", 1),
        "active_start_hour": get_int("settings", "active_start_hour", 9),
        "active_end_hour": get_int("settings", "active_end_hour", 22),
        "quiet_weekend": get_bool("settings", "quiet_weekend", True),
        "interval_minutes": get_float("settings", "interval_minutes", 10),
        # 今日の未担当タスクアラート
        "today_enabled": get_bool("today_alert", "enabled", True),
        "keywords": keywords,
        "match_time": get_bool("today_alert", "match_time", True),
        "today_threshold": get_int("today_alert", "threshold", 1),
        # このStatusになったら通知対象から外す（作業完了まで通知し続けるため）
        "done_statuses": [s.strip() for s in (get(
            "today_alert", "done_statuses", "作業完了,全て完了") or "").split(",") if s.strip()],
        "assignee_optional_keywords": assignee_optional,
        # ②のポップアップに表示するひとことアドバイス
        "today_note": (get(
            "today_alert", "note", "流し込み確認は午前中に対応しましょう") or "").strip(),
    }
    return cfg


def _api_get_page(url, token):
    """Asana API を GET して (data, 次ページのoffset) を返す"""
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    obj = json.loads(body)
    data = obj.get("data", [])
    nxt = obj.get("next_page")
    offset = nxt.get("offset") if nxt else None
    return data, offset


# 全未完了タスクの取得に使う項目（①②で共用）
_ALL_TASK_FIELDS = (
    "name,due_on,assignee,"
    "custom_fields.gid,custom_fields.enum_value.gid,custom_fields.enum_value.name")

# ページ送りの安全弁（1ページ100件 × 最大ページ数）
_MAX_PAGES = 60


def fetch_all_incomplete(cfg):
    """プロジェクトの未完了タスクを、ページ送りで全件取得する。
    Asanaの検索APIは100件で頭打ち＆ページ送り不可のため、
    ページ送りできる /tasks?project= 経由で取りこぼしなく全件取る。"""
    tasks = []
    offset = None
    pages = 0
    while True:
        params = {
            "project": cfg["project_gid"],
            "completed_since": "now",   # 未完了タスクだけを返す
            "opt_fields": _ALL_TASK_FIELDS,
            "limit": "100",
        }
        if offset:
            params["offset"] = offset
        url = "{}/tasks?{}".format(API_BASE, urllib.parse.urlencode(params))
        data, offset = _api_get_page(url, cfg["token"])
        tasks.extend(data)
        pages += 1
        if not offset or pages >= _MAX_PAGES:
            if offset:
                log("警告: {}ページ({}件)で打ち切り。タスクが多すぎます".format(pages, len(tasks)))
            break
    log("全未完了タスク取得: {} 件 ({} ページ)".format(len(tasks), pages))
    return tasks


def _status_of(task, status_field_gid):
    """タスクのStatusカスタムフィールドの (値gid, 表示名) を返す"""
    for f in task.get("custom_fields") or []:
        if f.get("gid") == status_field_gid:
            ev = f.get("enum_value")
            if ev:
                return ev.get("gid"), ev.get("name")
            return None, None
    return None, None


def filter_status_tasks(tasks, cfg):
    """取得済みタスクから Status＝チーム内確認待ち のタスク名リストを返す"""
    result = []
    for t in tasks:
        gid, _name = _status_of(t, cfg["status_field_gid"])
        if gid == cfg["status_value_gid"]:
            result.append(t.get("name") or "(名称なし)")
    return result


def name_matches(name, keywords, match_time):
    """タスク名がキーワード/時刻表記のいずれかに該当するか"""
    if not name:
        return False
    for kw in keywords:
        if kw.upper() in ("AM", "PM"):
            # Instagram の "am" 等を誤検知しないよう英字の単語境界で判定
            if re.search(r"(?<![A-Za-z])" + kw.upper() + r"(?![A-Za-z])",
                         name, re.IGNORECASE):
                return True
        elif kw in name:
            return True
    if match_time:
        # 「17時」「12時まで」「10:00」などの時刻表記
        if re.search(r"\d{1,2}\s*時", name):
            return True
        if re.search(r"\d{1,2}:\d{2}", name):
            return True
    return False


def filter_today_timed(tasks, cfg):
    """取得済みタスクから 今日期日 × 名前が時刻/キーワード該当 のタスク名リストを返す。
    ただし「流し込み」「表示確認」等（assignee_optional_keywords）は担当者ありなら除外する。"""
    today = datetime.now().strftime("%Y-%m-%d")
    result = []
    for t in tasks:
        if t.get("due_on") != today:
            continue
        name = t.get("name") or ""
        if not name_matches(name, cfg["keywords"], cfg["match_time"]):
            continue
        # Status が「作業完了」等になっていたら通知対象から外す
        _gid, status_name = _status_of(t, cfg["status_field_gid"])
        if status_name in cfg["done_statuses"]:
            continue
        # 「流し込み」「表示確認」は担当者が入っていたら通知しない（担当が対応するため）
        if any(kw in name for kw in cfg["assignee_optional_keywords"]):
            if t.get("assignee"):
                continue
        result.append(name or "(名称なし)")
    return result


class ReminderApp:
    def __init__(self, cfg):
        self.cfg = cfg
        self.interval_ms = int(max(0.1, cfg["interval_minutes"]) * 60 * 1000)

        # 2種類のアラート定義（それぞれ独立して表示・OK管理する）
        self.alerts = {
            "status": {
                "ack": False, "popup": None, "y": 40,
                "color": "#e53935", "color2": "#8e0000",   # 点滅する赤
                "title": "⚠ 警告 - チーム内確認待ち",
                "header": "チーム内確認待ち {count} 件",
                "message": "制作・更新プロジェクトで確認待ちが {count} 件たまっています！\nすぐに対応してください。",
            },
            "today": {
                "ack": False, "popup": None, "y": 460,
                "color": "#fb8c00", "color2": "#bf360c",   # 点滅するオレンジ→赤
                "renotify": True,   # 作業完了になるまで、OKしても再通知し続ける
                "title": "⚠ 警告 - 今日の時間指定タスク",
                "header": "今日の時間指定タスク {count} 件",
                "message": "今日期日で時刻指定（AM/17時/10:00等）の要対応タスクが {count} 件あります！\n作業完了になるまでお知らせし続けます。",
                "note": cfg.get("today_note", ""),
            },
        }

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.after(2000, self.check_loop)

    # ------------------------------------------------------------------
    def is_notify_time(self, now):
        """通知してよい時間帯か（夜間・土日は通知しない）"""
        cfg = self.cfg
        # 5=土曜, 6=日曜
        if cfg["quiet_weekend"] and now.weekday() >= 5:
            return False
        return cfg["active_start_hour"] <= now.hour < cfg["active_end_hour"]

    # ------------------------------------------------------------------
    def check_loop(self):
        cfg = self.cfg
        now = datetime.now()

        # 通知しない時間帯（夜間22〜9時・土日）はチェックせずスキップ
        if not self.is_notify_time(now):
            for key in self.alerts:
                self.alerts[key]["ack"] = False
                if self.alerts[key]["popup"] is not None:
                    self.close_popup(key)
            log("通知時間外（夜間/休日）のためスキップ")
            self.root.after(self.interval_ms, self.check_loop)
            return

        # まず未完了タスクを全件取得（①②で共用・取りこぼし防止）
        try:
            all_tasks = fetch_all_incomplete(cfg)
        except urllib.error.HTTPError as e:
            log("APIエラー HTTP {}: トークン/設定を確認してください".format(e.code))
            self.root.after(self.interval_ms, self.check_loop)
            return
        except urllib.error.URLError as e:
            log("通信エラー: {}".format(e.reason))
            self.root.after(self.interval_ms, self.check_loop)
            return
        except Exception as e:
            log("予期しないエラー(タスク取得): {}".format(e))
            self.root.after(self.interval_ms, self.check_loop)
            return

        # ① チーム内確認待ち（17時以降はしきい値を下げ、0件になるまで通知）
        try:
            names = filter_status_tasks(all_tasks, cfg)
            is_evening = datetime.now().hour >= cfg["evening_hour"]
            eff_threshold = cfg["evening_threshold"] if is_evening else cfg["threshold"]
            log("チェック: チーム内確認待ち = {} 件 (しきい値 {}{})".format(
                len(names), eff_threshold, " / 夕方=なくなるまで通知" if is_evening else ""))
            # 17時以降は×で閉じても、0件になるまで毎回再通知する
            self.handle_alert("status", names, eff_threshold, force_renotify=is_evening)
        except Exception as e:
            log("予期しないエラー(確認待ち): {}".format(e))

        # ② 今日の時間指定タスク
        if cfg["today_enabled"]:
            try:
                names2 = filter_today_timed(all_tasks, cfg)
                log("チェック: 今日の時間指定タスク = {} 件".format(len(names2)))
                self.handle_alert("today", names2, cfg["today_threshold"])
            except Exception as e:
                log("予期しないエラー(時間指定): {}".format(e))

        self.root.after(self.interval_ms, self.check_loop)

    # ------------------------------------------------------------------
    def handle_alert(self, key, names, threshold, force_renotify=False):
        """件数に応じてポップアップを出す/最新化する/閉じる。
        force_renotify=True のときは、そのアラートを一時的に再通知モードにする（17時以降用）。"""
        a = self.alerts[key]
        count = len(names)
        if count >= threshold:
            # renotify のアラートは、OKを押しても毎回再通知する
            # （＝対象が無くなる＝作業完了/0件になるまで出し続ける）
            if a.get("renotify") or force_renotify or not a["ack"]:
                # 毎回最新情報で表示し直す（放置対策・最前面へ）
                if a["popup"] is not None:
                    self.close_popup(key)
                self.show_popup(key, count, names)
        else:
            # しきい値未満に戻ったら再アラート可能な状態に戻す
            a["ack"] = False
            if a["popup"] is not None:
                self.close_popup(key)

    # ------------------------------------------------------------------
    def show_popup(self, key, count, names):
        a = self.alerts[key]
        c1 = a["color"]
        c2 = a.get("color2", c1)

        popup = tk.Toplevel(self.root)
        a["popup"] = popup
        popup.withdraw()                # 位置を決めるまで隠す（左にチラつくのを防ぐ）
        popup.title(a["title"])
        popup.configure(bg=c1)          # 外周＝警告色の太い枠
        popup.attributes("-topmost", True)
        popup.resizable(False, False)
        popup.protocol("WM_DELETE_WINDOW", lambda k=key: self.on_ok(k))

        width, height = 440, 400

        # ※音は鳴らさない（会社環境のため）。点滅の見た目だけで気づかせる。

        # 太い枠の内側
        border = tk.Frame(popup, bg=c1)
        border.pack(fill="both", expand=True, padx=6, pady=6)

        # 見出し（点滅する）
        header = tk.Frame(border, bg=c1)
        header.pack(fill="x")
        warn = tk.Label(header, text="⚠　警　告　⚠", bg=c1, fg="#ffffff",
                        font=("Meiryo UI", 13, "bold"))
        warn.pack(pady=(10, 0))
        count_lbl = tk.Label(header, text=a["header"].format(count=count),
                             bg=c1, fg="#fff9c4", font=("Meiryo UI", 17, "bold"))
        count_lbl.pack(pady=(2, 10))

        # 本文（白地）
        body = tk.Frame(border, bg="#ffffff")
        body.pack(fill="both", expand=True)

        tk.Label(
            body, text=a["message"].format(count=count),
            bg="#ffffff", fg="#b71c1c", font=("Meiryo UI", 10, "bold"),
            justify="left", wraplength=372,
        ).pack(padx=16, pady=(12, 2), anchor="w")

        # ひとことアドバイス（②のみ。黄色い帯で目立たせる）
        if a.get("note"):
            tk.Label(
                body, text="💡 " + a["note"],
                bg="#fff3cd", fg="#8a6d00", font=("Meiryo UI", 10, "bold"),
                justify="left", wraplength=372, anchor="w",
            ).pack(fill="x", padx=16, pady=(2, 4))

        tk.Label(
            body,
            text="最終更新 {}（放置しても10分ごとに最新へ更新）".format(
                datetime.now().strftime("%H:%M")),
            bg="#ffffff", fg="#5f6368", font=("Meiryo UI", 8),
        ).pack(padx=16, pady=(0, 4), anchor="w")

        # 閉じ方の案内（×で閉じる）。下部に固定表示するので先にpackする
        tk.Label(
            body, text="閉じるには右上の × を押してください",
            bg="#ffffff", fg="#9e9e9e", font=("Meiryo UI", 8),
        ).pack(side="bottom", pady=(4, 10))

        # タスク名リスト（スクロールバー付き。全件表示）
        list_frame = tk.Frame(body, bg="#f1f3f4")
        list_frame.pack(fill="both", expand=True, padx=16, pady=4)

        canvas = tk.Canvas(list_frame, bg="#f1f3f4", highlightthickness=0)
        vbar = tk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg="#f1f3f4")
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(inner_id, width=e.width))

        for n in names:
            tk.Label(
                inner, text="・" + n, bg="#f1f3f4", fg="#202124",
                font=("Meiryo UI", 11, "bold"), anchor="w", justify="left",
                wraplength=360,
            ).pack(fill="x", padx=8, pady=2)

        # マウスホイールでスクロール（このポップアップにマウスがある時だけ有効）
        def _wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        popup.update_idletasks()
        screen_w = popup.winfo_screenwidth()
        x = screen_w - width - 20
        popup.geometry("{}x{}+{}+{}".format(width, height, x, a["y"]))
        popup.deiconify()               # 位置確定後に表示（右上にだけ出る）
        popup.lift()
        popup.attributes("-topmost", True)   # deiconify後に最前面を再指定（隠れ防止）
        popup.focus_force()                  # 確実に前面へ持ってくる

        # 枠と見出しを点滅させて「焦る」演出
        self._blink(popup, [popup, border, header, warn, count_lbl], [c1, c2])

    # ------------------------------------------------------------------
    def _blink(self, popup, widgets, colors, idx=0):
        """枠・見出しの背景色を交互に切り替えて点滅させる"""
        try:
            if not popup.winfo_exists():
                return
        except Exception:
            return
        color = colors[idx % len(colors)]
        for w in widgets:
            try:
                w.configure(bg=color)
            except Exception:
                pass
        popup.after(450, lambda: self._blink(popup, widgets, colors, idx + 1))

    # ------------------------------------------------------------------
    def on_ok(self, key):
        self.alerts[key]["ack"] = True
        log("OK押下({}): 件数がしきい値未満に戻るまで再表示しません".format(key))
        self.close_popup(key)

    def close_popup(self, key):
        a = self.alerts[key]
        if a["popup"] is not None:
            try:
                a["popup"].destroy()
            except Exception:
                pass
            a["popup"] = None

    def run(self):
        self.root.mainloop()


def ensure_config_exists():
    """config.ini が無ければ config.sample.ini からコピーしてメモ帳で開き、案内を出す。
    そのまま続行してよければ True、初回セットアップで止める場合は False を返す。"""
    if os.path.exists(CONFIG_PATH):
        return True
    sample = os.path.join(BASE_DIR, "config.sample.ini")
    if not os.path.exists(sample):
        show_config_error("config.ini が見つかりません。\n"
                          "（見本 config.sample.ini も無いため自動作成できません）")
        return False
    try:
        shutil.copyfile(sample, CONFIG_PATH)
    except Exception as e:
        show_config_error("config.ini を作成できませんでした。\n\n{}".format(e))
        return False
    # 作った config.ini をメモ帳で開く
    try:
        import subprocess
        subprocess.Popen(["notepad.exe", CONFIG_PATH])
    except Exception:
        try:
            os.startfile(CONFIG_PATH)
        except Exception:
            pass
    log("初回セットアップ: config.ini を作成しました")
    show_config_error(
        "初回セットアップ\n\n"
        "設定ファイル config.ini を作成し、メモ帳で開きました。\n\n"
        "【やること】\n"
        "1) token = の右に、自分のAsanaトークンを貼り付ける\n"
        "2) 上書き保存する（Ctrl+S）\n"
        "3) もう一度このプログラム（動作テスト.bat など）を起動する\n\n"
        "トークン発行ページ: https://app.asana.com/0/my-apps",
        title="Asana リマインド - 初回セットアップ")
    return False


def show_config_error(message, title="Asana リマインド - 設定エラー"):
    """設定エラー／案内を利用者に見せる"""
    try:
        root = tk.Tk()
        root.withdraw()
        top = tk.Toplevel(root)
        top.title(title)
        top.attributes("-topmost", True)
        tk.Label(
            top, text=message, font=("Meiryo UI", 10),
            justify="left", padx=20, pady=20, wraplength=380,
        ).pack()
        tk.Button(top, text="閉じる", command=root.destroy,
                  font=("Meiryo UI", 10), width=10).pack(pady=(0, 16))
        root.mainloop()
    except Exception:
        pass


def main():
    # 初回起動時（config.iniが無い）は見本から自動作成して案内を出す
    if not ensure_config_exists():
        return
    try:
        cfg = load_config()
    except Exception as e:
        msg = "config.ini の読み込みに失敗しました。\n\n{}".format(e)
        log(msg)
        show_config_error(msg)
        sys.exit(1)

    if not cfg["token"] or cfg["token"].startswith("ここに"):
        msg = ("Asana の個人アクセストークンが設定されていません。\n\n"
               "config.ini を開いて、[asana] の token に\n"
               "自分のトークンを貼り付けてください。\n\n"
               "トークン発行: https://app.asana.com/0/my-apps")
        log("トークン未設定")
        show_config_error(msg)
        sys.exit(1)

    log("=== 起動: {}分ごとに監視 / 確認待ちしきい値 {}件 / 未担当アラート {} ===".format(
        cfg["interval_minutes"], cfg["threshold"],
        "有効" if cfg["today_enabled"] else "無効"))
    app = ReminderApp(cfg)
    app.run()


if __name__ == "__main__":
    main()
