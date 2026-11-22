"""Constantes + feature engineering partagés entre l'entraînement et l'API.
Une seule fonction build_features => aucune différence entre train et production."""
import numpy as np
import pandas as pd

SIGNALS = ["hr", "spo2", "temp", "hrv", "sys_bp", "dia_bp", "activity"]
VITALS = SIGNALS[:-1]
CALIB = 360          # minutes de calibration (baseline personnelle du patient)
HORIZON = 15         # prédiction : urgence dans les 15 prochaines minutes
CONTEXT = 45         # minutes d'historique nécessaires pour calculer les features
FORECAST_THR = 0.5
STATES = {0: "normal", 1: "surveiller", 2: "urgence"}

NAMES = {
    "hr": ("Fréquence cardiaque", "bpm"), "spo2": ("SpO2", "%"),
    "temp": ("Température", "°C"), "hrv": ("HRV", "ms"),
    "sys_bp": ("Tension systolique", "mmHg"), "dia_bp": ("Tension diastolique", "mmHg"),
}
FLOOR = {"hr": 4, "spo2": 0.6, "temp": 0.12, "hrv": 5, "sys_bp": 6, "dia_bp": 4, "activity": 0.1}


def fit_baseline(df: pd.DataFrame) -> dict:
    """Baseline personnelle = médiane / écart-type sur la période de calibration (repos)."""
    c = df.iloc[:CALIB]
    return {s: {"med": float(c[s].median()), "std": float(max(c[s].std(), FLOOR[s]))} for s in SIGNALS}


def build_features(df: pd.DataFrame, base: dict, age: int) -> pd.DataFrame:
    """Features par minute, calculées uniquement sur le passé (pas de fuite du futur)."""
    d = df[SIGNALS + ["fall"]].astype(float).ffill().bfill()   # capteur coupé -> dernière valeur
    f = pd.DataFrame(index=df.index)
    for s in SIGNALS:
        x = d[s]
        dev = x - base[s]["med"]                                 # écart à SA baseline
        f[f"{s}_dev"] = dev
        f[f"{s}_m5"] = dev.rolling(5, min_periods=1).mean()      # tendance courte
        f[f"{s}_sd5"] = x.rolling(5, min_periods=2).std().fillna(0)   # variabilité
        f[f"{s}_m30"] = dev.rolling(30, min_periods=1).mean()    # tendance longue
        f[f"{s}_slope10"] = (dev - dev.shift(10)).fillna(0)      # pente sur 10 min
    f["fall_15"] = d["fall"].rolling(15, min_periods=1).max()
    f["act_10"] = d["activity"].rolling(10, min_periods=1).mean()
    f["age"] = age
    return f
