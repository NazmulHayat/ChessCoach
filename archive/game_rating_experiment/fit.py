import json, sys, time
import numpy as np, lightgbm as lgb
sys.path.insert(0, "/Users/nazmulhayat/Desktop/Programming/ChessCoach")
from ep_model.phase_d import rating_estimate as RE

D = np.load(sys.argv[1]); pg, mv = D["pg"], D["mv"]
GI, CRC, ELO, OPP, SCORE, NM = pg.T
pid = mv[:, 0].astype(int); ply, loss, cpb, cfrac, init, inc = mv[:, 1:].T
split = CRC % 5  # by player name: 0 = test, 1 = calibration, rest = train
msplit = split[pid]
X = np.column_stack([ELO[pid], np.clip(cpb, -1000, 1000), np.clip(cfrac, 0, 1.5), init, inc, np.minimum(ply, 160)])
NAMES = ["rating", "cp_before", "clock_frac", "init", "inc", "ply"]
EDGES = np.array([0.005, 0.02, 0.05, 0.10, 0.20])
y = np.searchsorted(EDGES, loss, side="right")
tr = msplit >= 2
t0 = time.time()
mono = [0, 0, 0, 0, 0, 0]
P = dict(learning_rate=0.08, num_leaves=63, min_data_in_leaf=500, verbose=-1, num_threads=10)
clf = lgb.train({**P, "objective": "multiclass", "num_class": 6}, lgb.Dataset(X[tr], y[tr]), 300)
reg = lgb.train({**P, "objective": "l2"}, lgb.Dataset(X[tr], loss[tr]), 300)
print("fit s", round(time.time() - t0), "train moves", tr.sum(), file=sys.stderr)

GRID = np.arange(500, 2851, 50.0)
rng = np.random.RandomState(0)

def pick(s, n):
    ids = np.where(split == s)[0]
    return np.sort(rng.choice(ids, min(n, len(ids)), replace=False))

def per_game(ids):
    """log-lik [game, grid] and SSE [game, grid] for player-games ids."""
    sel = np.isin(pid, ids); Xs, ys, ls, ps = X[sel], y[sel], loss[sel], pid[sel]
    w = np.ones(len(ys))  # w=0 for forced moves would need legal-move counts; not in the dump
    G = len(GRID); n = len(ys)
    Xg = np.repeat(Xs, G, axis=0); Xg[:, 0] = np.tile(GRID, n)
    pr = clf.predict(Xg).reshape(n, G, 6)
    ll = np.log(np.clip(pr[np.arange(n), :, ys], 1e-6, 1)) * w[:, None]
    mu = reg.predict(Xg).reshape(n, G)
    se = (ls[:, None] - mu) ** 2 * w[:, None]
    _, inv = np.unique(ps, return_inverse=True)
    LL = np.zeros((len(ids), G)); SE = np.zeros((len(ids), G))
    np.add.at(LL, inv, ll); np.add.at(SE, inv, se)
    return LL, SE

def summarize(LL, alpha):
    lp = alpha * LL; lp -= lp.max(1, keepdims=True); p = np.exp(lp); p /= p.sum(1, keepdims=True)
    c = np.cumsum(p, 1)
    q = lambda a: GRID[np.argmax(c >= a, axis=1)]
    return q(0.5), q(0.1), q(0.9)

cal = pick(1, 4000)
LLc, _ = per_game(cal)
best = None
for a in [1.0, 0.8, 0.6, 0.5, 0.4, 0.3, 0.25, 0.2, 0.15, 0.1]:
    _, lo, hi = summarize(LLc, a)
    cov = np.mean((ELO[cal] >= lo) & (ELO[cal] <= hi))
    print(f"alpha {a}: 80% interval coverage on calibration players {cov:.3f}", file=sys.stderr)
    if best is None or abs(cov - 0.8) < abs(best[1] - 0.8): best = (a, cov)
ALPHA = best[0]

# test: players with >=5 test games (all their games) + random others
test_ids = np.where(split == 0)[0]
cnt = {}
for i in test_ids: cnt.setdefault(CRC[i], []).append(i)
multi = [i for v in cnt.values() if len(v) >= 5 for i in v]
rest = np.setdiff1d(test_ids, multi)
ids = np.sort(np.concatenate([multi, rng.choice(rest, max(0, 6000 - len(multi)), replace=False)]))
LL, SE = per_game(ids)
med, lo, hi = summarize(LL, ALPHA)
A = GRID[np.argmin(SE, 1)]           # plan as written: argmin squared error
mle = GRID[np.argmax(LL, 1)]
truth = ELO[ids].astype(float)

# current shipped model (plays-like, before shrink/cap)
booster, meta = RE._model()
tab = meta["inverse"]["rapid"]
feats = []
for i in ids:
    m = pid == i
    feats.append(RE.features(list(loss[m]), list(np.abs(cpb[m])), "rapid"))
C = np.interp(booster.predict(np.array(feats)), tab["score"], tab["rating"])
Cship = truth + tab["k"] * (C - truth)
base = np.median(ELO[split >= 2])

def report(name, est):
    err = est - truth
    out = {"MAE": round(float(np.mean(np.abs(err)))), "corr": round(float(np.corrcoef(est, truth)[0, 1]), 3)}
    bands = {}
    for b in range(1000, 2400, 200):
        s = (truth >= b) & (truth < b + 200)
        if s.sum() >= 80: bands[f"{b}-{b+200}"] = int(np.median(est[s]))
    out["median_est_by_band"] = bands
    # many games per player: average the estimates
    ok = []
    for v in cnt.values():
        if len(v) >= 5:
            k = np.searchsorted(ids, v); ok.append((np.mean(est[k]), truth[k].mean()))
    ok = np.array(ok); out["MAE_avg_of_5plus_games"] = round(float(np.mean(np.abs(ok[:, 0] - ok[:, 1])))); out["players_5plus"] = len(ok)
    sc = SCORE[ids].astype(float); s_ok = sc >= 0
    out["score_when_est>rating+150"] = round(float(sc[s_ok & (err > 150)].mean()), 3)
    out["score_when_est<rating-150"] = round(float(sc[s_ok & (err < -150)].mean()), 3)
    return out

res = {"n_test_player_games": len(ids), "alpha": ALPHA, "cal_coverage": round(best[1], 3), "median_baseline_MAE": round(float(np.mean(np.abs(truth - base))))}
res["A_plan_least_squares"] = report("A", A)
res["B_likelihood_median"] = report("B", med)
res["B_likelihood_mle"] = report("Bmle", mle)
res["C_current_plays_like"] = report("C", C)
res["C_current_shipped(shrunk to own rating)"] = {"MAE": round(float(np.mean(np.abs(Cship - truth))))}
res["B_test_coverage_80"] = round(float(np.mean((truth >= lo) & (truth <= hi))), 3)
w = hi - lo
res["B_interval_width_median"] = float(np.median(w))
for n0, n1 in ((10, 20), (20, 30), (30, 45), (45, 200)):
    s = (NM[ids] >= n0) & (NM[ids] < n1)
    res[f"B_width_median_{n0}-{n1}_moves"] = float(np.median(w[s]))
    res[f"B_MAE_{n0}-{n1}_moves"] = round(float(np.mean(np.abs(med[s] - truth[s]))))
imp = dict(zip(NAMES, clf.feature_importance("gain").round().tolist()))
res["clf_gain"] = imp
print(json.dumps(res, indent=1))
