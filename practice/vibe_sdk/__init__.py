# MOCK SDK: sirf practice ke liye. Asli kit ka vibe_sdk alag hoga.
DIRECTION_DELTAS = {
    "NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0),
    "NORTHEAST": (1, -1), "NORTHWEST": (-1, -1),
    "SOUTHEAST": (1, 1), "SOUTHWEST": (-1, 1),
}

class Action:
    @staticmethod
    def move(d): return {"type": "move", "dir": d}
    @staticmethod
    def attack(i): return {"type": "attack", "id": i}
    @staticmethod
    def collect(i): return {"type": "collect", "id": i}
    @staticmethod
    def defend(): return {"type": "defend"}
    @staticmethod
    def use_item(*a, **k): return {"type": "use_item"}

class Bot:
    def buy(self, shop): return None
    def decide(self, view): raise NotImplementedError
