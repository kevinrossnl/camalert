"""State snapshots on disk: written before the first change and after every change (write-ahead), so that
`run.py --restore last` can undo a run that crashed. Files: reports/state/<run>.json and reports/state/last.json."""
import json
import os
import time


class Store(object):
    def __init__(self, folder, run_id=None):
        self.folder = os.path.join(folder, "state")
        self.run_id = run_id or time.strftime("%Y%m%d-%H%M%S")
        self.path = os.path.join(self.folder, "%s.json" % self.run_id)
        self.data = {"run": self.run_id, "devices": {}}

    def device(self, name, kind):
        st = {"device": name, "type": kind, "started": int(time.time()), "restored": False, "before": None,
              "changes": {}, "notes": [], "problems": []}
        self.data["devices"][name] = st
        return st

    def save(self):
        os.makedirs(self.folder, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1, sort_keys=True)
        os.replace(tmp, self.path)
        last = os.path.join(self.folder, "last.json")
        with open(last + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"run": self.run_id, "path": os.path.basename(self.path)}, f)
        os.replace(last + ".tmp", last)

    @classmethod
    def load(cls, folder, which="last"):
        base = os.path.join(folder, "state")
        if which == "last":
            with open(os.path.join(base, "last.json"), encoding="utf-8") as f:
                which = json.load(f)["run"]
        store = cls(folder, which)
        with open(store.path, encoding="utf-8") as f:
            store.data = json.load(f)
        return store

    def pending(self):
        """Device states that were changed and not (fully) restored."""
        return [d for d in self.data["devices"].values() if d["before"] is not None and not d["restored"]]
