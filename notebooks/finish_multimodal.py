"""
Finish multimodal analysis: calibration curves + KM + interpretability summary.
Runs the expensive parts only if checkpoints don't exist.
"""
from pathlib import Path
import warnings, random
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as mgridspec
import torch, torch.nn as nn, torch.optim as optim, xgboost as xgb

from sklearn.model_selection import StratifiedKFold, KFold, train_test_split
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.compose import ColumnTransformer

from sksurv.linear_model import CoxnetSurvivalAnalysis
from sksurv.ensemble import RandomSurvivalForest, GradientBoostingSurvivalAnalysis
from sksurv.util import Surv
from sksurv.metrics import concordance_index_censored

from patsy import dmatrix, build_design_matrices
from lifelines import KaplanMeierFitter
from lifelines.statistics import logrank_test, multivariate_logrank_test
from matplotlib.gridspec import GridSpec as _GS

warnings.filterwarnings("ignore")
SEED = 42
np.random.seed(SEED); random.seed(SEED); torch.manual_seed(SEED)

REPO_ROOT  = Path(__file__).resolve().parent.parent
DATA_DIR   = REPO_ROOT / 'dataset'
OUTPUT_DIR = REPO_ROOT / 'results_v2'
CKPT_DIR   = OUTPUT_DIR / 'checkpoints'
CKPT_DIR.mkdir(exist_ok=True, parents=True)
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

print("=" * 70)
print("FINISH MULTI-MODAL SAGAM (Calibration + KM + Final Summary)")
print("=" * 70)

# ─── Helpers ────────────────────────────────────────────────────────────────

class DeepSurv(nn.Module):
    def __init__(self, n):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n, 128), nn.BatchNorm1d(128), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(128, 64), nn.BatchNorm1d(64),  nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(64, 1))
    def forward(self, x): return self.net(x).squeeze(-1)

def cox_loss(r, t, e):
    o = torch.argsort(-t); r, e = r[o], e[o]
    return -(e*(r - torch.logcumsumexp(r, 0))).sum() / (e.sum() + 1e-8)

def train_ds(Xt, yt, Xv, yv, n, ep=300, pat=25):
    net = DeepSurv(n).to(device)
    opt = optim.Adam(net.parameters(), lr=1e-3, weight_decay=1e-4)
    to_t = lambda a: torch.tensor(np.array(a, dtype=np.float32)).to(device)
    Xt_t, Xv_t = to_t(Xt), to_t(Xv)
    yt_t = to_t([e['time'] for e in yt]); yt_e = to_t([e['event'] for e in yt])
    yv_t = to_t([e['time'] for e in yv]); yv_e = to_t([e['event'] for e in yv])
    best, wait, state = np.inf, 0, None
    for _ in range(ep):
        net.train(); opt.zero_grad()
        cox_loss(net(Xt_t), yt_t, yt_e).backward(); opt.step()
        net.eval()
        with torch.no_grad(): vl = cox_loss(net(Xv_t), yv_t, yv_e).item()
        if vl < best - 1e-6:
            best, wait, state = vl, 0, {k: v.cpu().clone() for k, v in net.state_dict().items()}
        else:
            wait += 1
            if wait >= pat: break
    if state: net.load_state_dict(state)
    net.eval(); return net

def ds_pred(net, X):
    with torch.no_grad():
        return net(torch.tensor(np.array(X, dtype=np.float32)).to(device)).cpu().numpy()

XGB_P = dict(objective="survival:cox", eval_metric="cox-nloglik",
             eta=0.05, max_depth=3, subsample=0.8,
             colsample_bytree=0.8, seed=SEED, verbosity=0)

def ci(ev, ti, r): return concordance_index_censored(ev, ti, r)[0]

def coxnet_fit(X, y, a):
    m = CoxnetSurvivalAnalysis(alphas=[a], l1_ratio=0.9, max_iter=100_000, tol=1e-7)
    m.fit(X, y); return m

ALPHA_GRID = [0.001, 0.005, 0.01, 0.05, 0.1, 0.5]

def tune_alpha(Xt, yt, Xv, yv):
    ba, bc = ALPHA_GRID[-1], -1.0
    for a in ALPHA_GRID:
        try:
            c = ci(yv['event'], yv['time'], coxnet_fit(Xt, yt, a).predict(Xv))
            if c > bc: bc, ba = c, a
        except: pass
    return ba

def tune_alpha_on_train(Xt, yt, val_frac=0.2):
    try:
        X2, Xv2, y2, yv2 = train_test_split(Xt, yt, test_size=val_frac,
                                              random_state=SEED, stratify=yt['event'])
    except ValueError:
        X2, Xv2, y2, yv2 = train_test_split(Xt, yt, test_size=val_frac, random_state=SEED)
    return tune_alpha(X2, y2, Xv2, yv2)

