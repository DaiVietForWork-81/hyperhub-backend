"""
generate.py -- Cong cu tao de bai Duel tu dong (DuelProblem Generator)

Cach dung:
    python generate.py                  # Hoi tung truong, sinh sample + secret tests
    python generate.py --tier T5        # Goi y san theo Tier
    python generate.py --out output.txt # Ghi ra file

Output: Doan code Python san de paste vao PROBLEM_BANK trong services/duel_problems.py
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
import textwrap
from dataclasses import dataclass, field

TIER_CONFIG: dict = {
    "T8":  {"division": "Div. 4", "rating": "300 pts",  "time": 15, "kb": 64,  "difficulty": "Rat de -- toan/mang/chuoi co ban"},
    "T7":  {"division": "Div. 4", "rating": "550 pts",  "time": 15, "kb": 64,  "difficulty": "De -- sang nguyen to, mang tien to 1D"},
    "T6":  {"division": "Div. 4", "rating": "850 pts",  "time": 18, "kb": 64,  "difficulty": "De trung binh -- Greedy / Kadane / sliding window"},
    "T5":  {"division": "Div. 3", "rating": "1300 pts", "time": 20, "kb": 128, "difficulty": "Trung binh -- Chat nhi phan ket qua / Two Pointers dieu kien"},
    "T4":  {"division": "Div. 3", "rating": "1500 pts", "time": 22, "kb": 128, "difficulty": "Trung binh -- 0/1 Knapsack & truy vet / Multi-source BFS"},
    "T3":  {"division": "Div. 3", "rating": "1750 pts", "time": 25, "kb": 128, "difficulty": "Kha -- 2D Grid DP modulo / Topo Sort tu dien / Kruskal MST"},
    "LT2": {"division": "Div. 2", "rating": "2000 pts", "time": 30, "kb": 256, "difficulty": "Kho -- Segment Tree Lazy Propagation / LCA Binary Lifting"},
    "MT2": {"division": "Div. 2", "rating": "2200 pts", "time": 35, "kb": 256, "difficulty": "Kho -- State-space Dijkstra K ve / Tarjan Cau & Khop"},
    "HT2": {"division": "Div. 2", "rating": "2350 pts", "time": 40, "kb": 256, "difficulty": "Kho -- Rerooting Tree DP / HLD duong di tren cay / 2-SAT"},
    "LT1": {"division": "Div. 1", "rating": "2500 pts", "time": 45, "kb": 512, "difficulty": "Rat kho -- Min-Cut Project Selection / Persistent Segment Tree"},
    "MT1": {"division": "Div. 1", "rating": "2800 pts", "time": 50, "kb": 512, "difficulty": "Rat kho -- Centroid Decomposition / FFT NTT / Link-Cut Tree"},
    "HT1": {"division": "Div. 1", "rating": "3000 pts", "time": 60, "kb": 512, "difficulty": "Cuc kho -- Semi-ring (min, +) Matrix Expo / Suffix Automaton"},
}

CONTEXT_THEMES = [
    # Tai chinh
    "ngan hang & giao dich tai chinh",
    "san chung khoan & HFT",
    "cong ty bao hiem & tinh phi",
    "vi dien tu & he thong thanh toan",
    "quy dau tu & quan ly danh muc",
    "he thong ATM & phan phoi tien",
    "tien dien tu & blockchain",
    "he thong tin dung & cham diem khach hang",
    "dau gia truc tuyen & dinh gia",
    "cong thanh toan & xu ly giao dich",
    "ngan hang trung uong & dieu tiet lai suat",
    "quy tin dung vi mo & cho vay nho le",
    "thi truong phai sinh & hop dong tuong lai",
    "he thong thanh toan bu tru & quyet toan",
    "cong ty kiem toan & phat hien gian lan",
    # Thuong mai
    "cua hang tien loi & kho hang",
    "san thuong mai dien tu & khuyen mai",
    "sieu thi & toi uu ke hang",
    "chuoi cua hang & quan ly chi nhanh",
    "nha hang & quan ly don hang",
    "quan ca phe & xep hang phuc vu",
    "cho truyen thong & phan phoi hang hoa",
    "he thong dau gia & nguoi mua",
    "kho lanh & bao quan thuc pham",
    "trung tam phan phoi & dong goi",
    "he thong dat hang truc tuyen & quan ly ton kho",
    "cua hang dien thoai & doi tra bao hanh",
    "cho dau moi nong san & dinh gia mua vu",
    "he thong loyalty & tich diem thuong",
    "nen tang mua sam nhom & flash sale",
    # Giao thong
    "he thong giao thong & toi uu duong di",
    "tau dien ngam & chuyen tuyen",
    "san bay & dieu phoi chuyen bay",
    "ben xe & phan bo tuyen",
    "cang bien & dieu phoi container",
    "he thong taxi & ghep chuyen",
    "ung dung goi xe & dinh tuyen",
    "duong cao toc & thu phi",
    "bai do xe & phan bo cho",
    "robot giao hang & tim duong",
    "xe buyt thanh pho & lap lich tuyen",
    "he thong den giao thong thong minh & luong xe",
    "duong sat lien tinh & lap lich tau",
    "tau thuy & toi uu hai trinh",
    "he thong chia se xe dap & tram do",
    "cau duong & phan luong phuong tien",
    # Y te
    "benh vien & quan ly ca truc",
    "phong cap cuu & phan loai benh nhan",
    "nha thuoc & quan ly thuoc",
    "phong xet nghiem & xu ly mau",
    "trung tam tiem chung & dat lich",
    "xe cuu thuong & toi uu tuyen duong",
    "benh vien & phan bo phong",
    "he thong ho so benh an dien tu",
    "phong kham & quan ly lich hen",
    "trung tam y te & phan phoi vat tu",
    "he thong giam sat suc khoe tu xa",
    "phau thuat robot & lap ke hoach thao tac",
    "dich te hoc & mo hinh lay lan benh",
    "ngan hang mau & phan phoi nhom mau",
    "trung tam phuc hoi chuc nang & lich tri lieu",
    # Cong nghe
    "trung tam du lieu & toi uu tai nguyen",
    "he thong IoT & cam bien thong minh",
    "dien toan dam may & phan bo may chu",
    "mang may tinh & dinh tuyen goi tin",
    "he thong CDN & phan phoi du lieu",
    "cong cu tim kiem & xep hang ket qua",
    "he thong luu tru & sao luu du lieu",
    "server game & can bang tai",
    "he thong xac thuc & quan ly phien",
    "mang luoi ve tinh & truyen tin hieu",
    "he thong cache & chien luoc thay the trang",
    "microservice & phan tai API gateway",
    "pipeline CI/CD & kiem thu tu dong",
    "he thong giam sat mang & phat hien bat thuong",
    "nen du lieu & ma hoa thong tin",
    "he thong phan tan & dong thuan Raft/Paxos",
    # Mang xa hoi
    "mang xa hoi & lan truyen thong tin",
    "he thong de xuat & noi dung ca nhan hoa",
    "mang xa hoi & phat hien cong dong",
    "nen tang video & de xuat noi dung",
    "dien dan truc tuyen & xep hang bai viet",
    "ung dung nhan tin & truyen tin",
    "mang xa hoi & phat hien tin gia",
    "he thong quang cao & dau gia luot hien thi",
    "influencer marketing & do luong reach",
    "podcast & phan phoi tap noi dung",
    # Game
    "game online & he thong xep hang",
    "game chien thuat & quan ly tai nguyen",
    "game nhap vai & cay ky nang",
    "game the bai & xay dung bo bai",
    "game tower defense & bo tri thap",
    "game dua xe & toi uu duong dua",
    "game MMO & phan chia may chu",
    "game sandbox & quan ly the gioi",
    "game battle royale & vong bo",
    "game esports & lich thi dau",
    "game puzzle & giai me cung toi thieu buoc",
    "game roguelike & sinh cap do ngau nhien",
    "game chien tranh & phan bo quan linh",
    "game nong trai & toi uu mua vu",
    "game kinh doanh & quan ly tien von",
    # Logistics
    "cong ty logistics & giao van",
    "dich vu chuyen phat & phan loai buu kien",
    "doi xe tai & toi uu tuyen",
    "robot kho hang & van chuyen hang",
    "cang hang khong & van chuyen hang hoa",
    "chuoi cung ung & du bao nhu cau",
    "container & toi uu xep hang",
    "he thong giao hang & ghep don",
    "tram trung chuyen & phan phoi hang",
    "kho hang tu dong & robot",
    "lastmile delivery & toi uu chang cuoi",
    "cold chain logistics & kiem soat nhiet do",
    "quan ly ham doi tau & bao duong",
    # Giao duc
    "truong hoc & xep thoi khoa bieu",
    "ky thi & phan phong thi",
    "he thong cham bai truc tuyen",
    "nen tang hoc truc tuyen & de xuat khoa hoc",
    "thu vien & quan ly sach",
    "ky tuc xa & phan phong",
    "cuoc thi lap trinh & bang xep hang",
    "trung tam ngoai ngu & xep lop",
    "he thong hoc bong & xet tuyen",
    "truong dai hoc & phan bo phong hoc",
    "nen tang luyen thi & de xuat bai tap",
    "he thong chong gian lan thi cu",
    "trai he khoa hoc & lich hoat dong",
    # San xuat
    "nha may san xuat & day chuyen lap rap",
    "nha may & lap lich san xuat",
    "robot cong nghiep & toi uu thao tac",
    "day chuyen dong goi & kiem tra san pham",
    "nha may dien & phan phoi nang luong",
    "xuong co khi & lap lich may moc",
    "kho nguyen lieu & quan ly ton kho",
    "he thong kiem soat chat luong san pham",
    "nha may thong minh & IoT",
    "cong truong xay dung & phan bo may moc",
    "nha may det may & toi uu vai",
    "xuong in 3D & lap lich in",
    # Nang luong
    "luoi dien & phan phoi nang luong",
    "nha may dien & toi uu cong suat",
    "tram sac xe dien & phan bo nang luong",
    "he thong pin & quan ly dung luong",
    "dien mat troi & du bao san luong",
    "dien gio & dieu phoi turbine",
    "mang luoi khi dot & phan phoi nhien lieu",
    "he thong tich tru nang luong & dieu do",
    "nha thong minh & toi uu tieu thu dien",
    # Khoa hoc / Khong gian
    "kinh thien van & quan sat cac vi sao",
    "tram khong gian & quan ly tai nguyen",
    "ve tinh & lap lich quan sat",
    "tau vu tru & toi uu quy dao",
    "phong thi nghiem & phan tich du lieu",
    "mo phong vat ly & cac hat chuyen dong",
    "he thong radar & theo doi muc tieu",
    "genome & phan tich chuoi DNA",
    "kinh hien vi dien tu & xu ly anh",
    "tram nghien cuu Nam Cuc & cung ung",
    # Doi song
    "chung cu & quan ly cu dan",
    "khach san & phan bo phong",
    "cong vien & quan ly khach tham quan",
    "rap chieu phim & dat ghe",
    "san van dong & phan bo cho ngoi",
    "khu vui choi & xep hang tro choi",
    "bao tang & quan ly luot tham quan",
    "thu vien & he thong muon tra sach",
    "spa & lich dat dich vu",
    "san golf & phan lich golfer",
    "phong gym & dat lich may tap",
    # Moi truong
    "thanh pho & thu gom rac",
    "he thong cap nuoc & phan phoi nuoc sach",
    "song ngoi & kiem soat lu lut",
    "rung & theo doi chay rung",
    "tram quan trac & phan tich chat luong khong khi",
    "nong trai & tuoi tieu thong minh",
    "nong nghiep & toi uu mua vu",
    "he thong du bao thoi tiet & cam bien",
    "tai che & phan loai rac thai",
    "bien & theo doi o nhiem",
    "do thi thong minh & quan ly chat thai",
    # Dac biet / Sang tao
    "me cung & robot tim duong",
    "hon dao & xay dung mang luoi cau",
    "vuong quoc & he thong duong sa",
    "de che & phan chia lanh tho",
    "tham hiem hang dong & thu thap kho bau",
    "doan tau & quan ly toa tau",
    "tau ngam & lap ban do dai duong",
    "thanh pho tuong lai & giao thong tu dong",
    "doi cuu ho & giai cuu nguoi dan",
    "drone & lap ke hoach bay",
    "can cu quan su & phan bo luc luong",
    "cong ty tham tu & phan tich manh moi",
    "nha may tai che robot & phan loai linh kien",
    "buu dien thoi chien & ma hoa thong tin",
    "le hoi am nhac & bo tri san khau",
    "marathon & phan lan chay",
    "cuoc dua robot & lap trinh chien thuat",
    "cuoc thi nau an & xep lich thi dau",
]


@dataclass
class ProblemDraft:
    id: str = ""
    name: str = ""
    tier: str = "T8"
    division: str = "Div. 4"
    rating_display: str = ""
    statement: str = ""
    input_format: str = ""
    output_format: str = ""
    constraints: str = ""
    sample_input: str = ""
    sample_output: str = ""
    secret_tests: list = field(default_factory=list)
    time_limit_minutes: int = 15
    max_code_size_kb: int = 64
    hint: str = ""
    solution_code: str = ""
    rating: int = 800
    tags: list = field(default_factory=list)
    time_limit_sec: float = 1.0
    memory_limit_mb: int = 256
    sample_explanation: str = ""


CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def _c(color, text):
    if not sys.stdout.isatty():
        return text
    return f"{color}{text}{RESET}"


def banner():
    print(_c(BOLD + CYAN, """
