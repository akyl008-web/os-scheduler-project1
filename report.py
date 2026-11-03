"""
Генерирует все таблицы и диаграммы Ганта проекта:
    python report.py
Результат: RESULTS.md и SVG-картинки в папке img/ (нужен только Python).
"""

import os

from scheduler import (load, fcfs, sjf, srtf, priority, priority_aging, rr, mlfq,
                       gantt_text, table)

DATA = "data"
IMG = "img"
os.makedirs(IMG, exist_ok=True)
out = []


def p(s=""):
    out.append(s)


COLORS = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc948", "#b07aa1",
          "#ff9da7", "#9c755f", "#bab0ac"]


def svg_gantt(res, fname, title):
    """Диаграмма Ганта в SVG (без внешних библиотек)."""
    segs = res.segments()
    pids = [pr.pid for pr in res.procs]
    end = segs[-1][2]
    L, R, T, row = 40, 15, 30, 18
    k = min(14, 640 / end)
    W, H = L + end * k + R, T + row * len(pids) + 30
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H}" '
         f'font-family="sans-serif" font-size="11"><rect width="100%" height="100%" fill="white"/>',
         f'<text x="{W/2:.0f}" y="18" text-anchor="middle" font-size="13">{title}</text>']
    step = 1 if end <= 30 else 5 if end <= 80 else 10
    for x in range(0, end + 1, step):
        X = L + x * k
        o.append(f'<line x1="{X:.1f}" y1="{T}" x2="{X:.1f}" y2="{H-25}" stroke="#ddd"/>'
                 f'<text x="{X:.1f}" y="{H-12}" text-anchor="middle">{x}</text>')
    for i, pid in enumerate(pids):
        o.append(f'<text x="{L-5}" y="{T + i*row + 13}" text-anchor="end">{pid}</text>')
    for pid, s, e in segs:
        if pid is None:
            continue
        i = pids.index(pid)
        o.append(f'<rect x="{L+s*k:.1f}" y="{T+i*row+2}" width="{(e-s)*k:.1f}" height="{row-4}" '
                 f'fill="{COLORS[i % len(COLORS)]}" stroke="black" stroke-width="0.5"/>')
    o.append("</svg>")
    with open(os.path.join(IMG, fname), "w", encoding="utf-8") as f:
        f.write("\n".join(o))


