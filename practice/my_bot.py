from vibe_sdk import DIRECTION_DELTAS, Action, Bot

# =====================================================================
# ADAPTER SECTION  (Yahan field names hain. Agar check.py ya play.py
# mein koi key ghalat nikle, SIRF yahan theek karo. Sahi naam
# docs/BOT_SDK_CONTRACT.md mein likhe hain.)
# Jo naam GUESS hain unke saath "GUESS" likha hai.
# =====================================================================
KNOWN_OK = "self/x/y/energy, visible_enemies/id/x/y, board/width/height"  # guide se confirm


def g(d, *keys, default=None):
    """Safe get: pehli key jo mile wohi return karo."""
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def get_turn(view):                       # GUESS
    return g(view, "turn", "turn_number", default=0)


def get_health(e):                        # GUESS
    return g(e, "health", "hp", default=70)


def get_cargo_count(me):                  # GUESS: list, number ya dict ho sakta hai
    c = g(me, "cargo", "hold", default=0)
    if isinstance(c, (list, tuple)):
        return len(c)
    if isinstance(c, dict):
        return int(g(c, "units", "count", default=0))
    try:
        return int(c)
    except Exception:
        return 0


def get_capacity(me):                     # GUESS
    return int(g(me, "cargo_capacity", "hold_size", default=4))


def get_items(view, key):                 # GUESS: resources / crates lists
    v = g(view, key, default=[])
    return v if isinstance(v, (list, tuple)) else []


def get_walls(view):                      # GUESS: [(x,y)] ya [{"x":..,"y":..}]
    out = set()
    for w in g(view, "walls", default=[]) or []:
        if isinstance(w, dict):
            out.add((w.get("x"), w.get("y")))
        else:
            try:
                out.add((w[0], w[1]))
            except Exception:
                pass
    return out


def get_pads(view):                       # GUESS
    pads = g(view, "uplink_pads", "pads", default=[]) or []
    res = []
    for p in pads:
        if isinstance(p, dict):
            res.append((p.get("x"), p.get("y")))
        else:
            try:
                res.append((p[0], p[1]))
            except Exception:
                pass
    return res


def get_core(view):                       # GUESS: dict with x, y ya None
    c = g(view, "core", default=None)
    if isinstance(c, dict) and c.get("x") is not None:
        return c
    return None


def core_is_carried(core):                # id 0 bhi valid id hai, isliye "is not None"
    return g(core, "carried_by", "carrier", default=None) is not None


def holding_item(me):                     # GUESS
    return g(me, "item", "held_item", default=None)


# =====================================================================
# Helper functions
# =====================================================================
def dist(ax, ay, bx, by):
    return max(abs(ax - bx), abs(ay - by))


