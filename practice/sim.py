"""Practice simulator (guide ke rules ka saada version). Asli engine nahi hai."""
import random, sys, argparse, time
from vibe_sdk import DIRECTION_DELTAS, Action, Bot
import my_bot

W = H = 12; TURNS = 40; CAP = 4; RES_VALUE = 10
CORNERS = [(0, 0), (11, 0), (0, 11), (11, 11)]
PADS = [(5, 0), (6, 11), (0, 6), (11, 5)]
cheb = lambda a, b, c, d: max(abs(a - c), abs(b - d))

# ---------- time budget ----------
BUDGET_MS = 200  # every buy()/decide() call must finish within this
TIMING = dict(n=0, over=0, worst=0.0, worst_who="-")
def timed(who, fn, *a):
    t0 = time.perf_counter()
    try: return fn(*a)
    finally:
        ms = (time.perf_counter() - t0) * 1000
        TIMING["n"] += 1
        if ms > BUDGET_MS: TIMING["over"] += 1
        if ms > TIMING["worst"]: TIMING["worst"], TIMING["worst_who"] = ms, who

def timing_line():
    return (" decisions: %d | over %d ms: %d | slowest: %.3f ms (%s)"
            % (TIMING["n"], BUDGET_MS, TIMING["over"], TIMING["worst"], TIMING["worst_who"]))

# ---------- opponents ----------
def step_toward(me, tx, ty, walls):
    best = None
    for n, (dx, dy) in DIRECTION_DELTAS.items():
        nx, ny = me["x"] + dx, me["y"] + dy
        if 0 <= nx < W and 0 <= ny < H and (nx, ny) not in walls:
            k = (cheb(nx, ny, tx, ty), n)
            if best is None or k < best: best = k
    return best[1] if best else "EAST"

class Walker(Bot):
    def decide(self, v):
        me = v["self"]; walls = set(v["walls"])
        if v["visible_enemies"]:
            t = v["visible_enemies"][0]
            if cheb(me["x"], me["y"], t["x"], t["y"]) == 1 and me["energy"] >= 5:
                return Action.attack(t["id"])
            return Action.move(step_toward(me, t["x"], t["y"], walls))
        return Action.move(step_toward(me, 6, 6, walls))

class Wanderer(Bot):
    def __init__(self): self.r = random.Random(7)
    def decide(self, v):
        me = v["self"]
        ok = [n for n, (dx, dy) in DIRECTION_DELTAS.items()
              if 0 <= me["x"]+dx < W and 0 <= me["y"]+dy < H]
        return Action.move(self.r.choice(ok))

class Picker(Bot):
    def decide(self, v):
        me = v["self"]; walls = set(v["walls"]); n = len(me["cargo"])
        for r in v["resources"]:
            if (r["x"], r["y"]) == (me["x"], me["y"]) and n < CAP and me["energy"] >= 2:
                return Action.collect(r["id"])
        if n >= CAP or (n and v["turn"] >= 30):
            return Action.move(step_toward(me, me["home"][0], me["home"][1], walls))
        if v["resources"]:
            r = min(v["resources"], key=lambda q: cheb(me["x"], me["y"], q["x"], q["y"]))
            return Action.move(step_toward(me, r["x"], r["y"], walls))
        return Action.move(step_toward(me, 6, 6, walls))

class Hunter(Bot):
    def decide(self, v):
        me = v["self"]; walls = set(v["walls"])
        es = v["visible_enemies"]
        if es:
            t = min(es, key=lambda e: cheb(me["x"], me["y"], e["x"], e["y"]))
            if cheb(me["x"], me["y"], t["x"], t["y"]) == 1 and me["energy"] >= 5:
                return Action.attack(t["id"])
            return Action.move(step_toward(me, t["x"], t["y"], walls))
        return Action.move(step_toward(me, 6, 6, walls))

OPPS = {"walker": Walker, "wanderer": Wanderer, "picker": Picker, "hunter": Hunter}

# ---------- world ----------
def make_walls(rng):
    q = set()
    while len(q) < 6:
        x, y = rng.randint(1, 5), rng.randint(1, 5)
        if (x, y) in [(1,1),(5,5)] or (x, y) in [(5,0)]: continue
        q.add((x, y))
    walls = set()
    for (x, y) in q:
        for _ in range(4):
            walls.add((x, y)); x, y = 11 - y, x
    return walls - set(PADS)

