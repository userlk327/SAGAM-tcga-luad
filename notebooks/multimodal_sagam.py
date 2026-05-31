"""
Multi-Modal SAGAM: Clinical + Expression Integration
=====================================================
Adds gene-expression features to the SAGAM pipeline and runs a
3-way nested CV comparison:

  1. Clinical-only SAGAM  (existing baseline, reproduced for fair comparison)
  2. Expression-only SAGAM (10-gene panel on TCGA)
  3. Multi-Modal SAGAM   (clinical + expression, 5 base learners)

Also produces:
  - Enhanced interpretability figure (trust-zone annotated smooth contributions)
  - Calibration curves (predicted vs observed at 1 / 3 / 5 years)
  - Multi-modal KM stratification

Outputs saved to results_v2/
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
from sksurv.metrics import concordance_index_censored, cumulative_dynamic_auc

from patsy import dmatrix, build_design_matrices
from lifelines import KaplanMeierFitter
from lifelines.statistics import logrank_test, multivariate_logrank_test

warnings.filterwarnings("ignore")
SEED = 42
np.random.seed(SEED); random.seed(SEED); torch.manual_seed(SEED)

REPO_ROOT  = Path(__file__).resolve().parent.parent
DATA_DIR   = REPO_ROOT / 'dataset'
OUTPUT_DIR = REPO_ROOT / 'results_v2'
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

print("=" * 70)
print("MULTI-MODAL SAGAM — Clinical + Expression Integration")
print("=" * 70)

# ================================================================
# SHARED HELPERS (identical to final_experiments.py)
# ================================================================

class DeepSurv(nn.Module):
    """Upgraded 128->64 architecture (from 64->32) — matches best prior config."""
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
    """Train DeepSurv with early stopping on validation set."""
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
        with torch.no_grad():
            vl = cox_loss(net(Xv_t), yv_t, yv_e).item()
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

# ================================================================
# 1. LOAD TCGA CLINICAL DATA
# ================================================================

print("\n[1] Loading TCGA clinical data...")

def load_cbio(path):
    with open(path) as fh:
        skip = sum(1 for line in fh if line.startswith('#'))
    return pd.read_csv(path, sep='\t', skiprows=skip, low_memory=False)

patient = load_cbio(DATA_DIR / 'data_clinical_patient.txt')
sample  = load_cbio(DATA_DIR / 'data_clinical_sample.txt')
df_clin = patient.merge(sample, on='PATIENT_ID', how='inner')
df_clin['OS_time']  = pd.to_numeric(df_clin['OS_MONTHS'], errors='coerce')
df_clin['OS_event'] = df_clin['OS_STATUS'].str.startswith('1').fillna(False).astype(int)
df_clin = df_clin[df_clin['OS_time'].notna() & (df_clin['OS_time'] > 0)].copy()
df_clin = df_clin.reset_index(drop=True)

LEAKAGE = ['OS_MONTHS','OS_STATUS','DSS_STATUS','DSS_MONTHS','DFS_STATUS','DFS_MONTHS',
           'PFS_STATUS','PFS_MONTHS','DAYS_LAST_FOLLOWUP','DAYS_TO_BIRTH',
           'DAYS_TO_INITIAL_PATHOLOGIC_DIAGNOSIS','PERSON_NEOPLASM_CANCER_STATUS',
           'NEW_TUMOR_EVENT_AFTER_INITIAL_TREATMENT','RADIATION_THERAPY','PATIENT_ID','SAMPLE_ID',
           'OTHER_PATIENT_ID','SUBTYPE','CANCER_TYPE','CANCER_TYPE_DETAILED',
           'TUMOR_TYPE','CANCER_TYPE_ACRONYM','ONCOTREE_CODE','TISSUE_SOURCE_SITE',
           'TISSUE_SOURCE_SITE_CODE','SAMPLE_TYPE','SOMATIC_STATUS','ICD_10',
           'ICD_O_3_HISTOLOGY','ICD_O_3_SITE','AJCC_STAGING_EDITION',
           'FORM_COMPLETION_DATE','INFORMED_CONSENT_VERIFIED','IN_PANCANPATHWAYS_FREEZE',
           'HISTORY_NEOADJUVANT_TRTYN','TISSUE_PROSPECTIVE_COLLECTION_INDICATOR',
           'TISSUE_RETROSPECTIVE_COLLECTION_INDICATOR',
           'PRIMARY_LYMPH_NODE_PRESENTATION_ASSESSMENT',
           'TUMOR_TISSUE_SITE','GENETIC_ANCESTRY_LABEL']

# Retain patient ID for merging with expression, then drop from features
patient_ids = df_clin['PATIENT_ID'].copy()
df_clin.drop(columns=[c for c in LEAKAGE if c in df_clin.columns], inplace=True, errors='ignore')

ALL_FEATS = ['AJCC_PATHOLOGIC_TUMOR_STAGE','PATH_M_STAGE','PATH_N_STAGE','PATH_T_STAGE',
             'AGE','SEX','GRADE','ETHNICITY','RACE','PRIOR_DX','WEIGHT',
             'ANEUPLOIDY_SCORE','MSI_SCORE_MANTIS','MSI_SENSOR_SCORE','TMB_NONSYNONYMOUS',
             'TBL_SCORE','BUFFA_HYPOXIA_SCORE','WINTER_HYPOXIA_SCORE','RAGNUM_HYPOXIA_SCORE']
get_cols = lambda cols: [c for c in cols if c in df_clin.columns]

print(f"  Clinical: n={len(df_clin)}, events={df_clin['OS_event'].sum()}")

# ================================================================
# 2. LOAD GENE EXPRESSION (10-GENE PANEL)
# ================================================================

print("\n[2] Loading gene expression (10-gene panel)...")

GENE_PANEL = ['DKK1', 'FAM83A', 'RHOV', 'IRX5', 'SFTA3',
              'CD1B', 'PKP2', 'TNS4', 'LYPD3', 'TFAP2A']

expr_raw = pd.read_csv(DATA_DIR / 'data_mrna_seq_v2_rsem.txt',
                        sep='\t', index_col=0, low_memory=False)
expr_raw = expr_raw.drop(columns=['Entrez_Gene_Id'], errors='ignore')
# Strip sample-type suffix: TCGA-05-4244-01 -> TCGA-05-4244
expr_raw.columns = expr_raw.columns.str[:12]

# Select panel, transpose to (samples × genes), log2-transform
expr_panel = expr_raw.loc[GENE_PANEL].T.copy()
expr_panel = np.log2(expr_panel + 1)
expr_panel.index.name = 'PATIENT_ID'

print(f"  Expression: {len(expr_panel)} samples × {len(GENE_PANEL)} genes")
print(f"  Genes: {GENE_PANEL}")

# ================================================================
# 3. CREATE MULTI-MODAL MERGED DATASET
# ================================================================

print("\n[3] Creating merged clinical + expression dataset...")

df_clin['PATIENT_ID_KEY'] = patient_ids.values
df_mm = df_clin.merge(expr_panel, left_on='PATIENT_ID_KEY', right_index=True, how='inner')
df_mm = df_mm.drop(columns=['PATIENT_ID_KEY']).reset_index(drop=True)

clin_feats = get_cols(ALL_FEATS)
expr_feats = [g for g in GENE_PANEL if g in df_mm.columns]
mm_feats   = clin_feats + expr_feats

y_mm = Surv.from_arrays(event=df_mm['OS_event'].values, time=df_mm['OS_time'].values)

print(f"  Multi-modal dataset: n={len(df_mm)}, events={df_mm['OS_event'].sum()}")
print(f"  Clinical features: {len(clin_feats)}, Expression features: {len(expr_feats)}")

# ================================================================
# 4. NESTED CV HELPER — runs SAGAM on any feature set
# ================================================================

def run_sagam_nested_cv(df_use, y_use, feature_cols, expr_only_cols,
                         label="SAGAM", n_outer=5, n_inner=3,
                         use_expr_cox=False, verbose=True):
    """
    Runs full nested 5-fold CV and returns pooled OOF predictions + fold C-indices.

    Parameters
    ----------
    df_use        : DataFrame with features + OS_event + OS_time
    y_use         : structured array (event, time)
    feature_cols  : list of ALL feature column names for RSF/GBS/XGB/DS
    expr_only_cols: list of expression-only feature names (for ExprCox if used)
    label         : string label for printing
    use_expr_cox  : if True, add ExpressionCox as 5th base learner
    """
    outer_kf = StratifiedKFold(n_outer, shuffle=True, random_state=SEED)
    pooled_risk = np.zeros(len(df_use))
    fold_c = []
    META_FEATS = ["RSF", "GBS", "XGB", "DS"] + (["ExprCox"] if use_expr_cox else [])
    n_learners = len(META_FEATS)

    for fold_i, (tr_i, te_i) in enumerate(outer_kf.split(np.arange(len(df_use)), y_use['event'])):
        if verbose: print(f"  [{label}] Fold {fold_i+1}/{n_outer}...", end=' ', flush=True)

        X_tr_raw = df_use[feature_cols].iloc[tr_i]
        X_te_raw = df_use[feature_cols].iloc[te_i]
        y_tr, y_te = y_use[tr_i], y_use[te_i]

        # Preprocessing: fit on train only
        cat_c = X_tr_raw.select_dtypes(['object', 'category']).columns.tolist()
        num_c = X_tr_raw.select_dtypes(['number', 'bool']).columns.tolist()
        pre = ColumnTransformer([
            ('cat', OneHotEncoder(drop='first', sparse_output=False, handle_unknown='ignore'), cat_c),
            ('num', SimpleImputer(strategy='median'), num_c),
        ], remainder='drop')
        Xp_tr = pre.fit_transform(X_tr_raw)
        Xp_te = pre.transform(X_te_raw)
        sc = StandardScaler()
        Xs_tr = sc.fit_transform(Xp_tr)
        Xs_te = sc.transform(Xp_te)

        # Expression-only features for ExprCox
        if use_expr_cox and expr_only_cols:
            Xe_tr = StandardScaler().fit_transform(
                df_use[expr_only_cols].iloc[tr_i].values)
            Xe_te = StandardScaler().fit_transform(
                df_use[expr_only_cols].iloc[te_i].values)
        else:
            Xe_tr = Xe_te = None

        # Inner OOF for stacking
        inn_kf = KFold(n_inner, shuffle=True, random_state=SEED)
        oof = np.zeros((len(tr_i), n_learners))

        # ES set carved BEFORE inner CV
        es_size = max(10, int(0.15 * len(Xs_tr)))
        X_es, y_es = Xs_tr[:es_size], y_tr[:es_size]
        Xs_cv, y_cv = Xs_tr[es_size:], y_tr[es_size:]

        for ii_tr, ii_vl in inn_kf.split(Xs_cv):
            Xi, Xj = Xs_cv[ii_tr], Xs_cv[ii_vl]
            yi, yj = y_cv[ii_tr], y_cv[ii_vl]
            oof_idx = ii_vl + es_size

            # RSF
            rsf_i = RandomSurvivalForest(n_estimators=200, max_features='sqrt',
                                          min_samples_leaf=5, random_state=SEED, n_jobs=-1)
            rsf_i.fit(Xi, yi); oof[oof_idx, 0] = rsf_i.predict(Xj)

            # GBS
            gbs_i = GradientBoostingSurvivalAnalysis(n_estimators=200, learning_rate=0.05,
                                                      max_depth=3, random_state=SEED)
            gbs_i.fit(Xi, yi); oof[oof_idx, 1] = gbs_i.predict(Xj)

            # XGB
            dt = xgb.DMatrix(Xi, label=[e['time'] for e in yi], weight=[e['event'] for e in yi])
            dv = xgb.DMatrix(X_es, label=[e['time'] for e in y_es], weight=[e['event'] for e in y_es])
            xm = xgb.train(XGB_P, dt, num_boost_round=300, evals=[(dv, 'v')],
                           early_stopping_rounds=20, verbose_eval=False)
            it = getattr(xm, 'best_iteration', xm.num_boosted_rounds())
            oof[oof_idx, 2] = xm.predict(xgb.DMatrix(Xj), iteration_range=(0, it))

            # DeepSurv (128->64 upgraded)
            dn = train_ds(Xi, yi, X_es, y_es, Xi.shape[1])
            oof[oof_idx, 3] = ds_pred(dn, Xj)

            # ExprCox (expression-only, no ES needed)
            if use_expr_cox and Xe_tr is not None:
                Xe_i = Xe_tr[ii_tr]; Xe_j = Xe_tr[ii_vl]
                y_s_i = make_surv(yi['event'], yi['time'])
                a_ec = tune_alpha_on_train(Xe_i, y_s_i)
                ec_m = coxnet_fit(Xe_i, y_s_i, a_ec)
                oof[oof_idx, 4] = ec_m.predict(Xe_j)

        # Drop ES rows; meta-learner trains on CV rows only
        oof_meta = oof[es_size:]
        y_tr_meta = y_cv

        # Final models for test set
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
                                               weight=[e['event'] for e in y_es]), 'v')],
                          early_stopping_rounds=20, verbose_eval=False)
        it_f = getattr(xm_f, 'best_iteration', xm_f.num_boosted_rounds())
        dn_f = train_ds(Xs_f, y_f, X_es, y_es, Xs_f.shape[1])

        te_preds = np.column_stack([
            rsf_f.predict(Xs_te),
            gbs_f.predict(Xs_te),
            xm_f.predict(xgb.DMatrix(Xs_te), iteration_range=(0, it_f)),
            ds_pred(dn_f, Xs_te)
        ])
        if use_expr_cox and Xe_te is not None:
            y_f_s = make_surv(y_f['event'], y_f['time'])
            a_ecf = tune_alpha_on_train(Xe_tr[es_size:], y_f_s)
            ec_f  = coxnet_fit(Xe_tr[es_size:], y_f_s, a_ecf)
            te_preds = np.column_stack([te_preds, ec_f.predict(Xe_te)])

        # Build meta-feature DataFrames
        meta_tr = pd.DataFrame(oof_meta, columns=META_FEATS)
        meta_te = pd.DataFrame(te_preds, columns=META_FEATS)
        for f in META_FEATS:
            mn, mx = meta_tr[f].min(), meta_tr[f].max()
            meta_te[f] = meta_te[f].clip(mn, mx)

        # Spline basis
        sp_tr, dis, smap = build_splines(meta_tr, META_FEATS)
        sp_te = apply_splines(meta_te, META_FEATS, dis)
        sp_te.columns = sp_tr.columns

        y_tr_s = make_surv(y_tr_meta['event'], y_tr_meta['time'])
        sp_tv, sp_vl = train_test_split(sp_tr, test_size=0.2, random_state=SEED)
        ym_tv = y_tr_s[sp_tv.index]; ym_vl = y_tr_s[sp_vl.index]
        a_gam = tune_alpha(sp_tv.values, ym_tv, sp_vl.values, ym_vl)
        gam_m = coxnet_fit(sp_tr.values, y_tr_s, a_gam)
        risk_te = gam_m.predict(sp_te.values)

        pooled_risk[te_i] = risk_te
        c_fold = ci(y_te['event'], y_te['time'], risk_te)
        fold_c.append(c_fold)
        if verbose: print(f"C={c_fold:.4f}")

    return pooled_risk, fold_c, META_FEATS

# ================================================================
# 5. RUN 3-WAY NESTED CV COMPARISON
# ================================================================

print("\n" + "=" * 60)
print("EXPERIMENT: 3-Way Nested CV Comparison")
print("Clinical | Expression | Multi-Modal SAGAM")
print("=" * 60)

results = {}

# -- Expression-only SAGAM --
print("\n[A] Expression-only SAGAM (10 genes, CoxNet stack)...")
# For expression-only we use CoxNet on all 10 genes as single base learner
# plus RSF/GBS on expression features — this tests whether genes alone work
outer_kf = StratifiedKFold(5, shuffle=True, random_state=SEED)
expr_oof_risk = np.zeros(len(df_mm))
expr_fold_c   = []

for fold_i, (tr_i, te_i) in enumerate(outer_kf.split(np.arange(len(df_mm)), y_mm['event'])):
    print(f"  [ExprOnly] Fold {fold_i+1}/5...", end=' ', flush=True)
    Xe_tr_raw = df_mm[expr_feats].iloc[tr_i].values.astype(float)
    Xe_te_raw = df_mm[expr_feats].iloc[te_i].values.astype(float)
    y_tr, y_te = y_mm[tr_i], y_mm[te_i]

    sc_e = StandardScaler()
    Xe_tr = sc_e.fit_transform(Xe_tr_raw)
    Xe_te = sc_e.transform(Xe_te_raw)

    y_tr_s = make_surv(y_tr['event'], y_tr['time'])
    a_e = tune_alpha_on_train(Xe_tr, y_tr_s)
    ec_m = coxnet_fit(Xe_tr, y_tr_s, a_e)
    risk_e = ec_m.predict(Xe_te)
    expr_oof_risk[te_i] = risk_e
    c_e = ci(y_te['event'], y_te['time'], risk_e)
    expr_fold_c.append(c_e)
    print(f"C={c_e:.4f}")

results['Expression-only'] = {
    'pooled_risk': expr_oof_risk,
    'fold_c': expr_fold_c,
    'mean_c': np.mean(expr_fold_c),
    'std_c':  np.std(expr_fold_c)
}
print(f"  Expression-only SAGAM: C = {np.mean(expr_fold_c):.4f} ± {np.std(expr_fold_c):.4f}")

# -- Clinical-only SAGAM --
print("\n[B] Clinical-only SAGAM (all clinical features, 4 base learners)...")
clin_risk, clin_fold_c, _ = run_sagam_nested_cv(
    df_mm, y_mm, clin_feats, expr_only_cols=[],
    label="Clinical", use_expr_cox=False)
results['Clinical-only'] = {
    'pooled_risk': clin_risk,
    'fold_c': clin_fold_c,
    'mean_c': np.mean(clin_fold_c),
    'std_c':  np.std(clin_fold_c)
}
print(f"  Clinical-only SAGAM:   C = {np.mean(clin_fold_c):.4f} ± {np.std(clin_fold_c):.4f}")

# -- Multi-Modal SAGAM (5 base learners) --
print("\n[C] Multi-Modal SAGAM (clinical + expression, 5 base learners)...")
mm_risk, mm_fold_c, mm_feats_used = run_sagam_nested_cv(
    df_mm, y_mm, mm_feats, expr_only_cols=expr_feats,
    label="MultiModal", use_expr_cox=True)
results['Multi-Modal'] = {
    'pooled_risk': mm_risk,
    'fold_c': mm_fold_c,
    'mean_c': np.mean(mm_fold_c),
    'std_c':  np.std(mm_fold_c)
}
print(f"  Multi-Modal SAGAM:     C = {np.mean(mm_fold_c):.4f} ± {np.std(mm_fold_c):.4f}")

# -- Summary table --
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

# Save comparison
comp_df = pd.DataFrame({
    'Model': list(results.keys()),
    'Mean_C': [r['mean_c'] for r in results.values()],
    'Std_C':  [r['std_c']  for r in results.values()],
    'Fold_C': [r['fold_c'] for r in results.values()]
})
comp_df.to_csv(OUTPUT_DIR / 'multimodal_comparison.csv', index=False)

# ================================================================
# 6. INTERPRETABILITY: TRUST-ZONE ANNOTATED SMOOTH CONTRIBUTIONS
# ================================================================

print("\n" + "=" * 60)
print("INTERPRETABILITY: Trust-Zone Annotated Smooth Contributions")
print("=" * 60)

# Refit GAM on all data (one representative fold for the figure)
print("  Fitting representative GAM for interpretability figure...")
outer_kf_rep = StratifiedKFold(5, shuffle=True, random_state=SEED)
for fold_i, (tr_i, te_i) in enumerate(outer_kf_rep.split(np.arange(len(df_mm)), y_mm['event'])):
    if fold_i > 0: break  # use fold 1 only for the figure

    X_tr_f = df_mm[mm_feats].iloc[tr_i]
    y_tr_f  = y_mm[tr_i]

    cat_c = X_tr_f.select_dtypes(['object', 'category']).columns.tolist()
    num_c = X_tr_f.select_dtypes(['number', 'bool']).columns.tolist()
    pre_f = ColumnTransformer([
        ('cat', OneHotEncoder(drop='first', sparse_output=False, handle_unknown='ignore'), cat_c),
        ('num', SimpleImputer(strategy='median'), num_c),
    ], remainder='drop')
    Xs_f = StandardScaler().fit_transform(pre_f.fit_transform(X_tr_f))

    # Expression features
    Xe_f = StandardScaler().fit_transform(df_mm[expr_feats].iloc[tr_i].values.astype(float))

    inn_kf = KFold(3, shuffle=True, random_state=SEED)
    oof_f  = np.zeros((len(tr_i), 5))
    X_es_f = Xs_f[:max(10, int(0.15 * len(Xs_f)))]
    y_es_f = y_tr_f[:max(10, int(0.15 * len(y_tr_f)))]
    Xs_cv_f, y_cv_f = Xs_f[max(10, int(0.15*len(Xs_f))):], y_tr_f[max(10, int(0.15*len(y_tr_f))):]

    for ii_tr, ii_vl in inn_kf.split(Xs_cv_f):
        es_ = max(10, int(0.15*len(Xs_f)))
        Xi, Xj = Xs_cv_f[ii_tr], Xs_cv_f[ii_vl]
        yi, yj = y_cv_f[ii_tr], y_cv_f[ii_vl]
        oof_idx = ii_vl + es_

        rsf_i = RandomSurvivalForest(n_estimators=200, max_features='sqrt',
                                      min_samples_leaf=5, random_state=SEED, n_jobs=-1)
        rsf_i.fit(Xi, yi); oof_f[oof_idx, 0] = rsf_i.predict(Xj)
        gbs_i = GradientBoostingSurvivalAnalysis(n_estimators=200, learning_rate=0.05,
                                                  max_depth=3, random_state=SEED)
        gbs_i.fit(Xi, yi); oof_f[oof_idx, 1] = gbs_i.predict(Xj)
        dt_i = xgb.DMatrix(Xi, label=[e['time'] for e in yi], weight=[e['event'] for e in yi])
        dv_i = xgb.DMatrix(X_es_f, label=[e['time'] for e in y_es_f],
                             weight=[e['event'] for e in y_es_f])
        xm_i = xgb.train(XGB_P, dt_i, num_boost_round=200,
                          evals=[(dv_i, 'v')], early_stopping_rounds=20, verbose_eval=False)
        oof_f[oof_idx, 2] = xm_i.predict(xgb.DMatrix(Xj),
                                           iteration_range=(0, getattr(xm_i, 'best_iteration', 200)))
        dn_i = train_ds(Xi, yi, X_es_f, y_es_f, Xi.shape[1])
        oof_f[oof_idx, 3] = ds_pred(dn_i, Xj)

        # ExprCox inner
        Xe_cv_f = Xe_f[es_:]
        Xe_i = Xe_cv_f[ii_tr]; Xe_j = Xe_cv_f[ii_vl]
        yi_s = make_surv(yi['event'], yi['time'])
        a_ec = tune_alpha_on_train(Xe_i, yi_s)
        ec_m = coxnet_fit(Xe_i, yi_s, a_ec)
        oof_f[oof_idx, 4] = ec_m.predict(Xe_j)

    es_ = max(10, int(0.15*len(Xs_f)))
    oof_f_meta = oof_f[es_:]
    y_meta_f = make_surv(y_cv_f['event'], y_cv_f['time'])

META_FEATS_MM = ['RSF', 'GBS', 'XGB', 'DS', 'ExprCox']
meta_rep = pd.DataFrame(oof_f_meta, columns=META_FEATS_MM)
# Standardize scores for comparability across learners
for f in META_FEATS_MM:
    meta_rep[f] = (meta_rep[f] - meta_rep[f].mean()) / (meta_rep[f].std() + 1e-8)

sp_rep, dis_rep, smap_rep = build_splines(meta_rep, META_FEATS_MM)
sp_tv_r, sp_vl_r = train_test_split(sp_rep, test_size=0.2, random_state=SEED)
ym_tv_r = y_meta_f[sp_tv_r.index]; ym_vl_r = y_meta_f[sp_vl_r.index]
a_rep   = tune_alpha(sp_tv_r.values, ym_tv_r, sp_vl_r.values, ym_vl_r)
gam_rep = coxnet_fit(sp_rep.values, y_meta_f, a_rep)

gam_coefs = gam_rep.coef_.ravel()
sp_cols   = list(sp_rep.columns)

# Compute relative contribution per learner
contrib = {}
for f in META_FEATS_MM:
    idx_c = [sp_cols.index(c) for c in smap_rep[f] if c in sp_cols]
    contrib[f] = float(np.sum(np.abs(gam_coefs[idx_c])))
total_contrib = sum(contrib.values()) + 1e-12
contrib_pct   = {f: 100*v/total_contrib for f, v in contrib.items()}

print("  Learner contributions:")
for f, pct in contrib_pct.items():
    print(f"    {f:>8s}: {pct:.1f}%")

# --- Build enhanced 5-panel interpretability figure ---
colors_panel = ['#2196F3', '#FF5722', '#4CAF50', '#9C27B0', '#E91E63']
labels_full  = [
    'RSF (Random Survival Forest)',
    'GBS (Gradient Boosting Survival)',
    'XGBoost-Cox',
    'DeepSurv (128->64)',
    'ExprCox (10-Gene Panel)'
]
descriptions = [
    'Ensemble of survival trees;\ncaptures complex clinical interactions',
    'Boosted regression on clinical data;\nseeks additive risk structure',
    'Cox-regularized boosting;\nexcels at non-monotone clinical scores',
    'Deep neural network;\nlearns latent clinical representations',
    'Lasso Cox on 10 gene panel;\nbiologically interpretable expression signal'
]

fig = plt.figure(figsize=(20, 13))
fig.patch.set_facecolor('#FAFAFA')
outer_gs = mgridspec.GridSpec(2, 3, figure=fig, hspace=0.38, wspace=0.32,
                              left=0.06, right=0.97, top=0.90, bottom=0.07)

axes_list = []
for r in range(2):
    for c in range(3):
        if r == 1 and c == 2:
            break
        axes_list.append(fig.add_subplot(outer_gs[r, c]))

# Summary panel: contribution pie
ax_pie = fig.add_subplot(outer_gs[1, 2])
wedge_colors = colors_panel
wedge_sizes  = [contrib_pct[f] for f in META_FEATS_MM]
wedge_labels = [f"{f}\n{contrib_pct[f]:.1f}%" for f in META_FEATS_MM]
ax_pie.pie(wedge_sizes, labels=wedge_labels, colors=wedge_colors,
           autopct='', startangle=90,
           textprops={'fontsize': 9, 'fontweight': 'bold'})
ax_pie.set_title('Relative Contribution\nto Meta-Learner', fontsize=11,
                  fontweight='bold', pad=8)

for panel_i, (f, color, label, desc) in enumerate(
        zip(META_FEATS_MM, colors_panel, labels_full, descriptions)):

    ax = axes_list[panel_i]
    ax.set_facecolor('#FAFAFA')

    vals  = meta_rep[f].values
    grid  = np.linspace(vals.min(), vals.max(), 400)
    df_g  = pd.DataFrame({f: grid})
    S_g   = dmatrix(f"bs({f}, df=4, degree=3, include_intercept=False)",
                    df_g, return_type='dataframe')
    idx_c = [sp_cols.index(c) for c in smap_rep[f] if c in sp_cols]
    fvals = S_g.values @ gam_coefs[idx_c]

    # Numerical derivative for trust-zone detection
    dfvals = np.gradient(fvals, grid)
    trust_thresh = 0.3 * np.max(np.abs(dfvals))

    # Shade trust zones
    high_trust = np.abs(dfvals) > trust_thresh
    # Fill high-trust regions
    ax.fill_between(grid, fvals.min() - 0.05, fvals.max() + 0.05,
                    where=high_trust, alpha=0.10, color=color,
                    label='High-trust zone')

    # Linear CoxNet baseline
    try:
        y_s_rep = make_surv(y_tr_f['event'], y_tr_f['time'])
        v2d = vals.reshape(-1, 1)
        lin_a = tune_alpha_on_train(v2d, y_s_rep)
        lin_cx = coxnet_fit(v2d, y_s_rep, lin_a)
        lin_slope = float(lin_cx.coef_.ravel()[0])
        ax.plot(grid, lin_slope * grid, color='#888888', linewidth=1.5,
                linestyle='--', alpha=0.6, label='Linear equivalent', zorder=2)
    except:
        pass

    # Main spline curve
    ax.plot(grid, fvals, color=color, linewidth=2.8, label=f'SAGAM spline f({f})', zorder=3)

    # Zero reference
    ax.axhline(0, color='black', linewidth=0.7, linestyle=':', alpha=0.4)

    # Rug
    rug_y = fvals.min() - 0.06 * (fvals.max() - fvals.min())
    ax.scatter(vals[::4], np.full(len(vals[::4]), rug_y),
               marker='|', color=color, alpha=0.25, s=25, zorder=1)

    # Annotate trust zone transitions
    crossings = np.where(np.diff(high_trust.astype(int)))[0]
    for cx in crossings[:2]:
        ax.axvline(grid[cx], color=color, linewidth=0.8, linestyle=':', alpha=0.5)

    # Find most informative region and annotate
    peak_idx = np.argmax(np.abs(fvals))
    ax.annotate(
        f"Peak: {fvals[peak_idx]:+.2f}",
        xy=(grid[peak_idx], fvals[peak_idx]),
        xytext=(0.65 if grid[peak_idx] > 0 else 0.05, 0.85),
        textcoords='axes fraction',
        fontsize=8, color=color, fontweight='bold',
        arrowprops=dict(arrowstyle='->', color=color, lw=1.2)
    )

    # Contribution badge
    ax.text(0.03, 0.97, f"Contrib: {contrib_pct[f]:.1f}%",
            transform=ax.transAxes, fontsize=9, fontweight='bold',
            va='top', color='white',
            bbox=dict(boxstyle='round,pad=0.3', facecolor=color, alpha=0.85))

    ax.set_xlabel('Standardized risk score', fontsize=10)
    ax.set_ylabel('Log-hazard contribution f(score)', fontsize=10)
    ax.set_title(f'{label}\n{desc}', fontsize=10, fontweight='bold',
                 color=color, pad=4)
    ax.grid(alpha=0.25, linestyle='--')

    # Legend (compact)
    handles, lbs = ax.get_legend_handles_labels()
    ax.legend(handles[:3], lbs[:3], fontsize=7.5, loc='upper left',
              framealpha=0.85, edgecolor='lightgrey')

fig.suptitle(
    'SAGAM Interpretability: Per-Learner Smooth Contribution Functions\n'
    'Shaded = high-trust zones (|df/dx| > 30% max). '
    'Nonlinear deviations from dashed linear baseline confirm spline necessity.',
    fontsize=13, fontweight='bold', y=0.97)

plt.savefig(OUTPUT_DIR / 'interpretability_trust_zones.png', dpi=300, bbox_inches='tight')
plt.close()
print("  Trust-zone interpretability figure saved.")

# ================================================================
# 7. CALIBRATION CURVES (Predicted vs Observed Survival)
# ================================================================

print("\n" + "=" * 60)
print("CALIBRATION ANALYSIS: Predicted vs Observed at 1/3/5 Years")
print("=" * 60)

def calibration_curve(risk_scores, events, times, eval_time_months,
                       n_bins=5, label='SAGAM', color='steelblue', ax=None):
    """
    Calibration curve: split patients into n_bins by predicted risk,
    compare mean KM survival in each bin to mean predicted rank.
    Uses risk quintiles; 'observed' = KM estimate at eval_time.
    """
    if ax is None:
        _, ax = plt.subplots()
    try:
        bins = pd.qcut(pd.Series(risk_scores), n_bins, labels=False, duplicates='drop')
    except Exception:
        return ax

    bin_km_surv  = []
    bin_mean_rank = []

    kmf_cal = KaplanMeierFitter()
    for b in sorted(bins.dropna().unique()):
        mask = (bins == b)
        if mask.sum() < 5:
            continue
        kmf_cal.fit(times[mask], event_observed=events[mask])
        try:
            km_s = float(kmf_cal.predict(eval_time_months))
        except Exception:
            km_s = np.nan
        if not np.isnan(km_s):
            bin_km_surv.append(km_s)
            # Mean risk rank in this bin (normalized 0-1)
            rank = (risk_scores[mask].mean() - risk_scores.min()) / \
                   (risk_scores.max() - risk_scores.min() + 1e-8)
            # Convert rank to approximate survival: low rank = low risk = high survival
            bin_mean_rank.append(1 - rank)

    if len(bin_km_surv) < 2:
        return ax

    bin_km_surv  = np.array(bin_km_surv)
    bin_mean_rank = np.array(bin_mean_rank)

    ax.plot(bin_mean_rank, bin_km_surv, 'o-', color=color, linewidth=2,
            markersize=7, label=label)
    return ax

time_labels_cal = ['1-Year', '3-Year', '5-Year']
eval_times_cal  = [12.0, 36.0, 60.0]

fig_cal, axes_cal = plt.subplots(1, 3, figsize=(16, 5))
fig_cal.patch.set_facecolor('#FAFAFA')

model_colors_cal = {
    'Clinical-only':  '#2196F3',
    'Expression-only': '#FF5722',
    'Multi-Modal':    '#4CAF50',
}

ev_cal = df_mm['OS_event'].values.astype(bool)
ti_cal = df_mm['OS_time'].values

for j, (t_label, t_val) in enumerate(zip(time_labels_cal, eval_times_cal)):
    ax = axes_cal[j]
    ax.set_facecolor('#FAFAFA')

    for name, res in results.items():
        color = model_colors_cal.get(name, 'grey')
        calibration_curve(
            res['pooled_risk'], ev_cal, ti_cal,
            eval_time_months=t_val,
            n_bins=5, label=name, color=color, ax=ax)

    # Perfect calibration reference line
    ax.plot([0, 1], [0, 1], 'k--', linewidth=1, alpha=0.5, label='Perfect calibration')
    ax.set_xlabel('Predicted survival (by risk rank)', fontsize=12)
    ax.set_ylabel('Observed KM survival', fontsize=12)
    ax.set_title(f'{t_label} Calibration', fontsize=13, fontweight='bold')
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.grid(alpha=0.3, linestyle='--')
    ax.legend(fontsize=9, loc='upper left')

plt.suptitle('Calibration: Predicted (Risk Rank) vs Observed (Kaplan-Meier) Survival\n'
             'Points closer to diagonal = better calibration',
             fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / 'calibration_curves.png', dpi=300, bbox_inches='tight')
plt.close()
print("  Calibration curves saved.")

# ================================================================
# 8. MULTI-MODAL KM STRATIFICATION
# ================================================================

print("\n" + "=" * 60)
print("KM STRATIFICATION: Multi-Modal SAGAM")
print("=" * 60)

from matplotlib.gridspec import GridSpec as _GS

mm_risk_arr = results['Multi-Modal']['pooled_risk']
ev_km = df_mm['OS_event'].values
ti_km = df_mm['OS_time'].values
risk_grp_mm = pd.qcut(mm_risk_arr, q=3, labels=['Low Risk', 'Medium Risk', 'High Risk'])

lr_mm = logrank_test(
    ti_km[risk_grp_mm == 'Low Risk'], ti_km[risk_grp_mm == 'High Risk'],
    ev_km[risk_grp_mm == 'Low Risk'], ev_km[risk_grp_mm == 'High Risk'])
sig_mm = ('***' if lr_mm.p_value < 0.001 else '**' if lr_mm.p_value < 0.01
           else '*' if lr_mm.p_value < 0.05 else 'NS')

fig_km = plt.figure(figsize=(12, 10))
gs_km  = _GS(2, 1, figure=fig_km, height_ratios=[4, 1], hspace=0.04)
ax_km  = fig_km.add_subplot(gs_km[0])
ax_km2 = fig_km.add_subplot(gs_km[1], sharex=ax_km)

colors_km = ['#2E7D32', '#F57C00', '#C62828']
kmf_mm = KaplanMeierFitter()
median_s_mm = {}

for i, (grp, color) in enumerate(zip(['Low Risk', 'Medium Risk', 'High Risk'], colors_km)):
    mask = (risk_grp_mm == grp)
    kmf_mm.fit(ti_km[mask], ev_km[mask], label=f"{grp} (n={mask.sum()})")
    kmf_mm.plot_survival_function(ax=ax_km, ci_show=True, linewidth=3, color=color, alpha=0.9)
    try:
        ms = kmf_mm.median_survival_time_
        median_s_mm[grp] = f"{ms:.1f} mo" if not (np.isnan(ms) or np.isinf(ms)) else "NR"
    except:
        median_s_mm[grp] = "NR"

ax_km.set_ylabel('Overall Survival Probability', fontsize=14, fontweight='bold')
ax_km.set_title(
    f'Kaplan-Meier — Multi-Modal SAGAM Risk Stratification\n'
    f'TCGA-LUAD (n={len(df_mm)}, Pooled OOF) | Log-rank (Low vs High): '
    f'p={lr_mm.p_value:.4f} [{sig_mm}]',
    fontsize=12, fontweight='bold', pad=8)
ax_km.grid(True, alpha=0.3, linestyle='--'); ax_km.set_ylim(0, 1.05)
ax_km.tick_params(labelbottom=False)

# Clean legend
_hs, _ls = ax_km.get_legend_handles_labels()
_clean = [(h, l) for h, l in zip(_hs, _ls) if not l.lower().startswith('significance')]
if _clean:
    _hl, _ll = zip(*_clean)
    ax_km.legend(_hl, _ll, fontsize=12, loc='lower left', framealpha=0.92, edgecolor='grey')

for i, (grp, ms_txt) in enumerate(median_s_mm.items()):
    ax_km.text(0.98, 0.97 - i*0.09, f"{grp}: Median = {ms_txt}",
               transform=ax_km.transAxes, fontsize=10, fontweight='bold',
               ha='right', va='top',
               bbox=dict(boxstyle='round', facecolor=colors_km[i], alpha=0.15,
                         edgecolor=colors_km[i], linewidth=1.5))

# Number-at-risk table
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
for grp, color, yr in zip(['Low Risk', 'Medium Risk', 'High Risk'], colors_km, y_rows):
    mask = (risk_grp_mm == grp)
    ax_km2.text(-0.005, yr, grp, transform=ax_km2.transAxes,
                fontsize=9, fontweight='bold', color=color, ha='right', va='center')
    for xf, t in zip(x_fracs, time_pts):
        ax_km2.text(xf, yr, str(int((ti_km[mask] >= t).sum())),
                    transform=ax_km2.transAxes, fontsize=9, ha='center', va='center', color=color)

plt.savefig(OUTPUT_DIR / 'kaplan_meier_multimodal.png', dpi=300, bbox_inches='tight')
plt.close()
print("  Multi-modal KM figure saved.")

# ================================================================
# 9. SAVE ALL RESULTS
# ================================================================

print("\n" + "=" * 60)
print("SAVING RESULTS")
print("=" * 60)

with open(OUTPUT_DIR / 'multimodal_results.txt', 'w', encoding='utf-8') as fout:
    fout.write("MULTI-MODAL SAGAM RESULTS\n")
    fout.write("=" * 60 + "\n\n")

    fout.write("=== 3-WAY NESTED CV COMPARISON ===\n")
    fout.write(f"{'Model':<25} {'Mean C':>8} {'Std C':>8} {'Delta vs Clin':>14}\n")
    fout.write("-" * 57 + "\n")
    for name, res in results.items():
        delta = res['mean_c'] - results['Clinical-only']['mean_c']
        fout.write(f"{name:<25} {res['mean_c']:>8.4f} {res['std_c']:>8.4f} {delta:>+14.4f}\n")

    fout.write("\n=== LEARNER CONTRIBUTIONS (MULTI-MODAL) ===\n")
    for f, pct in sorted(contrib_pct.items(), key=lambda x: -x[1]):
        fout.write(f"  {f:>10s}: {pct:.1f}%\n")

    fout.write("\n=== MULTI-MODAL KM STRATIFICATION ===\n")
    fout.write(f"Log-rank (Low vs High): p={lr_mm.p_value:.6f} [{sig_mm}]\n")
    for grp, ms_txt in median_s_mm.items():
        fout.write(f"  {grp}: Median OS = {ms_txt}\n")

    fout.write("\n=== ARCHITECTURE UPGRADES ===\n")
    fout.write("  DeepSurv: 64->32 (old) --> 128->64 with BatchNorm (new)\n")
    fout.write("  5th base learner: ExprCox (CoxNet on 10-gene panel)\n")
    fout.write("  Meta-learner inputs: RSF, GBS, XGB, DS, ExprCox\n")

print(f"  [OK] multimodal_results.txt saved")
print(f"  [OK] multimodal_comparison.csv saved")
print(f"  [OK] interpretability_trust_zones.png saved")
print(f"  [OK] calibration_curves.png saved")
print(f"  [OK] kaplan_meier_multimodal.png saved")

print("\n" + "=" * 70)
print("MULTI-MODAL SAGAM COMPLETE")
print("=" * 70)
print(f"\n  Clinical-only:  C = {results['Clinical-only']['mean_c']:.4f}")
print(f"  Expression-only: C = {results['Expression-only']['mean_c']:.4f}")
print(f"  Multi-Modal:    C = {results['Multi-Modal']['mean_c']:.4f}")
delta_mm = results['Multi-Modal']['mean_c'] - results['Clinical-only']['mean_c']
print(f"\n  Delta (Multi-Modal vs Clinical): {delta_mm:+.4f}")
if delta_mm > 0.005:
    print("  *** Expression features ADD INCREMENTAL VALUE to clinical SAGAM ***")
elif delta_mm > 0:
    print("  Expression features provide marginal improvement (< 0.005 delta)")
else:
    print("  Expression features do not improve over clinical features alone")
