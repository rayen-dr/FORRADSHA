"""Génère des données MOCK réalistes : rythme circadien, activité (marche/sport),
bruit capteurs, coupures, et 5 scénarios pathologiques avec sévérité progressive.
Le sport fait monter la FC mais reste NORMAL (c'est le piège classique des seuils fixes)."""
import numpy as np
import pandas as pd
from pathlib import Path
from common import CALIB

N_PATIENTS, DAYS, SEED = 40, 2, 42
EVENTS = ["fever", "tachy", "hypoxia", "hypertension", "fall"]
PROBS = [0.20, 0.25, 0.20, 0.20, 0.15]
DUR = {"fever": (180, 480), "tachy": (20, 90), "hypoxia": (30, 150), "hypertension": (60, 240)}


def ar(T, sd, rng, phi=0.9):
    x = np.zeros(T)
    e = rng.normal(0, sd * np.sqrt(1 - phi ** 2), T)
    for i in range(1, T):
        x[i] = phi * x[i - 1] + e[i]
    return x


def profile(n, peak):
    up, dn = max(int(n * .3), 1), max(int(n * .3), 1)
    mid = max(n - up - dn, 0)
    return (peak * np.concatenate([np.linspace(.05, 1, up), np.ones(mid), np.linspace(1, .05, dn)]))[:n]


def label_from_sev(s):
    return np.where(s >= .65, 2, np.where(s >= .3, 1, 0))


def awake_start(T, dur, asleep, rng, lo):
    for _ in range(50):
        s = int(rng.integers(lo, T - dur - 5))
        if asleep[s:s + dur].mean() < .2:
            return s
    return lo


def simulate_patient(pid, rng):
    T = DAYS * 1440
    age = int(rng.integers(20, 80))
    b = dict(hr=rng.normal(68 + (age - 45) * .05, 6), spo2=float(np.clip(rng.normal(97.5, .7), 95.5, 99)),
             temp=rng.normal(36.7, .18), hrv=float(np.clip(rng.normal(55 - (age - 45) * .4, 10), 20, 90)),
             sys=rng.normal(115 + (age - 45) * .4, 8), dia=rng.normal(75 + (age - 45) * .15, 5))
    mod = (480 + np.arange(T)) % 1440            # le suivi démarre à 08:00
    asleep = ((mod < 420) | (mod >= 1380)).astype(float)

    act = np.where(asleep > 0, .02, .10) + np.abs(rng.normal(0, .03, T))
    is_ex = np.zeros(T, bool)
    for _ in range(DAYS):
        d = int(rng.integers(35, 60)); s = awake_start(T, d, asleep, rng, CALIB + 30)
        act[s:s + d] = rng.uniform(.7, 1.0); is_ex[s:s + d] = True
        for _ in range(3):
            d = int(rng.integers(10, 25)); s = awake_start(T, d, asleep, rng, CALIB + 30)
            if not is_ex[s:s + d].any():
                act[s:s + d] = rng.uniform(.35, .5)
    act = np.convolve(act, np.ones(3) / 3, "same")
    a = act - .10

    hr = b["hr"] + 80 * a - 10 * asleep + ar(T, 3, rng)
    hrv = b["hrv"] + 12 * asleep - 30 * a + ar(T, 4, rng)
    sys_ = b["sys"] + 30 * a - 8 * asleep + ar(T, 3, rng)
    dia = b["dia"] + 8 * a - 5 * asleep + ar(T, 2, rng)
    temp = b["temp"] - .25 * asleep + .25 * a + ar(T, .05, rng)
    spo2 = b["spo2"] - 1.0 * a + ar(T, .3, rng)
    lab, fall = np.zeros(T, int), np.zeros(T, int)

    for _ in range(rng.poisson(1.6 * DAYS)):
        kind = rng.choice(EVENTS, p=PROBS)
        if kind == "fall":
            s0 = int(rng.integers(CALIB + 20, T - 40)); recover = rng.random() < .4
            n = 6 if recover else 16
            fall[s0] = 1; is_ex[s0:s0 + n] = False
            act[s0 + 1:s0 + n] = .01
            hr[s0:s0 + n] = b["hr"] + 20 + rng.normal(0, 2, n); hrv[s0:s0 + n] -= 10
            lab[s0:s0 + n] = np.maximum(lab[s0:s0 + n], 1 if recover else 2)
            continue
        lo, hi = DUR[kind]; n = int(rng.integers(lo, hi)); s0 = int(rng.integers(CALIB + 20, T - n - 1))
        s = profile(n, rng.uniform(.5, 1.0)); sl = slice(s0, s0 + n)
        if kind == "fever":       temp[sl] += 2.0 * s; hr[sl] += 25 * s; hrv[sl] -= 15 * s
        elif kind == "tachy":     hr[sl] += 70 * s; hrv[sl] -= 20 * s
        elif kind == "hypoxia":   spo2[sl] -= 10 * s; hr[sl] += 20 * s
        elif kind == "hypertension": sys_[sl] += 60 * s; dia[sl] += 30 * s; hr[sl] += 10 * s
        lab[sl] = np.maximum(lab[sl], label_from_sev(s))

    # bruit capteur + artefacts (coupures 1 %, pics 0.3 %)
    hr = hr + rng.normal(0, 1.5, T); spo2 = spo2 + rng.normal(0, .3, T); temp = temp + rng.normal(0, .04, T)
    hrv = hrv + rng.normal(0, 2, T); sys_ = sys_ + rng.normal(0, 3, T); dia = dia + rng.normal(0, 2, T)
    hr[rng.random(T) < .003] += rng.choice([-30, 30])
    df = pd.DataFrame(dict(
        patient_id=pid, t=pd.date_range("2026-11-20 08:00", periods=T, freq="min").strftime("%Y-%m-%d %H:%M:%S"),
        hr=np.clip(hr, 35, 220).round(0), spo2=np.clip(spo2, 70, 100).round(1), temp=temp.round(2),
        hrv=np.clip(hrv, 5, 120).round(0), sys_bp=np.clip(sys_, 70, 230).round(0), dia_bp=np.clip(dia, 40, 140).round(0),
        activity=np.clip(act, 0, 1.2).round(3), fall=fall, label=lab, is_exercise=is_ex.astype(int)))
    for c in ["hr", "spo2", "temp", "hrv", "sys_bp", "dia_bp"]:
        df.loc[rng.random(T) < .01, c] = np.nan
    return df, age


if __name__ == "__main__":
    rng = np.random.default_rng(SEED)
    frames, ages = [], []
    for i in range(N_PATIENTS):
        pid = f"P{i + 1:03d}"
        df, age = simulate_patient(pid, rng)
        frames.append(df); ages.append((pid, age))
    data = pd.concat(frames, ignore_index=True)
    out = Path(__file__).parent / "data"
    data.to_csv(out / "mock_vitals.csv", index=False)
    pd.DataFrame(ages, columns=["patient_id", "age"]).to_csv(out / "patients.csv", index=False)
    print(data.shape, "\nrépartition des labels:\n", data.label.value_counts(normalize=True).round(3).to_dict())