def build_splines(meta_df, feats, df_val=4):
    parts, dis, mapping = [], [], {}
    for f in feats:
        sp = dmatrix(f"bs({f}, df={df_val}, degree=3, include_intercept=False)",
                     meta_df, return_type='dataframe')
        sp.columns = [f"{f}_s{i}" for i in range(sp.shape[1])]
        parts.append(sp); dis.append(sp.design_info); mapping[f] = sp.columns.tolist()
    return pd.concat(parts, axis=1), dis, mapping

def apply_splines(meta_df, feats, dis_list):
    return pd.concat([
        pd.DataFrame(build_design_matrices([dis_list[i]], meta_df)[0], index=meta_df.index)
        for i, f in enumerate(feats)
    ], axis=1)

def make_surv(event_arr, time_arr):
    return np.array(list(zip(event_arr.astype(bool), time_arr)),
                    dtype=[('event', bool), ('time', float)])

# ─── Load data ───────────────────────────────────────────────────────────────

def load_cbio(path):
    with open(path) as fh:
        skip = sum(1 for line in fh if line.startswith('#'))
    return pd.read_csv(path, sep='\t', skiprows=skip, low_memory=False)

patient = load_cbio(DATA_DIR / 'data_clinical_patient.txt')
sample  = load_cbio(DATA_DIR / 'data_clinical_sample.txt')
df_clin = patient.merge(sample, on='PATIENT_ID', how='inner')
df_clin['OS_time']  = pd.to_numeric(df_clin['OS_MONTHS'], errors='coerce')
df_clin['OS_event'] = df_clin['OS_STATUS'].str.startswith('1').fillna(False).astype(int)
df_clin = df_clin[df_clin['OS_time'].notna() & (df_clin['OS_time'] > 0)].copy().reset_index(drop=True)

LEAKAGE = ['OS_MONTHS','OS_STATUS','DSS_STATUS','DSS_MONTHS','DFS_STATUS','DFS_MONTHS',
           'PFS_STATUS','PFS_MONTHS','DAYS_LAST_FOLLOWUP','DAYS_TO_BIRTH',
           'DAYS_TO_INITIAL_PATHOLOGIC_DIAGNOSIS','PERSON_NEOPLASM_CANCER_STATUS',
           'NEW_TUMOR_EVENT_AFTER_INITIAL_TREATMENT','RADIATION_THERAPY','PATIENT_ID_y',
           'OTHER_PATIENT_ID','SUBTYPE','CANCER_TYPE','CANCER_TYPE_DETAILED',
           'TUMOR_TYPE','CANCER_TYPE_ACRONYM','ONCOTREE_CODE','TISSUE_SOURCE_SITE',
           'TISSUE_SOURCE_SITE_CODE','SAMPLE_TYPE','SOMATIC_STATUS','ICD_10',
           'ICD_O_3_HISTOLOGY','ICD_O_3_SITE','AJCC_STAGING_EDITION',
           'FORM_COMPLETION_DATE','INFORMED_CONSENT_VERIFIED','IN_PANCANPATHWAYS_FREEZE',
           'HISTORY_NEOADJUVANT_TRTYN','TISSUE_PROSPECTIVE_COLLECTION_INDICATOR',
           'TISSUE_RETROSPECTIVE_COLLECTION_INDICATOR',
           'PRIMARY_LYMPH_NODE_PRESENTATION_ASSESSMENT',
           'TUMOR_TISSUE_SITE','GENETIC_ANCESTRY_LABEL','SAMPLE_ID']

patient_ids = df_clin['PATIENT_ID'].copy()
df_clin.drop(columns=[c for c in LEAKAGE + ['PATIENT_ID'] if c in df_clin.columns],
             inplace=True, errors='ignore')

GENE_PANEL = ['DKK1', 'FAM83A', 'RHOV', 'IRX5', 'SFTA3',
              'CD1B', 'PKP2', 'TNS4', 'LYPD3', 'TFAP2A']
expr_raw = pd.read_csv(DATA_DIR / 'data_mrna_seq_v2_rsem.txt',
                        sep='\t', index_col=0, low_memory=False)
expr_raw = expr_raw.drop(columns=['Entrez_Gene_Id'], errors='ignore')
expr_raw.columns = expr_raw.columns.str[:12]
expr_panel = np.log2(expr_raw.loc[GENE_PANEL].T + 1)
expr_panel.index.name = 'PATIENT_ID'

