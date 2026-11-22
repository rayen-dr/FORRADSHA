"""Pipeline d'inférence : mesures -> features -> détection (RF) + prédiction (GB) -> règle de décision.
Même code pour le replay de données mock et pour les vraies données de la montre."""
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from common import *

M = Path(__file__).parent / "models"
_cache = {}
RANK = {"OK": 0, "REST": 1, "CONSULT_DOCTOR": 2, "ALERT_HOSPITAL": 3}
INV = {v: k for k, v in RANK.items()}


def _models():
    if not _cache:
        _cache["det"] = joblib.load(M / "rf_detection.joblib")
        _cache["fc"] = joblib.load(M / "gb_forecast.joblib")
    return _cache["det"], _cache["fc"]


def explain(frow, base) -> str:
    """Raisons lisibles pour le médecin : signaux qui s'écartent de la baseline PERSONNELLE du patient."""
    out = []
    for s in VITALS:
        d = float(frow[f"{s}_m5"]); z = d / base[s]["std"]
        if abs(z) >= 3:
            out.append((abs(z), f"{NAMES[s][0]} {d:+.1f} {NAMES[s][1]} vs baseline"))
    if frow["fall_15"] >= 1:
        out.append((99, "Chute détectée"))
    return " | ".join(t for _, t in sorted(out, reverse=True)[:3])


def analyze_series(df: pd.DataFrame, base: dict, age: int) -> pd.DataFrame:
    """df : mesures minute par minute d'UN patient (>= CONTEXT lignes conseillées)."""
    det, fc = _models()
    f = build_features(df, base, age)
    proba = det["model"].predict_proba(f[det["feats"]])
    st = pd.Series(det["model"].classes_[proba.argmax(1)], index=df.index)       # 0 normal / 1 surveiller / 2 urgence
    forecast = pd.Series(fc["model"].predict_proba(f[fc["feats"]])[:, 1], index=df.index)

    urgent = (st == 2).astype(int).rolling(2, min_periods=2).min().fillna(0).astype(bool)     # 2 min d'affilée (anti-pic capteur)
    persist = (st >= 1).astype(int).rolling(15, min_periods=1).sum() >= 10                    # anormal >= 10 min sur 15
    risk = (forecast >= FORECAST_THR).astype(int).rolling(3, min_periods=3).min().fillna(0).astype(bool)  # risque 3 min d'affilée
    rank = pd.Series(np.select([urgent, persist | risk, st == 1], [3, 2, 1], 0), index=df.index)
    rank = rank.rolling(5, min_periods=1).max().astype(int)                                  # hystérésis : pas de clignotement

    out = pd.DataFrame({"state": st.astype(int), "p_urgence": proba[:, list(det["model"].classes_).index(2)].round(3),
                        "forecast": forecast.round(3), "action": rank.map(INV)}, index=df.index)
    out["reasons"] = ""
    for i in np.where(rank.to_numpy() > 0)[0]:
        out.iloc[i, out.columns.get_loc("reasons")] = explain(f.iloc[i], base)
    return out
