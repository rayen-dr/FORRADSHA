"""API web app : réception des mesures -> analyse ML -> stockage SQLite -> dashboard médecin -> alertes -> backup."""
import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path
import pandas as pd
from flask import Flask, request, jsonify, g, send_from_directory
import auth
from common import *
import pipeline

ROOT = Path(__file__).parent
DB = ROOT / "data" / "smartwatch.db"
RAW = ["hr", "spo2", "temp", "hrv", "sys_bp", "dia_bp", "activity", "fall"]
# MOCK : à remplacer par une vraie recherche (ex. Google Places / annuaire des urgences)
HOSPITALS = [("Hôpital A (mock)", 34.745, 10.760), ("Hôpital B (mock)", 34.730, 10.775), ("Hôpital C (mock)", 34.760, 10.740)]

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients(id TEXT PRIMARY KEY, name TEXT, age INTEGER, lat REAL, lon REAL, baseline TEXT, created TEXT, device_key_hash TEXT);
CREATE TABLE IF NOT EXISTS readings(patient_id TEXT, t TEXT, hr REAL, spo2 REAL, temp REAL, hrv REAL, sys_bp REAL, dia_bp REAL,
  activity REAL, fall INTEGER, state INTEGER, forecast REAL, action TEXT, reasons TEXT, PRIMARY KEY(patient_id, t));
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, t_start TEXT, t_end TEXT, action TEXT, reasons TEXT);
CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, t TEXT, kind TEXT, hospital TEXT, payload TEXT, status TEXT);
"""
app = Flask(__name__)
auth.configure(app, lambda: db())


@app.after_request
def secure_headers(r):
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'"
    if request.path.startswith("/api/"):
        r.headers["Cache-Control"] = "no-store"
    return r


@app.get("/")
@app.get("/login")
def index():
    return send_from_directory(ROOT / "static", "index.html")


@app.get("/favicon.ico")
def favicon():
    return "", 204


def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    return c


def init_db():
    with db() as c:
        c.executescript(SCHEMA + auth.SCHEMA)


def nearest_hospital(lat, lon):
    d = lambda h: math.hypot(h[1] - lat, h[2] - lon)
    return min(HOSPITALS, key=d)


def insert_raw(c, pid, rows):
    vals = [(pid, r["t"], *[r.get(k) for k in RAW[:-1]], int(r.get("fall") or 0)) for r in rows]
    c.executemany("INSERT OR IGNORE INTO readings(patient_id,t,hr,spo2,temp,hrv,sys_bp,dia_bp,activity,fall) VALUES(?,?,?,?,?,?,?,?,?,?)", vals)


def apply_results(c, pid, df, out, prev, loc):
    """Écrit les résultats ML + journal des changements d'état (wa9tech sar) + alertes."""
    c.executemany("UPDATE readings SET state=?,forecast=?,action=?,reasons=? WHERE patient_id=? AND t=?",
                  [(int(s), float(f), a, r, pid, t) for s, f, a, r, t in zip(out.state, out.forecast, out.action, out.reasons, df.t)])
    row = c.execute("SELECT id FROM events WHERE patient_id=? AND t_end IS NULL", (pid,)).fetchone()
    open_id, alerts = (row["id"] if row else None), []
    for t, a, r in zip(df.t, out.action, out.reasons):
        if a == prev:
            continue
        if open_id is not None:
            c.execute("UPDATE events SET t_end=? WHERE id=?", (t, open_id)); open_id = None
        if a != "OK":
            open_id = c.execute("INSERT INTO events(patient_id,t_start,action,reasons) VALUES(?,?,?,?)", (pid, t, a, r)).lastrowid
        if a == "ALERT_HOSPITAL":
            h = nearest_hospital(*loc)
            payload = json.dumps({"patient": pid, "time": t, "location": {"lat": loc[0], "lon": loc[1]}, "reasons": r, "hospital": h[0]})
            for kind in ("SONNERIE_MONTRE", "ALERTE_HOPITAL"):          # envoi réel = à brancher (SMS / API urgences)
                c.execute("INSERT INTO alerts(patient_id,t,kind,hospital,payload,status) VALUES(?,?,?,?,?,'mock_sent')", (pid, t, kind, h[0], payload))
            alerts.append(t)
        prev = a
    return alerts


def load_df(c, pid, limit=None):
    q = "SELECT * FROM readings WHERE patient_id=? ORDER BY t"
    if limit:
        q = f"SELECT * FROM (SELECT * FROM readings WHERE patient_id=? ORDER BY t DESC LIMIT {int(limit)}) ORDER BY t"
    return pd.read_sql_query(q, c, params=(pid,))


def process_full(c, pid, p):
    df = load_df(c, pid)
    out = pipeline.analyze_series(df, json.loads(p["baseline"]), p["age"])
    return apply_results(c, pid, df, out, "OK", (p["lat"], p["lon"]))


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/patients")
@auth.require("doctor", "admin")
def create_patient():
    j = request.get_json(silent=True) or {}
    key, key_hash = auth.new_device_key()
    try:
        with db() as c:
            c.execute("INSERT INTO patients(id,name,age,lat,lon,created,device_key_hash) VALUES(?,?,?,?,?,?,?)",
                      (j["id"], j.get("name", j["id"]), j["age"], j.get("lat", 34.74), j.get("lon", 10.76), datetime.now().isoformat(), key_hash))
            if g.user["role"] == "doctor":
                c.execute("INSERT INTO doctor_patients VALUES(?,?)", (g.user["id"], j["id"]))
            if j.get("password"):
                auth.create_user(c, j.get("username", j["id"].lower()), j["password"], "patient", j["id"])
    except sqlite3.IntegrityError:
        return {"error": "patient ou utilisateur déjà existant"}, 409
    except (ValueError, KeyError) as e:
        return {"error": f"données invalides : {e}"}, 400
    return {"ok": True, "device_key": key}, 201      # la clé n'est montrée qu'une seule fois