def svg_lines(xs, series, fname, title):
    """Простой линейный график в SVG: series = [(название, значения, цвет)]."""
    W, H, L, R, T, B = 560, 300, 45, 130, 30, 35
    ymax = max(max(v) for _, v, _ in series)
    ymax = (int(ymax / 20) + 1) * 20
    fx = lambda x: L + (x - xs[0]) / (xs[-1] - xs[0]) * (W - L - R)
    fy = lambda y: T + (1 - y / ymax) * (H - T - B)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'font-family="sans-serif" font-size="11"><rect width="100%" height="100%" fill="white"/>',
         f'<text x="{(W-R+L)/2:.0f}" y="18" text-anchor="middle" font-size="13">{title}</text>']
    for y in range(0, ymax + 1, ymax // 5):
        o.append(f'<line x1="{L}" y1="{fy(y):.1f}" x2="{W-R}" y2="{fy(y):.1f}" stroke="#ddd"/>'
                 f'<text x="{L-5}" y="{fy(y)+4:.1f}" text-anchor="end">{y}</text>')
    for x in xs:
        o.append(f'<text x="{fx(x):.1f}" y="{H-B+15}" text-anchor="middle">{x}</text>')
    o.append(f'<text x="{(W-R+L)/2:.0f}" y="{H-5}" text-anchor="middle">квант q</text>')
    for j, (name, vals, col) in enumerate(series):
        pts = " ".join(f"{fx(x):.1f},{fy(v):.1f}" for x, v in zip(xs, vals))
        o.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2"/>')
        o.append(f'<text x="{W-R+8}" y="{T+15+j*16}" fill="{col}">{name}</text>')
    o.append("</svg>")
    with open(os.path.join(IMG, fname), "w", encoding="utf-8") as f:
        f.write("\n".join(o))


def summary_table(results):
    p("| Алгоритм | ср. ожидание | ср. оборот | ср. отклик | переключений |")
    p("|---|---|---|---|---|")
    for r in results:
        a = r.averages()
        p(f"| {r.name} | {a['waiting']:.2f} | {a['turnaround']:.2f} | "
          f"{a['response']:.2f} | {a['switches']} |")
    p()


def group_table(results, long_pids):
    p("| Алгоритм | ср. ожидание коротких | ср. отклик коротких | ср. оборот длинных | последний длинный завершён в |")
    p("|---|---|---|---|---|")
    for r in results:
        rows = r.per_process()
        short = [v for k, v in rows.items() if k not in long_pids]
        long_ = [v for k, v in rows.items() if k in long_pids]
        p(f"| {r.name} | {sum(x['waiting'] for x in short)/len(short):.2f} | "
          f"{sum(x['response'] for x in short)/len(short):.2f} | "
          f"{sum(x['turnaround'] for x in long_)/len(long_):.2f} | "
          f"{max(x['finish'] for x in long_)} |")
    p()


p("# Результаты (сгенерировано `python report.py`)")
p()

# ---------------- A. jobs.txt
jobs = load(f"{DATA}/jobs.txt")
p("## A. jobs.txt")
p()
resA = [fcfs(jobs), sjf(jobs), rr(jobs, 2)]
for r in resA:
    p(f"### {r.name}")
    p("```")
    p(gantt_text(r))
    p("```")
    p(table(r))
    p()
svg_gantt(resA[0], "jobs_FCFS.svg", "jobs.txt — FCFS")
p("### Сводная таблица jobs.txt")
p()
summary_table(resA)

# ---------------- A3. set1.txt
s1 = load(f"{DATA}/set1.txt")
p("## A3. Самопроверка на set1.txt")
p()
resS = [fcfs(s1), sjf(s1), srtf(s1), priority(s1), rr(s1, 2)]
for r in resS:
    p(f"**{r.name}**")
    p("```")
    p(gantt_text(r))
    p("```")
summary_table(resS)

# ---------------- B. mixed.txt
mixed = load(f"{DATA}/mixed.txt")
LONG = {pr.pid for pr in mixed if pr.burst >= 20}
p("## B1. SRTF и Priority на jobs.txt")
p()
for r in [srtf(jobs), priority(jobs)]:
    p(f"### {r.name}")
    p("```")
    p(gantt_text(r))
    p("```")
    p(table(r))
    p()

p("## B2. Все 5 алгоритмов на mixed.txt")
p()
resB = [fcfs(mixed), sjf(mixed), srtf(mixed), priority(mixed), rr(mixed, 2)]
summary_table(resB)
p(f"Длинные задачи: {', '.join(sorted(LONG, key=lambda x: int(x[1:])))}. Разбивка по группам:")
p()
group_table(resB, LONG)

p("## B3. RR на mixed.txt, квант 1…10")
p()
p("| q | ср. ожидание | ср. оборот | ср. отклик | переключений | ожидание коротких | последний длинный завершён в |")
p("|---|---|---|---|---|---|---|")
qs, waits, resps, sws = [], [], [], []
for q in range(1, 11):
    r = rr(mixed, q)
    a = r.averages()
    rows = r.per_process()
    short = [v for k, v in rows.items() if k not in LONG]
    p(f"| {q} | {a['waiting']:.2f} | {a['turnaround']:.2f} | {a['response']:.2f} | {a['switches']} | "
      f"{sum(x['waiting'] for x in short)/len(short):.2f} | "
      f"{max(v['finish'] for k, v in rows.items() if k in LONG)} |")
    qs.append(q); waits.append(a["waiting"]); resps.append(a["response"]); sws.append(a["switches"])
p()
svg_lines(qs, [("ср. ожидание", waits, "#4e79a7"), ("ср. отклик", resps, "#e15759"),
               ("переключений", sws, "#59a14f")], "rr_quantum.svg", "RR на mixed.txt: влияние кванта")
p("![RR quantum](img/rr_quantum.svg)")
p()

# ---------------- C. starve.txt
st = load(f"{DATA}/starve.txt")
p("## C1–C2. Голодание P1 на starve.txt и старение")
p()
p("| Вариант | P1 старт | P1 финиш | P1 ожидание | ср. ожидание всех | переключений |")
p("|---|---|---|---|---|---|")
variants = [priority(st)] + [priority_aging(st, k) for k in (2, 3, 5, 8)]
for r in variants:
    x = r.per_process()["P1"]
    a = r.averages()
    p(f"| {r.name} | {x['start']} | {x['finish']} | {x['waiting']} | {a['waiting']:.2f} | {a['switches']} |")
p()
svg_gantt(priority(st), "starve_priority.svg", "starve.txt — Priority (голодание P1)")
svg_gantt(priority_aging(st, 3), "starve_aging3.svg", "starve.txt — Priority + старение (шаг 3)")
p("![](img/starve_priority.svg)")
p()
p("![](img/starve_aging3.svg)")
p()

p("## C3. MLFQ на mixed.txt в сравнении с SRTF и RR")
p()
resC = [srtf(mixed), rr(mixed, 2), rr(mixed, 4), mlfq(mixed), mlfq(mixed, boost=50)]
summary_table(resC)
group_table(resC, LONG)
svg_gantt(mlfq(mixed), "mixed_MLFQ.svg", "mixed.txt — MLFQ 2/4/8, boost=20")
p("![](img/mixed_MLFQ.svg)")
p()

with open("RESULTS.md", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\n".join(out))