def run(seed, opps, show=False, auto=True):
    rng = random.Random(seed)
    walls = make_walls(rng)
    corners = CORNERS[:]; rng.shuffle(corners)
    names = ["YOU"] + opps
    brains = [my_bot.MyBot()] + [OPPS[o]() for o in opps]
    bots = []
    for i, c in enumerate(corners):
        bots.append(dict(id=i, name=names[i], x=c[0], y=c[1], health=70, energy=50, score=0,
                         cargo=[], alive=True, respawn=0, has_core=False, kills=0,
                         deaths=0, illegal=0, crashes=0, home=c, defend=False))
    # bot 0 = YOU. buy() call
    try: timed("YOU.buy", brains[0].buy, {"credits": 4, "prices": {}, "map": 1, "your_placements": []})
    except Exception: pass
    res = []; rid = [0]
    def spawn(n):
        for _ in range(n):
            for _ in range(50):
                x, y = rng.randint(2, 9), rng.randint(2, 9)
                if (x, y) not in walls and not any(r["x"]==x and r["y"]==y for r in res):
                    res.append(dict(id=f"r{rid[0]}", x=x, y=y, value=RES_VALUE)); rid[0] += 1; break
    spawn(4)
    core = None; planted = None; core_back = None
    log = []
    for t in range(TURNS):
        ot = t >= 32; mult = 2 if ot else 1
        if t == 8: core = dict(x=rng.choice([5, 6]), y=rng.choice([5, 6]), carried_by=None)
        if core_back == t: core = dict(x=5, y=5, carried_by=None); core_back = None
        if t > 0 and t % 6 == 0: spawn(2)
        for b in bots:
            b["energy"] = min(50, b["energy"] + (10 if ot else 5)); b["defend"] = False
            if not b["alive"] and b["respawn"] <= t:
                b.update(alive=True, health=70, energy=50, x=b["home"][0], y=b["home"][1])
        # decisions
        acts = {}
        for b in bots:
            if not b["alive"]: continue
            me = dict(x=b["x"], y=b["y"], energy=b["energy"], health=b["health"],
                      cargo=list(b["cargo"]), has_core=b["has_core"], id=b["id"], home=b["home"])
            ens = [dict(id=o["id"], x=o["x"], y=o["y"], health=o["health"]) for o in bots
                   if o is not b and o["alive"] and cheb(b["x"], b["y"], o["x"], o["y"]) <= 3]
            v = dict(self=me, visible_enemies=ens, board=dict(width=W, height=H),
                     walls=sorted(walls), turn=t, uplink_pads=list(PADS), crates=[],
                     resources=[dict(r) for r in res if cheb(b["x"], b["y"], r["x"], r["y"]) <= 3],
                     core=dict(core) if core else None)
            try: acts[b["id"]] = timed(f"{names[b['id']]}.decide t{t}", brains[b["id"]].decide, v)
            except Exception as e:
                b["crashes"] += 1; acts[b["id"]] = None
                if b["id"] == 0 and b["crashes"] == 1: print("  [CRASH]", repr(e))
        # validate
        valid = {}
        for b in bots:
            a = acts.get(b["id"]); 
            if a is None or not b["alive"]: continue
            ok = False; ty = a.get("type")
            if ty == "move": ok = b["energy"] >= 1 and a.get("dir") in DIRECTION_DELTAS and \
                0 <= b["x"]+DIRECTION_DELTAS[a["dir"]][0] < W and 0 <= b["y"]+DIRECTION_DELTAS[a["dir"]][1] < H
            elif ty == "attack":
                o = next((o for o in bots if o["id"] == a.get("id")), None)
                ok = b["energy"] >= 5 and o is not None and o is not b and o["alive"] and cheb(b["x"],b["y"],o["x"],o["y"]) == 1
            elif ty == "collect":
                here = [r for r in res if (r["x"], r["y"]) == (b["x"], b["y"]) and r["id"] == a.get("id")]
                coreok = a.get("id") == "CORE" and core and core["carried_by"] is None and (core["x"], core["y"]) == (b["x"], b["y"])
                ok = b["energy"] >= 2 and (bool(here) and len(b["cargo"]) < CAP or bool(coreok))
            elif ty == "defend": ok = b["energy"] >= 2
            if ok: valid[b["id"]] = a
            else: b["illegal"] += 1
        cost = dict(move=1, attack=5, collect=2, defend=2)
        for i, a in valid.items(): bots[i]["energy"] -= cost[a["type"]]
        # moves
        occ = {(b["x"], b["y"]) for b in bots if b["alive"]}
        tgt = {}
        for i, a in valid.items():
            if a["type"] == "move":
                dx, dy = DIRECTION_DELTAS[a["dir"]]; nt = (bots[i]["x"]+dx, bots[i]["y"]+dy)
                if nt not in walls and nt not in occ: tgt[i] = nt
        for i, nt in tgt.items():
            if sum(1 for j in tgt.values() if j == nt) == 1:
                bots[i]["x"], bots[i]["y"] = nt
        for i, a in valid.items():
            if a["type"] == "defend": bots[i]["defend"] = True
        # attacks
        dmgby = {}
        for i, a in valid.items():
            if a["type"] == "attack":
                o = bots[a["id"]]; d = rng.randint(16, 24) * (0.5 if o["defend"] else 1)
                o["health"] -= d; dmgby.setdefault(o["id"], []).append(i)
        for o in bots:
            if o["alive"] and o["health"] <= 0:
                o.update(alive=False, respawn=t+3, deaths=o["deaths"]+1)
                for k in dmgby.get(o["id"], []):
                    bots[k]["score"] += 40 * mult; bots[k]["kills"] += 1
                if o["cargo"]:
                    res.append(dict(id=f"r{rid[0]}", x=o["x"], y=o["y"], value=sum(o["cargo"]))); rid[0] += 1
                o["cargo"] = []
                if o["has_core"]: o["has_core"] = False; core["carried_by"] = None
        # collects
        for i, a in valid.items():
            b = bots[i]
            if a["type"] == "collect" and b["alive"]:
                if a["id"] == "CORE": b["has_core"] = True; core["carried_by"] = i
                else:
                    r = next((r for r in res if r["id"] == a["id"]), None)
                    if r: res.remove(r); b["cargo"].append(r["value"])
        if core and core["carried_by"] is not None:
            c = bots[core["carried_by"]]; core["x"], core["y"] = c["x"], c["y"]
        for b in bots:
            if b["alive"] and b["has_core"] and (b["x"], b["y"]) in PADS and not planted:
                planted = dict(by=b["id"], t=t); b["has_core"] = False; core = None
            if b["alive"] and b["cargo"] and (b["x"], b["y"]) == b["home"]:
                b["score"] += sum(b["cargo"]) * mult; b["cargo"] = []
        if planted and t - planted["t"] >= 3:
            bots[planted["by"]]["score"] += 60 * mult; bots[planted["by"]]["cores"] = bots[planted["by"]].get("cores", 0) + 1
            planted = None; core_back = t + 4
        if show: draw(t, bots, walls, res, core)
        if show and not auto: input()
    order = sorted(bots, key=lambda b: (-b["score"], -b["kills"], b["deaths"]))
    return bots, order