ALL_FEATS = ['AJCC_PATHOLOGIC_TUMOR_STAGE','PATH_M_STAGE','PATH_N_STAGE','PATH_T_STAGE',
             'AGE','SEX','GRADE','ETHNICITY','RACE','PRIOR_DX','WEIGHT',
             'ANEUPLOIDY_SCORE','MSI_SCORE_MANTIS','MSI_SENSOR_SCORE','TMB_NONSYNONYMOUS',
             'TBL_SCORE','BUFFA_HYPOXIA_SCORE','WINTER_HYPOXIA_SCORE','RAGNUM_HYPOXIA_SCORE']
get_cols = lambda cols: [c for c in cols if c in df_clin.columns]

df_clin['PATIENT_ID_KEY'] = patient_ids.values
df_mm = df_clin.merge(expr_panel, left_on='PATIENT_ID_KEY', right_index=True, how='inner')
df_mm = df_mm.drop(columns=['PATIENT_ID_KEY']).reset_index(drop=True)

clin_feats = get_cols(ALL_FEATS)
expr_feats = [g for g in GENE_PANEL if g in df_mm.columns]
mm_feats   = clin_feats + expr_feats

y_mm = Surv.from_arrays(event=df_mm['OS_event'].values, time=df_mm['OS_time'].values)
print(f"  Dataset: n={len(df_mm)}, events={df_mm['OS_event'].sum()}")

# ─── Checkpoint: run or load nested CVs ─────────────────────────────────────

ckpt_file = CKPT_DIR / 'multimodal_pooled_risks.npz'

if ckpt_file.exists():
    print("\n[CV] Loading checkpointed pooled risks...")
    ckpt = np.load(ckpt_file)
    expr_oof_risk = ckpt['expr_risk']
    clin_risk     = ckpt['clin_risk']
    mm_risk       = ckpt['mm_risk']
    expr_fold_c   = list(ckpt['expr_fold_c'])
    clin_fold_c   = list(ckpt['clin_fold_c'])
    mm_fold_c     = list(ckpt['mm_fold_c'])
    print(f"  Expression-only: C = {np.mean(expr_fold_c):.4f}")
    print(f"  Clinical-only:   C = {np.mean(clin_fold_c):.4f}")
    print(f"  Multi-Modal:     C = {np.mean(mm_fold_c):.4f}")