class MyBot(Bot):
    ABILITY = "DASH"   # v1 mein use nahi hota (safe). Baad mein add karenge.
    ROLE = None

    def buy(self, shop):
        credits = g(shop, "credits", default=0)
        items = []
        if credits >= 4:
            items = ["ARMOR", "KIT_MEDPACK"]   # 2 + 2 = 4 credits
        elif credits >= 2:
            items = ["ARMOR"]
        return {"role": None, "items": items}

    # ---------- movement ----------
    def step(self, me, tx, ty, board, walls, enemies_xy):
        """Target ki taraf ek LEGAL step. Walls aur enemies avoid karta hai."""
        W, H = board["width"], board["height"]
        mx, my = me["x"], me["y"]
        cands = []
        for name, (dx, dy) in DIRECTION_DELTAS.items():
            nx, ny = mx + dx, my + dy
            if not (0 <= nx < W and 0 <= ny < H):
                continue
            if (nx, ny) in walls or (nx, ny) in enemies_xy:
                continue
            cands.append((dist(nx, ny, tx, ty), abs(nx - tx) + abs(ny - ty), name))
        if not cands:
            return None
        cands.sort()
        # Agar bot atak gaya (pichli position wahi), doosra best raasta lo
        if self.stuck >= 2 and len(cands) > 1:
            return cands[1][2]
        return cands[0][2]

    def go(self, me, tx, ty, board, walls, enemies_xy):
        if me["energy"] < 1:
            return None
        d = self.step(me, tx, ty, board, walls, enemies_xy)
        return Action.move(d) if d else None

    # ---------- main brain ----------
    def decide(self, view):
        me = view["self"]
        board = view["board"]
        enemies = view["visible_enemies"] or []
        turn = get_turn(view)
        mx, my = me["x"], me["y"]
        energy = me["energy"]

        # yaaddasht (memory): har map ke pehle turn par reset (corner har map par badalta hai)
        if turn == 0 or not hasattr(self, "home"):
            self.home = (mx, my)       # pehla turn: hum apne base par hain
            self.last = None
            self.stuck = 0
        self.stuck = self.stuck + 1 if self.last == (mx, my) else 0
        self.last = (mx, my)

        walls = get_walls(view)
        enemies_xy = {(e["x"], e["y"]) for e in enemies}
        hp = get_health(me)
        cargo = get_cargo_count(me)
        cap = get_capacity(me)
        overtime = turn >= 32
        cx, cy = board["width"] // 2, board["height"] // 2

        action = self.think(view, me, board, enemies, walls, enemies_xy,
                            turn, hp, cargo, cap, overtime, cx, cy)
        if action is not None:
            return action
        # Aakhri safety: koi bhi legal move
        if energy >= 1:
            for name in DIRECTION_DELTAS:
                dx, dy = DIRECTION_DELTAS[name]
                nx, ny = mx + dx, my + dy
                if 0 <= nx < board["width"] and 0 <= ny < board["height"]:
                    return Action.move(name)
        return Action.defend() if energy >= 2 else Action.move("EAST")

    def think(self, view, me, board, enemies, walls, enemies_xy,
              turn, hp, cargo, cap, overtime, cx, cy):
        mx, my, energy = me["x"], me["y"], me["energy"]
        core = get_core(view)
        resources = get_items(view, "resources")
        crates = get_items(view, "crates")
        item = holding_item(me)

        # 1) Medpack: health kam ho to heal
        if item and "MEDPACK" in str(item).upper() and hp <= 30 and energy >= 4:
            return Action.use_item()

        # 2) Jis cheez par khade ho usay collect karo
        if energy >= 2:
            if core and (core.get("x"), core.get("y")) == (mx, my) \
                    and not core_is_carried(core) \
                    and not g(me, "has_core", "carrying_core", default=False):
                return Action.collect("CORE")
            if cargo < cap:
                for r in resources:
                    if (r.get("x"), r.get("y")) == (mx, my):
                        return Action.collect(r.get("id"))
            for c in crates:
                if (c.get("x"), c.get("y")) == (mx, my):
                    return Action.collect(c.get("id"))

        # 3) Enemy bilkul bagal mein: kill ya bachao
        adj = [e for e in enemies if dist(mx, my, e["x"], e["y"]) == 1]
        if adj and energy >= 5:
            weakest = min(adj, key=lambda e: get_health(e))
            ehp = get_health(weakest)
            if ehp <= 24:                     # ek hit mein kill mumkin
                return Action.attack(weakest["id"])
            # Bagal mein dushman: bhaagna mushkil hai, isliye wapas maaro
            # (sirf tab nahi jab cargo zyada ho aur health kam ho)
            if overtime or cargo < 3 or hp >= ehp:
                return Action.attack(weakest["id"])
        if adj and cargo >= 2 and energy >= 2 and hp < 35:
            return Action.defend()

        # 4) Core carry kar rahe ho? nearest pad par jao
        if g(me, "has_core", "carrying_core", default=False):
            pads = get_pads(view)
            if pads:
                p = min(pads, key=lambda q: dist(mx, my, q[0], q[1]))
                a = self.go(me, p[0], p[1], board, walls, enemies_xy)
                if a:
                    return a

        # 5) Bank: hold bhara ho ya match khatam hone wala ho
        if cargo >= max(cap - 1, 1) or (turn >= 28 and cargo > 0):
            hx, hy = self.home
            if (mx, my) != (hx, hy):
                a = self.go(me, hx, hy, board, walls, enemies_xy)
                if a:
                    return a

        # 6) Core zameen par aur paas hai (<=5 cells): lo
        if core and not core_is_carried(core):
            if dist(mx, my, core["x"], core["y"]) <= 5:
                a = self.go(me, core["x"], core["y"], board, walls, enemies_xy)
                if a:
                    return a

        # 7) Nazdeek resource, phir crate
        if cargo < cap and resources:
            r = min(resources, key=lambda q: dist(mx, my, q["x"], q["y"]))
            a = self.go(me, r["x"], r["y"], board, walls, enemies_xy)
            if a:
                return a
        if crates:
            c = min(crates, key=lambda q: dist(mx, my, q["x"], q["y"]))
            a = self.go(me, c["x"], c["y"], board, walls, enemies_xy)
            if a:
                return a

        # 8) Kuch na ho to center
        return self.go(me, cx, cy, board, walls, enemies_xy)
