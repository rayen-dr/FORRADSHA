"""Entraînement + évaluation honnête : split PAR PATIENT (jamais le même patient en train et test).
Compare : règle à seuils fixes  vs  Régression logistique  vs  Random Forest (détection)
          persistance  vs  Gradient Boosting (prédiction à 15 min)
          Isolation Forest par patient (anomalie vs baseline personnelle)."""
import json
import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier, IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import GroupShuffleSplit, GroupKFold
from sklearn.metrics import (classification_report, confusion_matrix, f1_score, roc_auc_score,
                             average_precision_score, precision_score, recall_score)
from common import *

ROOT = Path(__file__).parent
data = pd.read_csv(ROOT / "data" / "mock_vitals.csv")
ages = pd.read_csv(ROOT / "data" / "patients.csv").set_index("patient_id")["age"].to_dict()

# ---------- features + cibles ----------
Xs, Rs = [], []
for pid, g in data.groupby("patient_id", sort=False):
    g = g.reset_index(drop=True)
    base = fit_baseline(g)
    f = build_features(g, base, ages[pid])
    lab = g["label"].to_numpy()
    fut = pd.Series(lab[::-1]).rolling(HORIZON, min_periods=1).max().to_numpy()[::-1]   # max(label[t..t+14])
    fut = np.r_[fut[1:], 0]                                                              # -> t+1 .. t+15
    f["patient_id"], f["y"], f["y_future"], f["is_ex"] = pid, lab, fut, g["is_exercise"]
    keep = np.arange(len(g))
    keep = (keep >= CALIB) & (keep < len(g) - HORIZON)       # on évalue après calibration
    Xs.append(f[keep]); Rs.append(g[keep])
X, R = pd.concat(Xs, ignore_index=True), pd.concat(Rs, ignore_index=True)
FEATS = [c for c in X.columns if c not in ("patient_id", "y", "y_future", "is_ex")]

gss = GroupShuffleSplit(n_splits=1, test_size=.3, random_state=0)
tr, te = next(gss.split(X, groups=X["patient_id"]))
tr_s = tr[::3]                                              # minutes consécutives très corrélées -> sous-échantillon
test_patients = sorted(X.iloc[te]["patient_id"].unique())
print(f"patients train={X.iloc[tr]['patient_id'].nunique()}  test={len(test_patients)}")
Xtr, ytr = X.iloc[tr_s][FEATS], X.iloc[tr_s]["y"]
Xte, yte = X.iloc[te][FEATS], X.iloc[te]["y"].to_numpy()
ex_te = X.iloc[te]["is_ex"].to_numpy().astype(bool)
Rte = R.iloc[te].reset_index(drop=True)
Fte = X.iloc[te].reset_index(drop=True)


def det_metrics(y, p, ex):
    rep = classification_report(y, p, labels=[0, 1, 2], target_names=list(STATES.values()), output_dict=True, zero_division=0)
    return dict(macro_f1=round(f1_score(y, p, average="macro"), 3),
                recall_urgence=round(rep["urgence"]["recall"], 3), precision_urgence=round(rep["urgence"]["precision"], 3),
                recall_surveiller=round(rep["surveiller"]["recall"], 3),
                fausses_alertes_normal=round(float((p[y == 0] >= 1).mean()), 3),
                fausses_alertes_sport=round(float((p[(y == 0) & ex] >= 1).mean()), 3))


# ---------- 1. DÉTECTION ----------
def threshold_rule(r, f):
    urg = (r.spo2 < 90) | (r.hr > 140) | (r.temp >= 39) | (r.sys_bp >= 180) | ((f.fall_15 == 1) & (f.act_10 < .08))
    surv = (r.hr > 110) | (r.spo2 < 94) | (r.temp >= 38) | (r.sys_bp >= 140)
    return np.where(urg, 2, np.where(surv, 1, 0))


results = {"Seuils fixes": det_metrics(yte, threshold_rule(Rte, Fte), ex_te)}
lr = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=800)).fit(Xtr, ytr)
results["Régression logistique"] = det_metrics(yte, lr.predict(Xte), ex_te)
rf = RandomForestClassifier(n_estimators=150, min_samples_leaf=5, class_weight="balanced_subsample",
                            n_jobs=1, random_state=0).fit(Xtr, ytr)
rf_pred = rf.predict(Xte)
results["Random Forest"] = det_metrics(yte, rf_pred, ex_te)

cv = []
for a, b in GroupKFold(3).split(Xtr, ytr, groups=X.iloc[tr_s]["patient_id"]):
    m = RandomForestClassifier(n_estimators=80, min_samples_leaf=5, class_weight="balanced_subsample", n_jobs=1, random_state=0)
    cv.append(f1_score(ytr.iloc[b], m.fit(Xtr.iloc[a], ytr.iloc[a]).predict(Xtr.iloc[b]), average="macro"))
