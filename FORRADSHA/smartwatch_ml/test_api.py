"""Tests de bout en bout : authentification, autorisations, clé d'appareil, anti brute-force, replay live."""
import json
import pandas as pd
from app import app, db, RAW, DB
import seed_demo  # noqa  (recrée la base)
from seed_demo import PW, keys, demo

ok = lambda name, cond: print(("PASS " if cond else "FAIL ") + name) or cond
res = []
def new(): return app.test_client()

a = new()
res += [ok("sans login -> 401 sur /api/patients", a.get("/api/patients").status_code == 401),
        ok("sans login -> 401 sur series", a.get(f"/api/patients/{demo[0]}/series").status_code == 401),
        ok("page d'accueil servie", a.get("/").status_code == 200 and b"Connexion" in a.get("/").data),
        ok("mauvais mot de passe -> 401", a.post("/api/login", json={"username": "dr.salah", "password": "faux"}).status_code == 401)]

d1 = new(); d1.post("/api/login", json={"username": "dr.salah", "password": PW})
ids = [p["id"] for p in d1.get("/api/patients").json]
res += [ok("médecin 1 voit ses 3 patients seulement", ids == demo[:3]),
        ok("médecin 1 -> patient d'un autre médecin = 403", d1.get(f"/api/patients/{demo[3]}/series").status_code == 403),
        ok("médecin 1 -> events d'un autre = 403", d1.get(f"/api/patients/{demo[4]}/events").status_code == 403),
        ok("médecin 1 : alertes filtrées", {x["patient_id"] for x in d1.get("/api/alerts").json} <= set(demo[:3])),
        ok("médecin ne peut pas faire de backup", d1.post("/api/backup").status_code == 403),
        ok("séries accessibles pour son patient", len(d1.get(f"/api/patients/{demo[0]}/series?bucket=30").json["points"]) > 90)]

p = new(); p.post("/api/login", json={"username": demo[0].lower(), "password": PW})
res += [ok("patient ne voit que lui-même", [x["id"] for x in p.get("/api/patients").json] == [demo[0]]),
        ok("patient -> autre patient = 403", p.get(f"/api/patients/{demo[1]}/series").status_code == 403),
        ok("patient ne peut pas créer de patient", p.post("/api/patients", json={"id": "X", "age": 30}).status_code == 403)]

ad = new(); ad.post("/api/login", json={"username": "admin", "password": PW})
res += [ok("admin voit les 6 patients", len(ad.get("/api/patients").json) == 6), ok("admin peut sauvegarder", ad.post("/api/backup").status_code == 200)]

# création d'un patient + compte patient + replay live avec clé d'appareil
r = d1.post("/api/patients", json={"id": "LIVE01", "age": 40, "name": "Live", "password": "short"})
res.append(ok("mot de passe trop court refusé (400)", r.status_code == 400))
r = d1.post("/api/patients", json={"id": "LIVE01", "age": 40, "name": "Live", "password": "bon-mot-de-passe-1"})
res.append(ok("création patient -> clé appareil renvoyée", r.status_code == 201 and "device_key" in r.json))
key = r.json["device_key"]
data = pd.read_csv(DB.parent / "mock_vitals.csv"); g = data[data.patient_id == demo[0]]
rows = json.loads(g[["t"] + RAW].to_json(orient="records"))
res += [ok("ingest sans clé -> 401", new().post("/api/ingest", json={"patient_id": "LIVE01", "readings": rows[:5]}).status_code == 401),
        ok("ingest mauvaise clé -> 401", new().post("/api/ingest", json={"patient_id": "LIVE01", "readings": rows[:5]}, headers={"X-Device-Key": "x"}).status_code == 401),
        ok("clé d'un autre patient refusée", new().post("/api/ingest", json={"patient_id": "LIVE01", "readings": rows[:5]}, headers={"X-Device-Key": keys[demo[0]]}).status_code == 401)]
live = new(); last = None
for i in range(0, len(rows), 15):
    last = live.post("/api/ingest", json={"patient_id": "LIVE01", "readings": rows[i:i + 15]}, headers={"X-Device-Key": key})
res.append(ok("replay live complet accepté", last.status_code == 200 and last.json["status"] == "ok"))
with db() as c:
    m = pd.read_sql_query("SELECT a.action x, b.action y FROM readings a JOIN readings b ON a.t=b.t WHERE a.patient_id=? AND b.patient_id='LIVE01' AND a.action IS NOT NULL AND b.action IS NOT NULL", c, params=(demo[0],))
res.append(ok(f"live == traitement complet ({(m.x == m.y).mean():.4f})", (m.x == m.y).mean() > .999))
pl = new(); res.append(ok("nouveau compte patient peut se connecter", pl.post("/api/login", json={"username": "live01", "password": "bon-mot-de-passe-1"}).status_code == 200))

# anti brute-force
b = new(); codes = [b.post("/api/login", json={"username": "dr.mariem", "password": "x"}).status_code for _ in range(7)]
res.append(ok("brute-force bloqué (429)", codes[-1] == 429 and codes[0] == 401))
a.post("/api/logout"); res.append(ok("logout invalide la session", d1.post("/api/logout").status_code == 200 and d1.get("/api/me").status_code == 401))
print(f"\n{sum(res)}/{len(res)} tests OK")