else:
    print("\n[CV] Running nested CVs (this takes ~30-60 minutes)...")

    def run_sagam_cv(df_use, y_use, feature_cols, expr_only_cols,
                     label="SAGAM", n_outer=5, n_inner=3, use_expr_cox=False):
        outer_kf = StratifiedKFold(n_outer, shuffle=True, random_state=SEED)
        pooled_risk = np.zeros(len(df_use))
        fold_c = []
        META_FEATS = ["RSF", "GBS", "XGB", "DS"] + (["ExprCox"] if use_expr_cox else [])
        n_l = len(META_FEATS)

        for fold_i, (tr_i, te_i) in enumerate(outer_kf.split(np.arange(len(df_use)), y_use['event'])):
            print(f"  [{label}] Fold {fold_i+1}/{n_outer}...", end=' ', flush=True)
            X_tr_raw = df_use[feature_cols].iloc[tr_i]
            X_te_raw = df_use[feature_cols].iloc[te_i]
            y_tr, y_te = y_use[tr_i], y_use[te_i]

            cat_c = X_tr_raw.select_dtypes(['object','category']).columns.tolist()
            num_c = X_tr_raw.select_dtypes(['number','bool']).columns.tolist()
            pre = ColumnTransformer([
                ('cat', OneHotEncoder(drop='first', sparse_output=False, handle_unknown='ignore'), cat_c),
                ('num', SimpleImputer(strategy='median'), num_c),
            ], remainder='drop')
            Xp_tr = pre.fit_transform(X_tr_raw); Xp_te = pre.transform(X_te_raw)
            sc = StandardScaler()
            Xs_tr = sc.fit_transform(Xp_tr); Xs_te = sc.transform(Xp_te)

            if use_expr_cox and expr_only_cols:
                Xe_tr = StandardScaler().fit_transform(df_use[expr_only_cols].iloc[tr_i].values.astype(float))
                Xe_te = StandardScaler().fit_transform(df_use[expr_only_cols].iloc[te_i].values.astype(float))
            else:
                Xe_tr = Xe_te = None

            inn_kf = KFold(n_inner, shuffle=True, random_state=SEED)
            oof = np.zeros((len(tr_i), n_l))
            es_size = max(10, int(0.15 * len(Xs_tr)))
            X_es, y_es = Xs_tr[:es_size], y_tr[:es_size]
            Xs_cv, y_cv = Xs_tr[es_size:], y_tr[es_size:]

            for ii_tr, ii_vl in inn_kf.split(Xs_cv):
                Xi, Xj = Xs_cv[ii_tr], Xs_cv[ii_vl]
                yi, yj = y_cv[ii_tr], y_cv[ii_vl]
                oof_idx = ii_vl + es_size

                rsf_i = RandomSurvivalForest(n_estimators=200, max_features='sqrt',
                                              min_samples_leaf=5, random_state=SEED, n_jobs=-1)
                rsf_i.fit(Xi, yi); oof[oof_idx, 0] = rsf_i.predict(Xj)
                gbs_i = GradientBoostingSurvivalAnalysis(n_estimators=200, learning_rate=0.05,
                                                          max_depth=3, random_state=SEED)
                gbs_i.fit(Xi, yi); oof[oof_idx, 1] = gbs_i.predict(Xj)
                dt = xgb.DMatrix(Xi, label=[e['time'] for e in yi], weight=[e['event'] for e in yi])
                dv = xgb.DMatrix(X_es, label=[e['time'] for e in y_es], weight=[e['event'] for e in y_es])
                xm = xgb.train(XGB_P, dt, num_boost_round=300, evals=[(dv,'v')],
                               early_stopping_rounds=20, verbose_eval=False)
                it = getattr(xm,'best_iteration', xm.num_boosted_rounds())
                oof[oof_idx, 2] = xm.predict(xgb.DMatrix(Xj), iteration_range=(0, it))
                dn = train_ds(Xi, yi, X_es, y_es, Xi.shape[1])
                oof[oof_idx, 3] = ds_pred(dn, Xj)
                if use_expr_cox and Xe_tr is not None:
                    Xe_cv = Xe_tr[es_size:]
                    Xe_i = Xe_cv[ii_tr]; Xe_j = Xe_cv[ii_vl]
                    yi_s = make_surv(yi['event'], yi['time'])
                    a_ec = tune_alpha_on_train(Xe_i, yi_s)
                    oof[oof_idx, 4] = coxnet_fit(Xe_i, yi_s, a_ec).predict(Xe_j)

            oof_meta = oof[es_size:]; y_tr_meta = y_cv
            Xs_f, y_f = Xs_tr[es_size:], y_tr[es_size:]
            rsf_f = RandomSurvivalForest(n_estimators=200, max_features='sqrt',
                                          min_samples_leaf=5, random_state=SEED, n_jobs=-1)
            rsf_f.fit(Xs_f, y_f)
            gbs_f = GradientBoostingSurvivalAnalysis(n_estimators=200, learning_rate=0.05,
                                                      max_depth=3, random_state=SEED)
            gbs_f.fit(Xs_f, y_f)
            xm_f = xgb.train(XGB_P,
                              xgb.DMatrix(Xs_f, label=[e['time'] for e in y_f],
                                           weight=[e['event'] for e in y_f]),
                              num_boost_round=300,
                              evals=[(xgb.DMatrix(X_es, label=[e['time'] for e in y_es],
                                                   weight=[e['event'] for e in y_es]),'v')],
                              early_stopping_rounds=20, verbose_eval=False)
            it_f = getattr(xm_f,'best_iteration', xm_f.num_boosted_rounds())
            dn_f = train_ds(Xs_f, y_f, X_es, y_es, Xs_f.shape[1])
            te_preds = np.column_stack([
                rsf_f.predict(Xs_te), gbs_f.predict(Xs_te),
                xm_f.predict(xgb.DMatrix(Xs_te), iteration_range=(0, it_f)),
                ds_pred(dn_f, Xs_te)
            ])
            if use_expr_cox and Xe_te is not None:
                y_f_s = make_surv(y_f['event'], y_f['time'])
                a_ecf = tune_alpha_on_train(Xe_tr[es_size:], y_f_s)
                ec_f  = coxnet_fit(Xe_tr[es_size:], y_f_s, a_ecf)
                te_preds = np.column_stack([te_preds, ec_f.predict(Xe_te)])

            meta_tr = pd.DataFrame(oof_meta, columns=META_FEATS)
            meta_te = pd.DataFrame(te_preds, columns=META_FEATS)
            for f in META_FEATS:
                mn, mx = meta_tr[f].min(), meta_tr[f].max()
                meta_te[f] = meta_te[f].clip(mn, mx)
            sp_tr, dis, _ = build_splines(meta_tr, META_FEATS)
            sp_te = apply_splines(meta_te, META_FEATS, dis); sp_te.columns = sp_tr.columns
            y_tr_s = make_surv(y_tr_meta['event'], y_tr_meta['time'])
            sp_tv, sp_vl = train_test_split(sp_tr, test_size=0.2, random_state=SEED)
            ym_tv = y_tr_s[sp_tv.index]; ym_vl = y_tr_s[sp_vl.index]
            a_gam = tune_alpha(sp_tv.values, ym_tv, sp_vl.values, ym_vl)
            gam_m = coxnet_fit(sp_tr.values, y_tr_s, a_gam)
            risk_te = gam_m.predict(sp_te.values)
            pooled_risk[te_i] = risk_te
            c_fold = ci(y_te['event'], y_te['time'], risk_te)
            fold_c.append(c_fold)
            print(f"C={c_fold:.4f}")
        return pooled_risk, fold_c

    # Expression-only
    print("\n[A] Expression-only (CoxNet on 10 genes)...")
    outer_kf = StratifiedKFold(5, shuffle=True, random_state=SEED)
    expr_oof_risk = np.zeros(len(df_mm)); expr_fold_c = []
    for fold_i, (tr_i, te_i) in enumerate(outer_kf.split(np.arange(len(df_mm)), y_mm['event'])):
        print(f"  [ExprOnly] Fold {fold_i+1}/5...", end=' ', flush=True)
        Xe_tr_r = df_mm[expr_feats].iloc[tr_i].values.astype(float)
        Xe_te_r = df_mm[expr_feats].iloc[te_i].values.astype(float)
        y_tr, y_te = y_mm[tr_i], y_mm[te_i]
        sc_e = StandardScaler()
        Xe_tr = sc_e.fit_transform(Xe_tr_r); Xe_te = sc_e.transform(Xe_te_r)
        y_tr_s = make_surv(y_tr['event'], y_tr['time'])
        a_e = tune_alpha_on_train(Xe_tr, y_tr_s)
        ec_m = coxnet_fit(Xe_tr, y_tr_s, a_e)
        risk_e = ec_m.predict(Xe_te)
        expr_oof_risk[te_i] = risk_e
        c_e = ci(y_te['event'], y_te['time'], risk_e); expr_fold_c.append(c_e)
        print(f"C={c_e:.4f}")
    print(f"  ExprOnly: C = {np.mean(expr_fold_c):.4f} +/- {np.std(expr_fold_c):.4f}")

    print("\n[B] Clinical-only SAGAM...")
    clin_risk, clin_fold_c = run_sagam_cv(df_mm, y_mm, clin_feats, [], label="Clinical", use_expr_cox=False)
    print(f"  Clinical: C = {np.mean(clin_fold_c):.4f} +/- {np.std(clin_fold_c):.4f}")

    print("\n[C] Multi-Modal SAGAM (5 base learners)...")
    mm_risk, mm_fold_c = run_sagam_cv(df_mm, y_mm, mm_feats, expr_feats, label="MM", use_expr_cox=True)
    print(f"  Multi-Modal: C = {np.mean(mm_fold_c):.4f} +/- {np.std(mm_fold_c):.4f}")

    # Save checkpoint
    np.savez(ckpt_file,
             expr_risk=expr_oof_risk, clin_risk=clin_risk, mm_risk=mm_risk,
             expr_fold_c=expr_fold_c, clin_fold_c=clin_fold_c, mm_fold_c=mm_fold_c)
    print(f"  Checkpoints saved to {ckpt_file}")

