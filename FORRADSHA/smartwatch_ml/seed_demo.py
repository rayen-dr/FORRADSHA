"""Charge 6 patients de TEST (jamais vus à l'entraînement) + comptes de démo + clés d'appareil.
Comptes de DÉMO uniquement : à remplacer en production."""
import json, os
import pandas as pd
from app import db, init_db, insert_raw, process_full, RAW, DB
import auth
from common import fit_baseline

PW = os.environ.get("DEMO_PASSWORD", "demo-1234-Change!")
if DB.exists():
    DB.unlink()
init_db()
data = pd.read_csv(DB.parent / "mock_vitals.csv")
ages = pd.read_csv(DB.parent / "patients.csv").set_index("patient_id")["age"].to_dict()
demo = json.loads((DB.parent.parent / "reports" / "metrics.json").read_text())["test_patients"][:6]
keys = {}
with db() as c:
    auth.create_user(c, "admin", PW, "admin")
    docs = {"dr.salah": auth.create_user(c, "dr.salah", PW, "doctor"), "dr.mariem": auth.create_user(c, "dr.mariem", PW, "doctor")}
    for i, pid in enumerate(demo):
        key, kh = auth.new_device_key(); keys[pid] = key
        c.execute("INSERT INTO patients(id,name,age,lat,lon,created,device_key_hash) VALUES(?,?,?,?,?,datetime('now'),?)",
                  (pid, f"Patient {pid}", ages[pid], 34.74, 10.76, kh))
        c.execute("INSERT INTO doctor_patients VALUES(?,?)", (docs["dr.salah" if i < 3 else "dr.mariem"], pid))
        g = data[data.patient_id == pid]
        insert_raw(c, pid, json.loads(g[["t"] + RAW].to_json(orient="records")))
        c.execute("UPDATE patients SET baseline=? WHERE id=?", (json.dumps(fit_baseline(g.reset_index(drop=True))), pid))
        process_full(c, pid, c.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone())
    auth.create_user(c, demo[0].lower(), PW, "patient", demo[0])
(DB.parent / "demo_device_keys.json").write_text(json.dumps(keys, indent=1))
print("seed OK", demo, "| comptes : admin, dr.salah (3 premiers), dr.mariem (3 derniers),", demo[0].lower(), "(patient)")