def draw(t, bots, walls, res, core):
    print(f"\n=== TURN {t}/40 {'OVERTIME' if t>=32 else ''} ===")
    g = [["." for _ in range(W)] for _ in range(H)]
    for (x, y) in walls: g[y][x] = "\033[90m#\033[0m"
    for (x, y) in PADS: g[y][x] = "\033[96mP\033[0m"
    for r in res: g[r["y"]][r["x"]] = "\033[92mr\033[0m"
    if core: g[core["y"]][core["x"]] = "\033[93mC\033[0m"
    col = ["\033[91m", "\033[94m", "\033[95m", "\033[93m"]
    for b in bots:
        if b["alive"]: g[b["y"]][b["x"]] = f"{col[b['id']]}{'Y' if b['id']==0 else str(b['id'])}\033[0m"
    for row in g: print(" ".join(row))
    for b in bots:
        print(f" {col[b['id']]}{b['name']:<8}\033[0m score={b['score']:<4} hp={int(b['health']):<3} en={b['energy']:<3} cargo={len(b['cargo'])}{'' if b['alive'] else ' DEAD'}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1); ap.add_argument("--seeds", type=int, default=0)
    ap.add_argument("--vs", default="walker,picker,hunter"); ap.add_argument("--show", action="store_true")
    ap.add_argument("--step", action="store_true", help="Enter dabane par agla turn")
    a = ap.parse_args(); opps = a.vs.split(",")
    if a.seeds:
        pts = {1: 3, 2: 2, 3: 1, 4: 0}; tot = 0; ranks = []; ill = 0; cr = 0; kills = 0
        for s in range(a.seeds):
            bots, order = run(s, opps)
            r = [b["id"] for b in order].index(0) + 1; ranks.append(r); tot += pts[r]
            ill += bots[0]["illegal"]; cr += bots[0]["crashes"]; kills += bots[0]["kills"]
        print(f"vs {opps}: {a.seeds} maps")
        print(" ranks:", {k: ranks.count(k) for k in (1, 2, 3, 4)}, "| avg rank %.2f" % (sum(ranks)/len(ranks)))
        print(" rank points: %d / %d | kills %d | ILLEGAL actions: %d | crashes: %d" % (tot, 3*a.seeds, kills, ill, cr))
        print(timing_line())
    else:
        bots, order = run(a.seed, opps, show=a.show, auto=not a.step)
        print("\nFINAL:", [(b["name"], b["score"]) for b in order])
        print("YOU illegal:", bots[0]["illegal"], "crashes:", bots[0]["crashes"])
        print(timing_line())