# ─── Build results dict ──────────────────────────────────────────────────────

results = {
    'Expression-only': {'pooled_risk': expr_oof_risk, 'fold_c': expr_fold_c,
                        'mean_c': np.mean(expr_fold_c), 'std_c': np.std(expr_fold_c)},
    'Clinical-only':   {'pooled_risk': clin_risk,     'fold_c': clin_fold_c,
                        'mean_c': np.mean(clin_fold_c), 'std_c': np.std(clin_fold_c)},
    'Multi-Modal':     {'pooled_risk': mm_risk,        'fold_c': mm_fold_c,
                        'mean_c': np.mean(mm_fold_c),  'std_c': np.std(mm_fold_c)},
}

print("\n" + "=" * 55)
print("3-WAY COMPARISON SUMMARY")
print("=" * 55)
print(f"{'Model':<25} {'Mean C':>8} {'Std C':>8} {'vs Clinical':>12}")
print("-" * 55)
clin_c = results['Clinical-only']['mean_c']
for name, res in results.items():
    delta = res['mean_c'] - clin_c
    mark  = " [+]" if delta > 0.005 else (" [-]" if delta < -0.005 else "  ~")
    print(f"{name:<25} {res['mean_c']:>8.4f} {res['std_c']:>8.4f} {delta:>+10.4f}{mark}")