cv_res = dict(cv_macro_f1_mean=round(float(np.mean(cv)), 3), cv_macro_f1_std=round(float(np.std(cv)), 3))

# ---------- 2. PRÉDICTION (urgence dans les 15 prochaines minutes) ----------
cur_tr = X.iloc[tr_s]["y"] < 2
gb = HistGradientBoostingClassifier(max_depth=5, learning_rate=.08, max_iter=150, class_weight="balanced", random_state=0)
gb.fit(Xtr[cur_tr], (X.iloc[tr_s]["y_future"][cur_tr] == 2).astype(int))
p_fc = gb.predict_proba(Xte)[:, 1]
mask = yte < 2
yt = (X.iloc[te]["y_future"].to_numpy() == 2).astype(int)
base_pred = (rf_pred == 1).astype(int)                      # baseline : "surveiller" => urgence à venir
fc = dict(auc=round(roc_auc_score(yt[mask], p_fc[mask]), 3), avg_precision=round(average_precision_score(yt[mask], p_fc[mask]), 3),
          precision=round(precision_score(yt[mask], p_fc[mask] >= FORECAST_THR, zero_division=0), 3),
          recall=round(recall_score(yt[mask], p_fc[mask] >= FORECAST_THR), 3),
          baseline_precision=round(precision_score(yt[mask], base_pred[mask], zero_division=0), 3),
          baseline_recall=round(recall_score(yt[mask], base_pred[mask]), 3))
# délai d'anticipation par épisode d'urgence
leads, n_ep = [], 0
for pid in test_patients:
    idx = np.where(Fte["patient_id"].to_numpy() == pid)[0]
    y, p = yte[idx], p_fc[idx]
    for i in np.where((y[1:] == 2) & (y[:-1] < 2))[0] + 1:
        n_ep += 1
        w = np.where(p[max(i - HORIZON, 0):i] >= FORECAST_THR)[0]
        if len(w):
            leads.append(min(i, HORIZON) - w[0])
fc.update(episodes_urgence=n_ep, episodes_anticipes=len(leads),
          delai_median_min=float(np.median(leads)) if leads else 0.0)

# ---------- 3. ANOMALIE PERSONNALISÉE (Isolation Forest par patient) ----------
aucs = []
ISO_COLS = [f"{s}_m5" for s in VITALS]
for pid in test_patients:
    g = data[data.patient_id == pid].reset_index(drop=True)
    f = build_features(g, fit_baseline(g), ages[pid])
    iso = IsolationForest(n_estimators=100, random_state=0).fit(f.iloc[:CALIB][ISO_COLS])
    sc = -iso.score_samples(f.iloc[CALIB:][ISO_COLS])
    y_ = (g["label"].iloc[CALIB:] > 0).to_numpy(); ok = g["is_exercise"].iloc[CALIB:].to_numpy() == 0
    if y_[ok].any():
        aucs.append(roc_auc_score(y_[ok], sc[ok]))
iso_res = dict(auc_moyen=round(float(np.mean(aucs)), 3), patients=len(aucs))

# ---------- sauvegarde ----------
joblib.dump(dict(model=rf, feats=FEATS), ROOT / "models" / "rf_detection.joblib")
joblib.dump(dict(model=gb, feats=FEATS), ROOT / "models" / "gb_forecast.joblib")
rep = dict(detection=results, detection_cv=cv_res, prediction=fc, anomalie=iso_res, test_patients=test_patients)
(ROOT / "reports" / "metrics.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False))
pd.DataFrame(results).T.to_csv(ROOT / "reports" / "model_comparison.csv")

cm = confusion_matrix(yte, rf_pred, labels=[0, 1, 2])
fig, ax = plt.subplots(figsize=(4.8, 4.2)); ax.imshow(cm, cmap="Blues")
ax.set_xticks(range(3), STATES.values()); ax.set_yticks(range(3), STATES.values())
ax.set_xlabel("Prédit"); ax.set_ylabel("Réel"); ax.set_title("Random Forest : matrice de confusion (test)")
for i in range(3):
    for j in range(3):
        ax.text(j, i, cm[i, j], ha="center", va="center", color="white" if cm[i, j] > cm.max() / 2 else "black")
fig.tight_layout(); fig.savefig(ROOT / "reports" / "confusion_matrix.png", dpi=150); plt.close(fig)

imp = pd.Series(rf.feature_importances_, index=FEATS).sort_values().tail(12)
fig, ax = plt.subplots(figsize=(6, 4.2)); imp.plot.barh(ax=ax, color="#2a6f97")
ax.set_title("Variables les plus importantes (Random Forest)"); fig.tight_layout()
fig.savefig(ROOT / "reports" / "feature_importance.png", dpi=150); plt.close(fig)

print(json.dumps(rep, indent=2, ensure_ascii=False))
print("top features:", list(imp.index[::-1][:6]))
