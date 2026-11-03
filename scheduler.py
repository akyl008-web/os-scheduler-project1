"""
Проект 1. Планировщик учебного сервера.

Симулятор алгоритмов планирования процессора:
  FCFS, SJF (невытесняющий), SRTF, Priority (вытесняющий),
  Priority + старение (aging), Round Robin (квант q), MLFQ (3 уровня).

Формат входного файла: "PID arrival burst priority", строки с # пропускаются.
Меньшее число priority = более высокий приоритет.

Соглашения (как в ПР-5):
  * Время дискретное, шаг = 1.
  * Равенство: при одинаковом критерии выигрывает процесс, который уже
    выполняется (не вытесняем зря); затем раньше пришедший; затем тот,
    кто выше в файле.
  * RR: процессы, пришедшие в момент t, встают в очередь РАНЬШЕ процесса,
    у которого в момент t истёк квант.
  * Отклик (response) = момент первого запуска - arrival.
  * Ожидание (waiting) = turnaround - burst.  Оборот (turnaround) = finish - arrival.
  * Переключение контекста = смена одного процесса на ДРУГОЙ процесс
    (первый запуск с пустого процессора и простой не считаются).
"""

from __future__ import annotations

import sys
from collections import deque
from dataclasses import dataclass


# ---------------------------------------------------------------- данные

@dataclass
class Proc:
    pid: str
    arrival: int
    burst: int
    priority: int
    order: int  # позиция в файле — для разрешения равенства


def load(path: str) -> list[Proc]:
    procs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            pid, a, b, p = line.split()[:4]
            procs.append(Proc(pid, int(a), int(b), int(p), len(procs)))
    return procs


# ------------------------------------------------------- метрики по таймлайну

@dataclass
class Result:
    name: str
    timeline: list  # timeline[t] = pid или None (простой) на интервале [t, t+1)
    procs: list

    def segments(self):
        """Сжать таймлайн в отрезки (pid, start, end) для диаграммы Ганта."""
        segs = []
        for t, pid in enumerate(self.timeline):
            if segs and segs[-1][0] == pid:
                segs[-1][2] = t + 1
            else:
                segs.append([pid, t, t + 1])
        return [tuple(s) for s in segs]

    def per_process(self):
        rows = {}
        for p in self.procs:
            ticks = [t for t, x in enumerate(self.timeline) if x == p.pid]
            start, finish = ticks[0], ticks[-1] + 1
            tat = finish - p.arrival
            rows[p.pid] = dict(
                arrival=p.arrival, burst=p.burst, priority=p.priority,
                start=start, finish=finish,
                waiting=tat - p.burst, turnaround=tat, response=start - p.arrival,
            )
        return rows

    def switches(self):
        cnt, prev = 0, None
        for pid in self.timeline:
            if pid is None:
                continue
            if prev is not None and pid != prev:
                cnt += 1
            prev = pid
        return cnt

    def averages(self):
        rows = self.per_process().values()
        n = len(rows)
        return dict(
            waiting=sum(r["waiting"] for r in rows) / n,
            turnaround=sum(r["turnaround"] for r in rows) / n,
            response=sum(r["response"] for r in rows) / n,
            switches=self.switches(),
        )


# ------------------------------------------------- общий потиковый движок

def _simulate(procs, pick, name, preemptive):
    """
    pick(ready, current, t, state) -> Proc  — выбрать процесс из ready.
    Для невытесняющих алгоритмов pick вызывается только когда CPU свободен.
    """
    remaining = {p.pid: p.burst for p in procs}
    state = {"remaining": remaining, "waited": {p.pid: 0 for p in procs}}
    timeline, current, t = [], None, 0
    done = 0
    while done < len(procs):
        ready = [p for p in procs if p.arrival <= t and remaining[p.pid] > 0]
        if current is None or preemptive:
            current = pick(ready, current, t, state) if ready else None
        timeline.append(current.pid if current else None)
        for p in ready:  # для старения: сколько ждал в очереди
            if p is not current:
                state["waited"][p.pid] += 1
        if current:
            remaining[current.pid] -= 1
            if remaining[current.pid] == 0:
                done += 1
                current = None
        t += 1
    return Result(name, timeline, procs)


def _tie(p, current):
    """Ключ равенства: текущий процесс первый, затем arrival, затем порядок в файле."""
    return (0 if p is current else 1, p.arrival, p.order)


def fcfs(procs):
    return _simulate(procs, lambda r, c, t, s: min(r, key=lambda p: (p.arrival, p.order)),
                     "FCFS", preemptive=False)


def sjf(procs):
    return _simulate(procs, lambda r, c, t, s: min(r, key=lambda p: (p.burst, p.arrival, p.order)),
                     "SJF", preemptive=False)


def srtf(procs):
    return _simulate(procs, lambda r, c, t, s: min(
        r, key=lambda p: (s["remaining"][p.pid],) + _tie(p, c)), "SRTF", preemptive=True)


def priority(procs):
    return _simulate(procs, lambda r, c, t, s: min(
        r, key=lambda p: (p.priority,) + _tie(p, c)), "Priority", preemptive=True)


