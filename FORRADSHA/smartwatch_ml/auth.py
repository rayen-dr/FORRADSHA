"""Authentification : comptes médecin / patient / admin (session), clé d'appareil pour la montre,
contrôle d'accès par patient, limitation des tentatives de connexion."""
import hashlib
import hmac
import os
import secrets
import time
from functools import wraps
from pathlib import Path
from flask import session, request, g
from werkzeug.security import generate_password_hash, check_password_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password_hash TEXT, role TEXT, patient_id TEXT);
CREATE TABLE IF NOT EXISTS doctor_patients(doctor_id INTEGER, patient_id TEXT, PRIMARY KEY(doctor_id, patient_id));
"""
MAX_FAILS, LOCK = 5, 300
_fails, _db = {}, None
_DUMMY = generate_password_hash("dummy-password")      # même temps de calcul si l'utilisateur n'existe pas


def configure(app, db_func):
    global _db
    _db = db_func
    key_file = Path(__file__).parent / "data" / "secret.key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
    app.secret_key = os.environ.get("SECRET_KEY") or key_file.read_text()
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=bool(os.environ.get("HTTPS")), PERMANENT_SESSION_LIFETIME=8 * 3600)
    app.add_url_rule("/api/login", "login", login, methods=["POST"])
    app.add_url_rule("/api/logout", "logout", logout, methods=["POST"])
    app.add_url_rule("/api/me", "me_route", me_route)


def create_user(c, username, password, role, patient_id=None):
    if len(password) < 8:
        raise ValueError("mot de passe trop court (8 caractères minimum)")
    c.execute("INSERT INTO users(username,password_hash,role,patient_id) VALUES(?,?,?,?)",
              (username.strip().lower(), generate_password_hash(password), role, patient_id))
    return c.execute("SELECT id FROM users WHERE username=?", (username.strip().lower(),)).fetchone()[0]


def login():
    j = request.get_json(silent=True) or {}
    u, pw = str(j.get("username", "")).strip().lower(), str(j.get("password", ""))
    key, now = (request.remote_addr, u), time.time()
    _fails[key] = [t for t in _fails.get(key, []) if now - t < LOCK]
    if len(_fails[key]) >= MAX_FAILS:
        return {"error": "trop de tentatives, réessayez dans quelques minutes"}, 429
    with _db() as c:
        r = c.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
    ok = check_password_hash(r["password_hash"] if r else _DUMMY, pw)
    if not (r and ok):
        _fails[key].append(now)
        return {"error": "identifiants invalides"}, 401
    _fails.pop(key, None)
    session.clear(); session["uid"] = r["id"]; session.permanent = True
    return {"username": r["username"], "role": r["role"]}


def logout():
    session.clear()
    return {"ok": True}


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    with _db() as c:
        r = c.execute("SELECT id,username,role,patient_id FROM users WHERE id=?", (uid,)).fetchone()
    return dict(r) if r else None


def me_route():
    u = current_user()
    return (u, 200) if u else ({"error": "non authentifié"}, 401)


def require(*roles):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            u = current_user()
            if not u:
                return {"error": "non authentifié"}, 401
            if roles and u["role"] not in roles:
                return {"error": "accès refusé"}, 403
            g.user = u
            return f(*a, **k)
        return w
    return deco


def accessible(u):
    """None = tous les patients (admin) ; sinon ensemble d'identifiants autorisés."""
    if u["role"] == "admin":
        return None
    if u["role"] == "patient":
        return {u["patient_id"]}
    with _db() as c:
        return {r[0] for r in c.execute("SELECT patient_id FROM doctor_patients WHERE doctor_id=?", (u["id"],))}


def can_access(u, pid):
    ids = accessible(u)
    return ids is None or pid in ids


def new_device_key():
    k = secrets.token_urlsafe(24)
    return k, hashlib.sha256(k.encode()).hexdigest()


def verify_device(c, pid, key):
    r = c.execute("SELECT device_key_hash FROM patients WHERE id=?", (pid,)).fetchone()
    return bool(r and r["device_key_hash"] and hmac.compare_digest(r["device_key_hash"], hashlib.sha256(key.encode()).hexdigest()))
