"""Does per-move context likelihood add to the shipped game-level features? Same data, same splits."""
import json, sys
import numpy as np, lightgbm as lgb
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from ep_model.review import rating_estimate as RE

D = np.load(sys.argv[1]); pg, mv = D["pg"], D["mv"]
GI, CRC, ELO, OPP, SCORE, NM = pg.T
pid = mv[:, 0].astype(int); ply, loss, cpb, cfrac, init, inc = mv[:, 1:].T
split = CRC % 5
X = np.column_stack([ELO[pid], np.clip(cpb, -1000, 1000), np.clip(cfrac, 0, 1.5), init, inc, np.minimum(ply, 160)])
y = np.searchsorted(np.array([0.005, 0.02, 0.05, 0.10, 0.20]), loss, side="right")
tr = split[pid] >= 2
P = dict(learning_rate=0.08, num_leaves=63, min_data_in_leaf=500, verbose=-1, num_threads=10)
clf = lgb.train({**P, "objective": "multiclass", "num_class": 6}, lgb.Dataset(X[tr], y[tr]), 300)
GRID = np.arange(500, 2851, 100.0)
rng = np.random.RandomState(1)
order = np.argsort(pid, kind="stable"); starts = np.searchsorted(pid[order], np.arange(len(pg) + 1))

def moves_of(i): return order[starts[i]:starts[i + 1]]

def LLfor(ids):
    idx = np.concatenate([moves_of(i) for i in ids]); G = len(GRID); n = len(idx)
    Xg = np.repeat(X[idx], G, axis=0); Xg[:, 0] = np.tile(GRID, n)
    pr = clf.predict(Xg).reshape(n, G, 6)
    ll = np.log(np.clip(pr[np.arange(n), :, y[idx]], 1e-6, 1))
    inv = np.repeat(np.arange(len(ids)), [starts[i + 1] - starts[i] for i in ids])
    LL = np.zeros((len(ids), G)); np.add.at(LL, inv, ll); return LL

def lfeat(LL, a=0.3):
    lp = a * LL; lp -= lp.max(1, keepdims=True); p = np.exp(lp); p /= p.sum(1, keepdims=True); c = np.cumsum(p, 1)
    q = lambda t: GRID[np.argmax(c >= t, axis=1)]
    return np.column_stack([q(0.5), q(0.9) - q(0.1), GRID[np.argmax(LL, 1)], (p * GRID).sum(1)])

def gfeat(ids):
    return np.array([RE.features(list(loss[moves_of(i)]), list(np.abs(cpb[moves_of(i)])), "rapid")[:-1] for i in ids])

cal = np.sort(rng.choice(np.where(split == 1)[0], 12000, replace=False))
test = np.where(split == 0)[0]
by = {}
for i in test: by.setdefault(CRC[i], []).append(i)
multi = [i for v in by.values() if len(v) >= 5 for i in v]
test = np.sort(np.concatenate([multi, rng.choice(np.setdiff1d(test, multi), 8000 - len(multi), replace=False)]))
trn = np.where(split >= 2)[0]
Gc, Gt, Gtr = gfeat(cal), gfeat(test), gfeat(trn)
Lc, Lt = lfeat(LLfor(cal)), lfeat(LLfor(test))
yc, yt, ytr = ELO[cal].astype(float), ELO[test].astype(float), ELO[trn].astype(float)
R = dict(objective="l1", learning_rate=0.05, num_leaves=31, min_data_in_leaf=100, verbose=-1, num_threads=10)

def cv_fit(F, yy, Ft, rounds=400):
    return lgb.train(R, lgb.Dataset(F, yy), rounds).predict(Ft)

def inverse(score_fit, y_fit, score):
    cs, ms = [], []
    for b in range(600, 2700, 100):
        s = (y_fit >= b) & (y_fit < b + 100)
        if s.sum() >= 60: cs.append(b + 50); ms.append(np.median(score_fit[s]))
    ms = np.maximum.accumulate(ms) + np.arange(len(ms)) * 1e-6
    return np.interp(score, ms, cs)

def evaluate(name, Ffit, yfit, Ftest):
    # out-of-fold scores on the fitting set for the inverse table
    k = np.arange(len(yfit)) % 5; oof = np.zeros(len(yfit))
    for f in range(5): oof[k == f] = cv_fit(Ffit[k != f], yfit[k != f], Ffit[k == f])
    st = cv_fit(Ffit, yfit, Ftest)
    pl = inverse(oof, yfit, st)
    avg = np.array([(pl[np.searchsorted(test, v)].mean(), yt[np.searchsorted(test, v)].mean()) for v in by.values() if len(v) >= 5])
    return {"corr_score_rating": round(float(np.corrcoef(st, yt)[0, 1]), 3),
            "regression_MAE": round(float(np.mean(np.abs(st - yt)))),
            "plays_like_MAE": round(float(np.mean(np.abs(pl - yt)))),
            "plays_like_MAE_avg5": round(float(np.mean(np.abs(avg[:, 0] - avg[:, 1])))), "players": len(avg)}

out = {"n_cal": len(cal), "n_test": len(test), "n_train": len(trn),
       "median_baseline_MAE": round(float(np.mean(np.abs(yt - np.median(ytr)))))}
out["game_features_only (shipped recipe), fit on 12k"] = evaluate("C", Gc, yc, Gt)
out["per-move likelihood only, fit on 12k"] = evaluate("B", Lc, yc, Lt)
out["game features + per-move likelihood, fit on 12k"] = evaluate("BC", np.hstack([Gc, Lc]), yc, np.hstack([Gt, Lt]))
out["game_features_only, fit on 72k"] = evaluate("C72", Gtr, ytr, Gt)
print(json.dumps(out, indent=1))