def priority_aging(procs, step=3):
    """Старение: за каждые `step` единиц, проведённых в очереди готовых,
    эффективный приоритет улучшается на 1 (но не лучше 0).
    Накопленное ожидание не сбрасывается — иначе P1 стартует и тут же
    снова вытесняется, а завершается так же поздно."""
    def eff(p, s):
        return max(0, p.priority - s["waited"][p.pid] // step)
    return _simulate(procs, lambda r, c, t, s: min(
        r, key=lambda p: (eff(p, s),) + _tie(p, c)),
        f"Priority+aging({step})", preemptive=True)


def rr(procs, q=2):
    remaining = {p.pid: p.burst for p in procs}
    by_arrival = sorted(procs, key=lambda p: (p.arrival, p.order))
    queue, timeline = deque(), []
    current, used, i, t, done = None, 0, 0, 0, 0
    while done < len(procs):
        while i < len(by_arrival) and by_arrival[i].arrival == t:  # 1) новые
            queue.append(by_arrival[i]); i += 1
        if current is not None and used == q:                        # 2) истёк квант
            queue.append(current); current = None
        if current is None and queue:                                # 3) выбор
            current, used = queue.popleft(), 0
        timeline.append(current.pid if current else None)
        if current:
            remaining[current.pid] -= 1
            used += 1
            if remaining[current.pid] == 0:
                done += 1; current = None
        t += 1
    return Result(f"RR q={q}", timeline, procs)


def mlfq(procs, quanta=(2, 4, 8), boost=20):
    """
    3 уровня, квант растёт: 2 -> 4 -> 8.
    * Новый процесс попадает на уровень 0.
    * Использовал квант целиком -> понижение на уровень ниже.
    * Процесс более высокого уровня вытесняет процесс нижнего уровня
      (вытесненный встаёт в хвост своего уровня).
    * Каждые `boost` единиц времени все процессы поднимаются на уровень 0.
    """
    remaining = {p.pid: p.burst for p in procs}
    by_arrival = sorted(procs, key=lambda p: (p.arrival, p.order))
    queues = [deque() for _ in quanta]
    level = {}
    timeline = []
    current, used, i, t, done = None, 0, 0, 0, 0
    while done < len(procs):
        if boost and t > 0 and t % boost == 0:          # периодический boost
            for lv in range(1, len(queues)):
                while queues[lv]:
                    p = queues[lv].popleft(); level[p.pid] = 0; queues[0].append(p)
            if current is not None and level[current.pid] != 0:
                level[current.pid], used = 0, 0
        while i < len(by_arrival) and by_arrival[i].arrival == t:
            p = by_arrival[i]; level[p.pid] = 0; queues[0].append(p); i += 1
        if current is not None:
            lv = level[current.pid]
            if used == quanta[lv]:                      # квант исчерпан -> понижение
                level[current.pid] = min(lv + 1, len(queues) - 1)
                queues[level[current.pid]].append(current); current = None
            elif any(queues[k] for k in range(lv)):     # пришёл кто-то выше
                queues[lv].append(current); current = None
        if current is None:
            for qd in queues:
                if qd:
                    current, used = qd.popleft(), 0
                    break
        timeline.append(current.pid if current else None)
        if current:
            remaining[current.pid] -= 1; used += 1
            if remaining[current.pid] == 0:
                done += 1; current = None
        t += 1
    return Result(f"MLFQ {'/'.join(map(str, quanta))} boost={boost}", timeline, procs)


# ------------------------------------------------------------------ вывод

def gantt_text(res: Result) -> str:
    segs = res.segments()
    top = "|" + "|".join(f" {pid or 'idle'} ".center(max(5, (e - s) * 2)) for pid, s, e in segs) + "|"
    marks = "0"
    for pid, s, e in segs:
        w = max(5, (e - s) * 2) + 1
        marks += str(e).rjust(w)
    return top + "\n" + marks


def table(res: Result) -> str:
    rows = res.per_process()
    out = ["| PID | arrival | burst | prio | старт | финиш | ожидание | оборот | отклик |",
           "|---|---|---|---|---|---|---|---|---|"]
    for pid, r in rows.items():
        out.append(f"| {pid} | {r['arrival']} | {r['burst']} | {r['priority']} | {r['start']} | "
                   f"{r['finish']} | {r['waiting']} | {r['turnaround']} | {r['response']} |")
    a = res.averages()
    out.append(f"| **среднее** | | | | | | **{a['waiting']:.2f}** | **{a['turnaround']:.2f}** | "
               f"**{a['response']:.2f}** |")
    return "\n".join(out)


ALGOS = {
    "fcfs": fcfs, "sjf": sjf, "srtf": srtf, "priority": priority,
    "rr": rr, "aging": priority_aging, "mlfq": mlfq,
}

if __name__ == "__main__":
    # Пример:  python scheduler.py data/jobs.txt rr 2
    if len(sys.argv) < 3:
        print("usage: python scheduler.py <file> <fcfs|sjf|srtf|priority|rr|aging|mlfq> [q]")
        sys.exit(1)
    ps = load(sys.argv[1])
    algo = ALGOS[sys.argv[2]]
    res = algo(ps, int(sys.argv[3])) if len(sys.argv) > 3 else algo(ps)
    print(res.name)
    print(gantt_text(res))
    print(table(res))
    print("переключений:", res.switches())