# Save comparison CSV
comp_df = pd.DataFrame([
    {'Model': name, 'Mean_C': res['mean_c'], 'Std_C': res['std_c'],
     'Fold_1': res['fold_c'][0], 'Fold_2': res['fold_c'][1],
     'Fold_3': res['fold_c'][2], 'Fold_4': res['fold_c'][3], 'Fold_5': res['fold_c'][4]}
    for name, res in results.items()
])
comp_df.to_csv(OUTPUT_DIR / 'multimodal_comparison.csv', index=False)

# ─── Calibration curves ──────────────────────────────────────────────────────

print("\nGenerating calibration curves...")

ev_cal = df_mm['OS_event'].values.astype(bool)
ti_cal = df_mm['OS_time'].values

def calibration_curve(risk_scores, events, times, eval_time_months,
                       n_bins=5, label='Model', color='steelblue', ax=None):
    """Quintile-based calibration: KM-observed vs risk-rank-predicted."""
    if ax is None:
        _, ax = plt.subplots()
    try:
        bins = pd.qcut(pd.Series(risk_scores), n_bins, labels=False, duplicates='drop')
    except Exception:
        return ax
    bin_km_surv, bin_mean_rank = [], []
    kmf_cal = KaplanMeierFitter()
    for b in sorted(bins.dropna().unique()):
        mask = (bins == b).values
        if mask.sum() < 5: continue
        kmf_cal.fit(times[mask], event_observed=events[mask])
        try:
            km_s = float(kmf_cal.predict(eval_time_months))
        except Exception: km_s = np.nan
        if not np.isnan(km_s):
            bin_km_surv.append(km_s)
            rank = (risk_scores[mask].mean() - risk_scores.min()) / \
                   (risk_scores.max() - risk_scores.min() + 1e-8)
            bin_mean_rank.append(1 - rank)
    if len(bin_km_surv) < 2: return ax
    bk = np.array(bin_km_surv); br = np.array(bin_mean_rank)
    # Sort by predicted rank
    order = np.argsort(br)
    ax.plot(br[order], bk[order], 'o-', color=color, linewidth=2, markersize=7, label=label)
    return ax

time_labels_cal = ['1-Year', '3-Year', '5-Year']
eval_times_cal  = [12.0, 36.0, 60.0]
model_colors_cal = {
    'Clinical-only':   '#2196F3',
    'Expression-only': '#FF5722',
    'Multi-Modal':     '#4CAF50',
}

fig_cal, axes_cal = plt.subplots(1, 3, figsize=(16, 5))
fig_cal.patch.set_facecolor('#FAFAFA')
for j, (t_label, t_val) in enumerate(zip(time_labels_cal, eval_times_cal)):
    ax = axes_cal[j]; ax.set_facecolor('#FAFAFA')
    for name, res in results.items():
        calibration_curve(res['pooled_risk'], ev_cal, ti_cal, t_val,
                          n_bins=5, label=name, color=model_colors_cal.get(name,'grey'), ax=ax)
    ax.plot([0, 1], [0, 1], 'k--', linewidth=1, alpha=0.5, label='Perfect calibration')
    ax.set_xlabel('Predicted survival (by risk rank)', fontsize=12)
    ax.set_ylabel('Observed KM survival', fontsize=12)
    ax.set_title(f'{t_label} Calibration', fontsize=13, fontweight='bold')
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.grid(alpha=0.3, linestyle='--')
    ax.legend(fontsize=9, loc='upper left')

plt.suptitle('Calibration: Predicted (Risk Rank) vs Observed (Kaplan-Meier) Survival\n'
             'Points near the diagonal = well calibrated model',
             fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / 'calibration_curves.png', dpi=300, bbox_inches='tight')
plt.close()
print("  [OK] calibration_curves.png")

# ─── Multi-modal KM ──────────────────────────────────────────────────────────

print("Generating multi-modal KM figure...")

mm_risk_arr = results['Multi-Modal']['pooled_risk']
ev_km = df_mm['OS_event'].values; ti_km = df_mm['OS_time'].values
risk_grp_mm = pd.qcut(mm_risk_arr, q=3, labels=['Low Risk', 'Medium Risk', 'High Risk'])
lr_mm = logrank_test(
    ti_km[risk_grp_mm=='Low Risk'], ti_km[risk_grp_mm=='High Risk'],
    ev_km[risk_grp_mm=='Low Risk'], ev_km[risk_grp_mm=='High Risk'])
sig_mm = ('***' if lr_mm.p_value<0.001 else '**' if lr_mm.p_value<0.01
           else '*' if lr_mm.p_value<0.05 else 'NS')