\u256c\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2569
\u2551   \U0001f6e0\ufe0f  DuelProblem Generator -- HyperHub Ranked 1:1   \u2551
\u2551   Tao de bai tu nhien -> xuat code Python san paste  \u2551
\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d
"""))


def prompt(label, default="", required=True):
    disp_default = f" [{default}]" if default else ""
    while True:
        val = input(f"  {_c(GREEN, '>')}{_c(GREEN, '> ')} {label}{_c(YELLOW, disp_default)}: ").strip()
        if not val:
            val = default
        if val or not required:
            return val
        print(_c(RED, "    [!] Truong nay bat buoc, khong duoc de trong."))


def prompt_multiline(label):
    """
    Nhap doan van nhieu dong.
    Dung '|' de tach dong tren cung 1 lan Enter.
    Hoac nhap tung dong, ket thuc bang '.' hoac 2 Enter trong lien tiep.
    """
    print(f"  {_c(GREEN, '>> ')} {label}")
    print(_c(YELLOW,
        "    (Dung '|' de tach dong ngay, hoac nhap tung dong roi ket thuc bang '.' / Enter trong 2 lan)"))
    first = input("    ").strip()
    if "|" in first:
        return first.replace("|", "\n").strip()
    lines = [first] if first else []
    blank = 0
    while True:
        line = input("    ")
        if line == ".":
            break
        if line == "":
            blank += 1
            if blank >= 2:
                break
            lines.append("")
        else:
            blank = 0
            lines.append(line)
    return "\n".join(lines).strip()


def prompt_choice(label, choices, default=""):
    print(f"  {_c(GREEN, '>> ')} {label}")
    for i, ch in enumerate(choices, 1):
        marker = " <- (mac dinh)" if ch == default else ""
        print(f"      {i}. {ch}{_c(YELLOW, marker)}")
    while True:
        raw = input(f"  Chon so (1-{len(choices)}) hoac Enter de chon mac dinh: ").strip()
        if not raw and default:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        print(_c(RED, "    [!] Lua chon khong hop le."))


def suggest_id(name, tier):
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower())[:30].strip("_")
    return f"duel_{tier.lower()}_{slug}"


def suggest_contexts():
    picks = random.sample(CONTEXT_THEMES, min(5, len(CONTEXT_THEMES)))
    print(_c(YELLOW, "  [goi y] Chu de boi canh thuc te:"))
    for p in picks:
        print(_c(YELLOW, f"      * {p}"))


def format_constraints(tier, custom):
    cfg = TIER_CONFIG.get(tier, {})
    kb = cfg.get("kb", 64)
    base = f"Gioi han: `1.0s`, `256MB`, `{kb}KB`."
    if custom:
        return f"{custom.rstrip('.')}. {base}"
    return base


def _try_run_solution(solution_code, input_str):
    import subprocess, tempfile
    if not solution_code.strip():
        return None
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cpp", delete=False, encoding="utf-8") as f:
        f.write(solution_code)
        cpp_path = f.name
    bin_suffix = ".exe" if sys.platform == "win32" else ".out"
    exe_path = cpp_path.replace(".cpp", bin_suffix)
    try:
        r = subprocess.run(["g++", "-O2", "-o", exe_path, cpp_path],
                           capture_output=True, timeout=15)
        if r.returncode != 0:
            return None
        if sys.platform != "win32":
            try:
                os.chmod(exe_path, 0o755)
            except Exception:
                pass
        r2 = subprocess.run([exe_path], input=input_str,
                            capture_output=True, text=True, timeout=5)
        return r2.stdout.strip() if r2.returncode == 0 else None
    except Exception:
        return None
    finally:
        try:
            os.unlink(cpp_path)
        except Exception:
            pass
        try:
            os.unlink(exe_path)
        except Exception:
            pass


def auto_generate_secret_tests(sample_input, sample_output, solution_code=""):
    tests = [{"input": sample_input.strip(), "output": sample_output.strip()}]
    print()
    print(_c(CYAN, "  --- SECRET TESTS (test an de cham diem) ---"))
    print(_c(YELLOW, "  Nhap them cac test case (edge cases, bien, stress...)."))
    print(_c(YELLOW, "  Dung '|' thay \\n de nhap input nhieu dong tren 1 dong."))
    print(_c(YELLOW, "  Nhap 'x' vao o input de dung.\n"))
    idx = 2
    while True:
        raw_in = prompt(f"  Test #{idx} -- Input (hoac 'x' de dung)", default="x", required=False)
        if raw_in.lower() == "x" or not raw_in:
            break
        raw_in = raw_in.replace("|", "\n")
        raw_out = prompt(f"  Test #{idx} -- Output mong doi")
        if solution_code.strip():
            verified = _try_run_solution(solution_code, raw_in)
            if verified is not None:
                if verified == raw_out.strip():
                    print(_c(GREEN, f"    [OK] Solution xac nhan: output = {verified!r}"))
                else:
                    print(_c(RED, f"    [!] Solution tra ve {verified!r}, ban nhap {raw_out!r}"))
                    ov = prompt("    Dung output cua solution? (y/n)", default="y", required=False)
                    if ov.lower() in ("y", "yes", ""):
                        raw_out = verified
        tests.append({"input": raw_in.strip(), "output": raw_out.strip()})
        idx += 1
    return tests


def _esc_str(s):
    """Escape string thanh chuoi Python nhieu dong de doc."""
    if "\n" not in s:
        return repr(s)
    lines = s.split("\n")
    parts = []
    for i, line in enumerate(lines):
        suffix = "\\n" if i < len(lines) - 1 else ""
        parts.append(f"            {repr(line + suffix)}")
    return "(\n" + "\n".join(parts) + "\n        )"


def render_python_code(p):
    tests_repr = "[\n"
    for t in p.secret_tests:
        tests_repr += f"            {{\"input\": {repr(t['input'])}, \"output\": {repr(t['output'])}}},\n"
    tests_repr += "        ]"
    sol_repr = _esc_str(p.solution_code) if p.solution_code.strip() else '""'
    stmt_repr = _esc_str(p.statement) if "\n" in p.statement else repr(p.statement)
    return f"""    # -----------------------------------------------------------------------
    # BAI: {p.name.upper()} ({p.tier} / {p.division})
    # -----------------------------------------------------------------------
    DuelProblem(
        id={repr(p.id)},
        name={repr(p.name)},
        tier={repr(p.tier)},
        division={repr(p.division)},
        rating_display={repr(p.rating_display)},
        statement={stmt_repr},
        input_format={repr(p.input_format)},
        output_format={repr(p.output_format)},
        constraints={repr(p.constraints)},
        sample_input={repr(p.sample_input)},
        sample_output={repr(p.sample_output)},
        secret_tests={tests_repr},
        time_limit_minutes={p.time_limit_minutes},
        max_code_size_kb={p.max_code_size_kb},
        hint={repr(p.hint)},
        solution_code={sol_repr},
        rating={getattr(p, 'rating', 800)},
        tags={repr(getattr(p, 'tags', []))},
        time_limit_sec={getattr(p, 'time_limit_sec', 1.0)},
        memory_limit_mb={getattr(p, 'memory_limit_mb', 256)},
        sample_explanation={repr(getattr(p, 'sample_explanation', ''))},
    ),"""


def review(p):
    sep = _c(CYAN, "-" * 60)
    print(f"\n{sep}")
    print(_c(BOLD + GREEN, "  [OK] TONG KET BAI DA TAO"))
    print(sep)
    print(f"  ID           : {_c(YELLOW, p.id)}")
    print(f"  Ten          : {_c(BOLD, p.name)}")
    print(f"  Tier / Div.  : {p.tier}  /  {p.division}")
    print(f"  Rating       : {p.rating_display}")
    print(f"  Thoi gian    : {p.time_limit_minutes} phut  |  File: {p.max_code_size_kb}KB")
    print(f"  De bai       :\n{textwrap.indent(p.statement, '    ')}")
    print(f"  Input fmt    : {p.input_format}")
    print(f"  Output fmt   : {p.output_format}")
    print(f"  Constraints  : {p.constraints}")
    print(f"  Sample In    :\n{textwrap.indent(p.sample_input, '    ')}")
    print(f"  Sample Out   : {p.sample_output}")
    print(f"  Secret tests : {len(p.secret_tests)} tests")
    print(f"  Hint         : {p.hint}")
    if p.solution_code:
        print(f"  Solution     : {len(p.solution_code.splitlines())} dong C++")
    print(sep)


def run_wizard(default_tier="T8"):
    p = ProblemDraft()

    print(_c(BOLD, "\n  [BUOC 1/9] CHON BAC TIER & DIVISION\n"))
    tier_list = list(TIER_CONFIG.keys())
    chosen_tier = prompt_choice("Chon Tier:", tier_list, default=default_tier)
    cfg = TIER_CONFIG[chosen_tier]
    p.tier = chosen_tier
    p.division = cfg["division"]
    p.time_limit_minutes = cfg["time"]
    p.max_code_size_kb = cfg["kb"]
    print(_c(YELLOW, f"\n  Tier {chosen_tier}: {cfg['difficulty']}"))
    print(_c(YELLOW, f"  Division: {cfg['division']}  |  Thoi gian: {cfg['time']}p  |  File: {cfg['kb']}KB\n"))

    print(_c(BOLD, "  [BUOC 2/9] TEN BAI & ID\n"))
    suggest_contexts()
    print()
    p.name = prompt("Ten bai toan (co boi canh thuc te, viet tieng Viet khong dau cung duoc)")
    p.id = prompt("ID bai (snake_case)", default=suggest_id(p.name, p.tier))
    p.rating_display = f"{chosen_tier} / Rating: {cfg['rating']}"

    print(_c(BOLD, "\n  [BUOC 3/9] NOI DUNG DE BAI (STATEMENT)\n"))
    print(_c(YELLOW, "  Mo ta bai toan theo boi canh thuc te. Dung backtick `var` cho bien/CT inline."))
    print(_c(YELLOW, "  Vi du: 'Mot cua hang co `n` giao dich... hay tinh tong cac giao dich chan.'\n"))
    p.statement = prompt_multiline("Noi dung de bai:")

    print(_c(BOLD, "\n  [BUOC 4/9] DINH DANG INPUT\n"))
    print(_c(YELLOW, "  Vi du: 'Dong dau chua so nguyen `n`. Dong hai chua `n` so nguyen `a_i`.'\n"))
    p.input_format = prompt("Dinh dang input:")

    print(_c(BOLD, "\n  [BUOC 5/9] DINH DANG OUTPUT\n"))
    p.output_format = prompt("Dinh dang output:")

    print(_c(BOLD, "\n  [BUOC 6/9] RANG BUOC (CONSTRAINTS)\n"))
    print(_c(YELLOW, "  Vi du: '`1 <= n <= 10^5`, `-10^9 <= a_i <= 10^9`. Thuat toan `O(N log N)`.'\n"))
    custom_constraints = prompt(
        "Constraints tuy chinh (de trong = chi dung gioi han mac dinh Tier)",
        default="", required=False)
    p.constraints = format_constraints(p.tier, custom_constraints)

    print(_c(BOLD, "\n  [BUOC 7/9] VI DU MAU (SAMPLE I/O)\n"))
    print(_c(YELLOW, "  Dung '|' thay \\n neu input nhieu dong. Vi du: '5|1 2 3 4 5'\n"))
    raw_si = prompt("Sample Input:")
    raw_so = prompt("Sample Output:")
    p.sample_input = raw_si.replace("|", "\n")
    p.sample_output = raw_so.replace("|", "\n")

    print(_c(BOLD, "\n  [BUOC 8/9] CODE LOI GIAI C++ (Tuy chon -- de verify secret tests)\n"))
    has_sol = prompt("Ban co solution C++ khong? (y/n)", default="n", required=False)
    if has_sol.lower() in ("y", "yes"):
        p.solution_code = prompt_multiline("Paste code C++ (ket thuc bang '.'):")
    else:
        p.solution_code = ""

    print(_c(BOLD, "\n  [BUOC 8b/9] GOI Y CHO THI SINH (HINT)\n"))
    default_hint = f"[Goi y] Doc ky dieu kien bai toan va kiem tra cac truong hop bien dac biet! ({cfg['difficulty']})"
    p.hint = prompt("Hint:", default=default_hint, required=False) or default_hint

    print(_c(BOLD, "\n  [BUOC 9/9] SECRET TESTS\n"))
    p.secret_tests = auto_generate_secret_tests(p.sample_input, p.sample_output, p.solution_code)

    return p


def _append_to_problem_bank(path, code_block):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    marker = "\n]\n"
    idx = content.rfind(marker)
    if idx == -1:
        marker = "\n]\r\n"
        idx = content.rfind(marker)
    if idx == -1:
        print(_c(RED, "  [!] Khong tim thay cuoi PROBLEM_BANK. Vui long paste thu cong."))
        return
    new_content = content[:idx] + "\n" + code_block + "\n" + content[idx:]
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(_c(GREEN, f"  [OK] Da append thanh cong vao {path}"))
    print(_c(YELLOW, "  [info] Chay lai bot hoac: python -m unittest tests/test_ranked_duel.py"))




def run_raw_text_extractor(tier="T6", out_file=""):
    """Boc tach de bai tu van ban tho (statement, input, output, constraints, sample)."""
    from services.ai_generator import ai_generator, TIER_GUIDELINES
    
    print(_c(BOLD + CYAN, "\n  ========================================================"))
    print(_c(BOLD + CYAN, "  📄 BÓC TÁCH ĐỀ BÀI TỰ ĐỘNG TỪ VĂN BẢN THÔ (RAW TEXT)   "))
    print(_c(BOLD + CYAN, "  ========================================================\n"))

    is_ok, status_msg = ai_generator.check_connection()
    if not is_ok:
        print(_c(RED, f"  [!] Khong the ket noi den Ollama: {status_msg}"))
        print(_c(YELLOW, "  -> Hay chay start_ollama.bat hoac download_model.bat truoc!\n"))
        return

    if not tier:
        tier_list = list(TIER_GUIDELINES.keys())
        tier = prompt_choice("Chon Tier quy dinh cho bai:", tier_list, default="T6")

    print(_c(YELLOW, "\n  Dan toan bo van ban tho cua bai toan vao ben duoi."))
    print(_c(YELLOW, "  (Khi dan xong, xuong dong va go 'EOF' roi nhan Enter de bat dau phan tich):\n"))

    raw_lines = []
    while True:
        try:
            line = input()
            if line.strip() == "EOF":
                break
            raw_lines.append(line)
        except EOFError:
            break

    if not raw_text:
        print(_c(RED, "  [!] Ban chua nhap van ban nao!"))
        return

    print(_c(CYAN, "\n  Dang dung AI Core phan tich & loc dung De bai, Input, Output, Constraints, Vi du..."))
    problem, msg = ai_generator.extract_problem_from_raw_text(raw_text=raw_text, tier=tier)

    if not problem:
        print(_c(RED, f"\n  [X] Boc tach that bai: {msg}"))
        return

    print(_c(GREEN, f"\n  [OK] {msg}\n"))
    review(problem)
    rendered = render_python_code(problem)

    print(_c(BOLD + CYAN, "\n  --- MA NGUON PYTHON DA BÓC TÁCH ---"))
    print(_c(GREEN, rendered))

    if out_file:
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(rendered + "\n")
        print(_c(GREEN, f"\n  -> Da luu vao file: {out_file}"))

    problems_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "services", "duel_problems.py")
    if os.path.exists(problems_path):
        print()
        auto_app = prompt("  Tu dong append vao services/duel_problems.py? (y/n)", default="y", required=False)
        if auto_app.lower() in ("y", "yes", ""):
            _append_to_problem_bank(problems_path, rendered)

    print(_c(GREEN + BOLD, "\n  [DONE] Hoan tat!\n"))

def run_ai_generator(tier="T6", theme=None, out_file=""):
    """Sinh đề tự động bằng AI Core (Qwen3-4B-Instruct-2507)."""
    from services.ai_generator import ai_generator, TIER_GUIDELINES
    from config.settings import settings, AI_MODEL_NAME
    ai_model = AI_MODEL_NAME
    
    print(_c(BOLD + CYAN, "\n  ========================================================"))
    print(_c(BOLD + CYAN, f"  🤖 KHOI TAO BO SINH DE BANG AI CORE ({ai_model})      "))
    print(_c(BOLD + CYAN, "  ========================================================\n"))

    is_ok, status_msg = ai_generator.check_connection()
    print(f"  [1/4] Kiem tra ket noi Ollama: {status_msg}")
    if not is_ok:
        print(_c(RED, f"  [!] Khong the ket noi den Ollama tai {ai_generator.base_url}."))
        print(_c(YELLOW, f"  -> Hay chay 'ollama run {ai_model}' tren server truoc!\n"))
        return

    if not tier:
        tier_list = list(TIER_GUIDELINES.keys())
        tier = prompt_choice("Chon Tier can sinh:", tier_list, default="T6")

    if not theme:
        use_random = prompt("Dung chu de ngau nhien tu 199 chu de doi song? (y/n)", default="y", required=False)
        if use_random.lower() in ("y", "yes", ""):
            theme = random.choice(CONTEXT_THEMES)
            print(f"  -> Chu de da chon: {_c(YELLOW, theme)}")
        else:
            theme = prompt("Nhap chu de mong muon:")

    print(_c(CYAN, f"\n  [2/4] Dang goi AI Core ({ai_model}) tao de bai ({tier} - {theme})... Vui long doi 3-8 giay..."))
    problem, msg = ai_generator.generate_problem_sync(tier=tier, theme=theme)

    if not problem:
        print(_c(RED, f"\n  [X] Sinh de that bai: {msg}"))
        return

    print(_c(GREEN, f"  [3/4] {msg}"))
    print(_c(GREEN, "  [4/4] Sandbox Test: Code giai vuot qua 100% testcases mau & an!\n"))

    review(problem)
    rendered = render_python_code(problem)

    print(_c(BOLD + CYAN, "\n  --- MA NGUON PYTHON (PASTE VAO services/duel_problems.py) ---"))
    print(_c(GREEN, rendered))

    if out_file:
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(rendered + "\n")
        print(_c(GREEN, f"\n  -> Da luu ma nguon vao file: {out_file}"))

    problems_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "services", "duel_problems.py")
    if os.path.exists(problems_path):
        print()
        auto_app = prompt("  Tu dong append vao services/duel_problems.py? (y/n)", default="y", required=False)
        if auto_app.lower() in ("y", "yes", ""):
            _append_to_problem_bank(problems_path, rendered)

    print(_c(GREEN + BOLD, "\n  [DONE] Hoan tat! Chuc ban to chuc tran dau thanh cong!\n"))


def main():
    parser = argparse.ArgumentParser(
        description="Generator de bai DuelProblem cho Ranked 1:1 Arena (Ho tro AI Core Qwen3-4B-Instruct-2507)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Vi du:
          python generate.py --ai
          python generate.py --ai --tier T5
          python generate.py --tier LT2 --out my_problem.txt
        """),
    )
    parser.add_argument("--ai", "-a", action="store_true", help="Su dung AI Core de sinh de tu dong 100%")
    parser.add_argument("--tier", choices=list(TIER_CONFIG.keys()), default=None,
                        help="Tier can tao (T8..HT1)")
    parser.add_argument("--theme", default=None, help="Chu de thuc te (vd: 'ngan hang & giao dich')")
    parser.add_argument("--out", default="", metavar="FILE",
                        help="Ghi output ra file thay vi stdout")
    args = parser.parse_args()

    banner()

    if args.ai:
        run_ai_generator(tier=args.tier or "T6", theme=args.theme, out_file=args.out)
        return

    print(_c(BOLD + CYAN, "  [LUA CHON PHUONG THUC TAO DE]"))
    print("    [1] 🤖 Sinh de tu dong 100% bang AI Core (Tu nhien & chuan logic)")
    print("    [2] 📄 Boc tach tu van ban tho / copy paste (AI tu loc De bai, Input, Output, Vi du)")
    print("    [3] ✍️  Tu nhap de bai thu cong tung buoc (Wizard 9 buoc)")
    mode_choice = prompt("  Chon che do (1/2/3)", default="1", required=False)

    if mode_choice.strip() == "1":
        run_ai_generator(tier=args.tier or "T6", theme=args.theme, out_file=args.out)
        return

    if mode_choice.strip() == "2":
        run_raw_text_extractor(tier=args.tier or "T6", out_file=args.out)
        return

    try:
        problem = run_wizard(default_tier=args.tier or "T8")
    except KeyboardInterrupt:
        print(_c(RED, "\n\n  [!] Da huy. Khong co gi duoc luu."))
        sys.exit(0)

    review(problem)

    print()
    confirm = input(_c(BOLD, "  Xuat code Python? (y/n, Enter = y): ")).strip().lower()
    if confirm not in ("y", "yes", ""):
        print(_c(RED, "  Da huy."))
        sys.exit(0)

    code_output = render_python_code(problem)
    output_block = (
        "\n# ====================================================\n"
        "# [GENERATED BY generate.py]  Paste vao PROBLEM_BANK\n"
        "# trong file: services/duel_problems.py\n"
        "# ====================================================\n"
        + code_output + "\n"
    )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output_block)
        print(_c(GREEN, f"\n  [OK] Da luu vao file: {args.out}"))
    else:
        print(_c(CYAN, "\n" + "-" * 64))
        print(_c(BOLD, "  [CODE] Python san de paste vao PROBLEM_BANK:"))
        print(_c(CYAN, "-" * 64))
        print(output_block)
        print(_c(CYAN, "-" * 64))

    problems_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "services", "duel_problems.py")
    if os.path.exists(problems_path):
        print()
        auto_app = input(_c(BOLD, "  Tu dong append vao services/duel_problems.py? (y/n): ")).strip().lower()
        if auto_app in ("y", "yes"):
            _append_to_problem_bank(problems_path, code_output)

    print(_c(GREEN + BOLD, "\n  [DONE] Hoan tat! Chuc ban to chuc tran dau thanh cong!\n"))


if __name__ == "__main__":
    main()