@app.get("/api/patients")
@auth.require()
def patients():
    ids = auth.accessible(g.user)
    with db() as c:
        rows = c.execute("""SELECT p.id,p.name,p.age,
            (SELECT action FROM readings r WHERE r.patient_id=p.id AND r.action IS NOT NULL ORDER BY t DESC LIMIT 1) AS last_action,
            (SELECT COUNT(*) FROM events e WHERE e.patient_id=p.id AND e.action!='OK') AS n_events,
            (SELECT COUNT(*) FROM alerts a WHERE a.patient_id=p.id AND a.kind='ALERTE_HOPITAL') AS n_alerts
            FROM patients p ORDER BY p.id""").fetchall()
    return jsonify([dict(r) for r in rows if ids is None or r["id"] in ids])


@app.post("/api/ingest")
def ingest():
    """Corps : {"patient_id": "P001", "readings": [{"t": "...", "hr":..,"spo2":..,"temp":..,"hrv":..,"sys_bp":..,"dia_bp":..,"activity":..,"fall":0}]}"""
    j = request.get_json(silent=True) or {}
    pid, rows = j.get("patient_id", ""), j.get("readings") or []
    with db() as c0:                                     # la montre s'authentifie avec sa clé d'appareil
        if not auth.verify_device(c0, pid, request.headers.get("X-Device-Key", "")):
            return {"error": "clé appareil invalide"}, 401
    with db() as c:
        p = c.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
        if not p:
            return {"error": "patient inconnu"}, 404
        insert_raw(c, pid, rows)
        n = c.execute("SELECT COUNT(*) FROM readings WHERE patient_id=?", (pid,)).fetchone()[0]
        if p["baseline"] is None:
            if n < CALIB:
                return {"status": "calibrating", "readings": n, "needed": CALIB}
            base = fit_baseline(load_df(c, pid))
            c.execute("UPDATE patients SET baseline=? WHERE id=?", (json.dumps(base), pid))
            p = c.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
            process_full(c, pid, p)
        else:
            first = min(r["t"] for r in rows)
            prev = c.execute("SELECT action FROM readings WHERE patient_id=? AND t<? AND action IS NOT NULL ORDER BY t DESC LIMIT 1", (pid, first)).fetchone()
            df = load_df(c, pid, limit=CONTEXT + len(rows))
            out = pipeline.analyze_series(df, json.loads(p["baseline"]), p["age"])
            new = df.t.isin([r["t"] for r in rows]).to_numpy()
            apply_results(c, pid, df[new].reset_index(drop=True), out[new].reset_index(drop=True), prev["action"] if prev else "OK",
                          (rows[-1].get("lat", p["lat"]), rows[-1].get("lon", p["lon"])))
        last = c.execute("SELECT t,state,forecast,action,reasons FROM readings WHERE patient_id=? AND action IS NOT NULL ORDER BY t DESC LIMIT 1", (pid,)).fetchone()
    return {"status": "ok", "latest": dict(last) if last else None}


@app.get("/api/patients/<pid>/series")
@auth.require()
def series(pid):
    if not auth.can_access(g.user, pid):
        return {"error": "accès refusé"}, 403
    """Variation des mesures pour le dashboard. ?signals=hr,spo2&bucket=15&from=...&to=..."""
    sig = [s for s in request.args.get("signals", "hr,spo2,temp,hrv,sys_bp,dia_bp,activity").split(",") if s in SIGNALS]
    bucket = int(request.args.get("bucket", 15))
    with db() as c:
        df = pd.read_sql_query("SELECT t," + ",".join(sig) + ",state FROM readings WHERE patient_id=? AND t>=? AND t<=? ORDER BY t", c,
                               params=(pid, request.args.get("from", "0000"), request.args.get("to", "9999")))
        base = c.execute("SELECT baseline FROM patients WHERE id=?", (pid,)).fetchone()
    df["t"] = pd.to_datetime(df["t"])
    agg = df.set_index("t").resample(f"{bucket}min").agg({**{s: "mean" for s in sig}, "state": "max"}).round(2).reset_index()
    agg["t"] = agg["t"].dt.strftime("%Y-%m-%d %H:%M")
    return {"baseline": json.loads(base["baseline"]) if base and base["baseline"] else None, "points": json.loads(agg.to_json(orient="records"))}


@app.get("/api/patients/<pid>/events")
@auth.require()
def events(pid):
    if not auth.can_access(g.user, pid):
        return {"error": "accès refusé"}, 403
    with db() as c:
        rows = c.execute("SELECT t_start,t_end,action,reasons FROM events WHERE patient_id=? ORDER BY t_start", (pid,)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/alerts")
@auth.require()
def alerts():
    ids, pid = auth.accessible(g.user), request.args.get("patient_id")
    with db() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM alerts ORDER BY t DESC LIMIT 500").fetchall()]
    rows = [r for r in rows if (ids is None or r["patient_id"] in ids) and (not pid or r["patient_id"] == pid)]
    return jsonify(rows[:200])


@app.post("/api/backup")
@auth.require("admin")
def backup():
    dst = ROOT / "backups" / f"smartwatch_{datetime.now():%Y%m%d_%H%M%S}.db"
    with db() as src, sqlite3.connect(dst) as out:
        src.backup(out)
    return {"backup": dst.name, "size_kb": round(dst.stat().st_size / 1024)}


if __name__ == "__main__":
    init_db()
    app.run(port=5000, debug=False)