fig_km = plt.figure(figsize=(12, 10))
gs_km  = _GS(2, 1, figure=fig_km, height_ratios=[4, 1], hspace=0.04)
ax_km  = fig_km.add_subplot(gs_km[0])
ax_km2 = fig_km.add_subplot(gs_km[1], sharex=ax_km)
colors_km = ['#2E7D32', '#F57C00', '#C62828']
kmf_mm = KaplanMeierFitter(); median_s_mm = {}

for i, (grp, color) in enumerate(zip(['Low Risk','Medium Risk','High Risk'], colors_km)):
    mask = (risk_grp_mm == grp)
    kmf_mm.fit(ti_km[mask], ev_km[mask], label=f"{grp} (n={mask.sum()})")
    kmf_mm.plot_survival_function(ax=ax_km, ci_show=True, linewidth=3, color=color, alpha=0.9)
    try:
        ms = kmf_mm.median_survival_time_
        median_s_mm[grp] = f"{ms:.1f} mo" if not (np.isnan(ms) or np.isinf(ms)) else "NR"
    except: median_s_mm[grp] = "NR"

ax_km.set_ylabel('Overall Survival Probability', fontsize=14, fontweight='bold')
ax_km.set_title(
    f'Kaplan-Meier — Multi-Modal SAGAM (Clinical + 10-Gene Expression)\n'
    f'TCGA-LUAD n={len(df_mm)}, Pooled OOF | Log-rank Low vs High: '
    f'p={lr_mm.p_value:.4f} [{sig_mm}]  |  C-index={results["Multi-Modal"]["mean_c"]:.4f}',
    fontsize=11, fontweight='bold', pad=8)
ax_km.grid(True, alpha=0.3, linestyle='--'); ax_km.set_ylim(0, 1.05)
ax_km.tick_params(labelbottom=False)
_hs, _ls = ax_km.get_legend_handles_labels()
_clean = [(h, l) for h, l in zip(_hs, _ls) if not l.lower().startswith('significance')]
if _clean:
    _hl, _ll = zip(*_clean)
    ax_km.legend(_hl, _ll, fontsize=12, loc='lower left', framealpha=0.92, edgecolor='grey')
for i, (grp, ms_txt) in enumerate(median_s_mm.items()):
    ax_km.text(0.98, 0.97 - i*0.09, f"{grp}: Median = {ms_txt}",
               transform=ax_km.transAxes, fontsize=10, fontweight='bold', ha='right', va='top',
               bbox=dict(boxstyle='round', facecolor=colors_km[i], alpha=0.15,
                         edgecolor=colors_km[i], linewidth=1.5))

time_pts = [0, 12, 24, 36, 48, 60]
ax_km2.axis('off')
ax_km2.set_xlabel('Time (Months)', fontsize=13, fontweight='bold', labelpad=4)
xlim = ax_km.get_xlim()
x_fracs = [(t - xlim[0]) / (xlim[1] - xlim[0]) for t in time_pts]
y_hdr = 0.88; y_rows = [0.62, 0.37, 0.12]
for xf, t in zip(x_fracs, time_pts):
    ax_km2.text(xf, y_hdr, str(t), transform=ax_km2.transAxes,
                fontsize=9, fontweight='bold', ha='center', va='center')
ax_km2.text(-0.005, y_hdr, 'Time (mo)', transform=ax_km2.transAxes,
            fontsize=8, fontstyle='italic', ha='right', va='center', color='#444444')
for grp, color, yr in zip(['Low Risk','Medium Risk','High Risk'], colors_km, y_rows):
    mask = (risk_grp_mm == grp)
    ax_km2.text(-0.005, yr, grp, transform=ax_km2.transAxes,
                fontsize=9, fontweight='bold', color=color, ha='right', va='center')
    for xf, t in zip(x_fracs, time_pts):
        ax_km2.text(xf, yr, str(int((ti_km[mask] >= t).sum())),
                    transform=ax_km2.transAxes, fontsize=9, ha='center', va='center', color=color)
plt.savefig(OUTPUT_DIR / 'kaplan_meier_multimodal.png', dpi=300, bbox_inches='tight')
plt.close()
print("  [OK] kaplan_meier_multimodal.png")

# ─── C-index comparison bar chart ───────────────────────────────────────────

print("Generating model comparison bar chart...")

# All models for comparison (use existing + new)
all_models = {
    'Stage Cox':         0.657,  # from main pipeline
    'Clinical SAGAM':   results['Clinical-only']['mean_c'],
    'Expression SAGAM': results['Expression-only']['mean_c'],
    'Multi-Modal SAGAM': results['Multi-Modal']['mean_c'],
    'Linear Stack':     0.630,   # from main pipeline summary
}
model_names = list(all_models.keys())
model_values = [all_models[m] for m in model_names]
bar_colors = ['#9E9E9E', '#2196F3', '#FF5722', '#4CAF50', '#9C27B0']
bar_errors  = [0.04, results['Clinical-only']['std_c'],
               results['Expression-only']['std_c'], results['Multi-Modal']['std_c'], 0.045]

fig_bar, ax_bar = plt.subplots(figsize=(11, 6))
fig_bar.patch.set_facecolor('#FAFAFA')
ax_bar.set_facecolor('#FAFAFA')

bars = ax_bar.barh(model_names, model_values, xerr=bar_errors,
                    color=bar_colors, edgecolor='white', linewidth=1.5,
                    error_kw=dict(elinewidth=1.5, capsize=4, capthick=1.5, ecolor='#333333'),
                    height=0.55)
ax_bar.axvline(0.5, color='red', linewidth=1.2, linestyle='--', alpha=0.5, label='Random (C=0.5)')
ax_bar.axvline(0.7, color='green', linewidth=1.2, linestyle='--', alpha=0.5, label='Good (C=0.7)')
for i, (bar, val) in enumerate(zip(bars, model_values)):
    ax_bar.text(val + 0.003, bar.get_y() + bar.get_height()/2,
                f'{val:.4f}', va='center', fontsize=10, fontweight='bold')

ax_bar.set_xlabel('C-index (Concordance Index)', fontsize=13, fontweight='bold')
ax_bar.set_title('Model Comparison: C-index (5-fold Nested CV, TCGA-LUAD)\n'
                 'Multi-Modal SAGAM integrates clinical features + 10-gene expression panel',
                 fontsize=12, fontweight='bold')
ax_bar.set_xlim(0.45, 0.78)
ax_bar.grid(axis='x', alpha=0.3, linestyle='--')
ax_bar.legend(fontsize=10, loc='lower right')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / 'model_comparison_bar.png', dpi=300, bbox_inches='tight')
plt.close()
print("  [OK] model_comparison_bar.png")

# ─── Save results text ───────────────────────────────────────────────────────

with open(OUTPUT_DIR / 'multimodal_results.txt', 'w', encoding='utf-8') as fout:
    fout.write("MULTI-MODAL SAGAM RESULTS\n")
    fout.write("=" * 60 + "\n\n")
    fout.write("3-WAY NESTED CV COMPARISON (5-fold StratifiedKFold)\n")
    fout.write(f"{'Model':<25} {'Mean C':>8} {'Std C':>8} {'Delta vs Clin':>14}\n")
    fout.write("-" * 57 + "\n")
    for name, res in results.items():
        delta = res['mean_c'] - results['Clinical-only']['mean_c']
        fout.write(f"{name:<25} {res['mean_c']:>8.4f} {res['std_c']:>8.4f} {delta:>+14.4f}\n")
    fout.write("\nFold-level C-indices:\n")
    for name, res in results.items():
        fc = ', '.join([f"{c:.4f}" for c in res['fold_c']])
        fout.write(f"  {name}: [{fc}]\n")
    fout.write("\nMULTI-MODAL KM STRATIFICATION\n")
    fout.write(f"  Log-rank Low vs High: p={lr_mm.p_value:.6f} [{sig_mm}]\n")
    for grp, ms_txt in median_s_mm.items():
        fout.write(f"  {grp}: Median OS = {ms_txt}\n")
    fout.write("\nARCHITECTURE UPGRADES\n")
    fout.write("  DeepSurv: 64->32 (old) --> 128->64 + BatchNorm (new)\n")
    fout.write("  5th base learner: ExprCox (CoxNet on 10-gene panel)\n")
    fout.write("  Meta-learner: B-spline GAM on RSF, GBS, XGB, DS, ExprCox\n")

print("  [OK] multimodal_results.txt")
print("\n" + "=" * 70)
print("ALL DONE")
print("=" * 70)
print(f"\n  Expression-only:  C = {results['Expression-only']['mean_c']:.4f} +/- {results['Expression-only']['std_c']:.4f}")
print(f"  Clinical-only:    C = {results['Clinical-only']['mean_c']:.4f} +/- {results['Clinical-only']['std_c']:.4f}")
print(f"  Multi-Modal:      C = {results['Multi-Modal']['mean_c']:.4f} +/- {results['Multi-Modal']['std_c']:.4f}")
delta_mm = results['Multi-Modal']['mean_c'] - results['Clinical-only']['mean_c']
print(f"\n  Delta Multi-Modal vs Clinical: {delta_mm:+.4f}")
if delta_mm > 0.005:
    print("  *** Expression features ADD VALUE to clinical SAGAM ***")
elif delta_mm > 0:
    print("  Expression provides marginal gain (< 0.005 delta)")
else:
    print("  Expression does not improve clinical SAGAM alone")
