"""
Build the IEEE-formatted Word document (.docx) for the SAGAM paper.
Mirrors sagam_paper.tex (rewritten v3): improved prose, reconciled numbers,
and — unlike the previous build — the actual result figures are embedded.
"""
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from pathlib import Path

OUT       = Path(__file__).resolve().parent
REPO_ROOT = OUT.parent
FIG_DIR   = REPO_ROOT / "results_v2"

DOCX_PATH = OUT / "SAGAM_IEEE_Paper.docx"

doc = Document()

# ── Page setup: A4, narrow margins, two columns ──────────────────────────────
section = doc.sections[0]
section.page_width  = Cm(21.0)
section.page_height = Cm(29.7)
section.left_margin   = Cm(1.57)
section.right_margin  = Cm(1.57)
section.top_margin    = Cm(1.9)
section.bottom_margin = Cm(2.54)

sectPr = section._sectPr
cols_el = OxmlElement('w:cols')
cols_el.set(qn('w:num'), '2')
cols_el.set(qn('w:space'), '720')
sectPr.append(cols_el)

# Usable column width (page - margins - gutter) / 2 columns
COL_W_CM = (21.0 - 1.57 - 1.57 - 1.27) / 2  # ~ 8.3 cm

# ── Style helpers ─────────────────────────────────────────────────────────────
def set_font(run, name='Times New Roman', size=10, bold=False, italic=False, color=None):
    run.font.name = name
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    if color:
        run.font.color.rgb = RGBColor(*color)

def para(text, align=WD_ALIGN_PARAGRAPH.JUSTIFY, size=10, bold=False,
         italic=False, space_before=0, space_after=3, color=None):
    p = doc.add_paragraph()
    p.style = doc.styles['Normal']
    p.alignment = align
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after  = Pt(space_after)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    run = p.add_run(text)
    set_font(run, size=size, bold=bold, italic=italic, color=color)
    return p

def heading(text, level=1):
    sizes    = {1: 12, 2: 10, 3: 10}
    s_before = {1: 8,  2: 6,  3: 4}
    p = doc.add_paragraph()
    p.style = doc.styles['Normal']
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(s_before[level])
    p.paragraph_format.space_after  = Pt(3)
    run = p.add_run(text.upper() if level == 1 else text)
    if level == 3:
        run.italic = True
    set_font(run, size=sizes[level], bold=(level <= 2))
    return p

def bullet_item(text, size=10):
    p = doc.add_paragraph(style='List Bullet')
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after  = Pt(1)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    run = p.add_run(text)
    set_font(run, size=size)
    return p

def add_table(headers, rows, col_widths_cm, caption=None, caption_label=None):
    t = doc.add_table(rows=1 + len(rows), cols=len(headers))
    t.style = 'Table Grid'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr_cells = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr_cells[i].width = Cm(col_widths_cm[i])
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(h)
        set_font(run, size=8, bold=True, color=(255, 255, 255))
        tcPr = hdr_cells[i]._tc.get_or_add_tcPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear'); shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'), '1A3A5C')
        tcPr.append(shd)
    for ri, row_data in enumerate(rows):
        cells = t.rows[ri + 1].cells
        bg = 'F5F5F5' if ri % 2 == 0 else 'FFFFFF'
        for ci, val in enumerate(row_data):
            cells[ci].width = Cm(col_widths_cm[ci])
            p = cells[ci].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            bold = '**' in str(val)
            txt  = str(val).replace('**', '')
            run = p.add_run(txt)
            set_font(run, size=8, bold=bold)
            tcPr = cells[ci]._tc.get_or_add_tcPr()
            shd = OxmlElement('w:shd')
            shd.set(qn('w:val'), 'clear'); shd.set(qn('w:color'), 'auto')
            shd.set(qn('w:fill'), bg)
            tcPr.append(shd)
    if caption_label:
        cp = doc.add_paragraph()
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cp.paragraph_format.space_before = Pt(2)
        cp.paragraph_format.space_after  = Pt(6)
        r1 = cp.add_run(caption_label + ': ')
        set_font(r1, size=8, bold=True)
        if caption:
            r2 = cp.add_run(caption)
            set_font(r2, size=8, italic=True)
    return t

def add_figure(filename, caption_label, caption, width_cm=COL_W_CM):
    """Embed a result figure (scaled to column width) with an IEEE-style caption."""
    path = FIG_DIR / filename
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after  = Pt(2)
    if path.exists():
        p.add_run().add_picture(str(path), width=Cm(width_cm))
    else:
        r = p.add_run(f"[missing figure: {filename}]")
        set_font(r, size=8, italic=True, color=(180, 0, 0))
    cp = doc.add_paragraph()
    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cp.paragraph_format.space_after = Pt(6)
    r1 = cp.add_run(caption_label + '. ')
    set_font(r1, size=8, bold=True)
    r2 = cp.add_run(caption)
    set_font(r2, size=8, italic=True)

# ── TITLE ────────────────────────────────────────────────────────────────────
p_title = doc.add_paragraph()
p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
p_title.paragraph_format.space_after = Pt(6)
run_t = p_title.add_run(
    "SAGAM: A Multi-Modal Interpretable Survival-Aware\n"
    "Generalised Additive Meta-Learner for\n"
    "Lung Adenocarcinoma Prognosis")
set_font(run_t, size=20, bold=True, color=(26, 58, 92))

para("Lalit Kharel — Independent Researcher — [Department, Institution], "
     "[City, Country] — klalit.kharel@gmail.com",
     align=WD_ALIGN_PARAGRAPH.CENTER, size=10, italic=True, space_after=10)

# ── ABSTRACT ─────────────────────────────────────────────────────────────────
heading("Abstract", level=2)
abstract_text = (
    "Ensemble survival models routinely outperform classical Cox regression on lung "
    "adenocarcinoma (LUAD), but they purchase accuracy with opacity: a stacked ensemble "
    "reports one risk score and hides which component learner it trusted and where along the "
    "risk spectrum. We present SAGAM (Survival-Aware Generalised Additive Meta-Learner), a "
    "multi-modal stacking framework whose meta-learner is a B-spline generalised additive model "
    "(GAM). For each base learner k, SAGAM fits a smooth log-hazard contribution function "
    "f_k(s_k) over that learner's out-of-fold risk score. The shapes of these functions are the "
    "model's explanation: steep segments are trust zones where the ensemble relies on learner k, "
    "and flat segments mark where it is ignored — replacing the single scalar weight of linear "
    "stacking with a global, continuous, inspectable trust structure. SAGAM stacks five learners "
    "(RSF, GBS, XGBoost-Cox, a batch-normalised DeepSurv, and a gene-expression CoxNet) over a "
    "feature space fusing 16 clinical/molecular variables with a 10-gene panel. Under strict "
    "5-fold nested cross-validation on TCGA-LUAD (n=497, 180 events), Multi-Modal SAGAM reaches "
    "C=0.670 +/- 0.023, exceeding clinical-only (0.620 +/- 0.045; delta=+0.050) while halving "
    "fold variance, and expression-only (0.655 +/- 0.020). On independent GSE31210 (n=226) the "
    "expression model attains C=0.661 (log-rank p=8.5e-4); we also report a negative result on "
    "GSE68465 and trace it to gene dropout and platform shift. Risk tertiles separate median "
    "overall survival by 38.7 months. Code, figures, and trained artefacts are released."
)
para(abstract_text, size=9, space_after=4)
para("Keywords: Survival analysis, lung adenocarcinoma, ensemble stacking, generalised additive "
     "models, B-splines, interpretability, multi-modal integration, TCGA, concordance index.",
     size=9, italic=True, space_after=10)

# ── I. INTRODUCTION ──────────────────────────────────────────────────────────
heading("I. Introduction", level=1)
para(
    "Lung adenocarcinoma (LUAD) is the most common subtype of non-small-cell lung cancer, "
    "representing roughly 40% of lung cancer diagnoses and carrying a five-year survival below "
    "25% in advanced stages [1]. Even after EGFR/ALK targeted therapy and immune-checkpoint "
    "blockade, patients with identical TNM stage follow strikingly different trajectories, a "
    "direct consequence of molecular heterogeneity that anatomical staging cannot resolve. "
    "Better stratification is a prerequisite for allocating adjuvant therapy and surveillance.",
    size=10, space_after=4)
para(
    "Machine-learning survival models integrate stage, tumour mutational burden, "
    "genomic-instability indices, hypoxia scores, and transcriptomic profiles. Two tensions have "
    "limited their translation. First, the most accurate methods (random forests, boosting, deep "
    "networks) are opaque. Second, models tuned on a single cohort often collapse on external "
    "data because of platform differences, missing probes, and population shift. SAGAM addresses "
    "both at once by making the act of ensembling itself interpretable: instead of one scalar "
    "weight per base learner, it learns a smooth function f_k(s_k) whose derivative is a "
    "continuous read-out of trust. High-derivative segments are trust zones; flat segments mark "
    "learners the ensemble switches off. Contributions:",
    size=10, space_after=4)
bullet_item("Interpretable ensembling via B-spline trust functions: per-learner smooths form a "
            "global, visualisable trust structure that linear stacking and attention-weighted "
            "ensembles cannot produce. This is the primary contribution.")
bullet_item("Multi-modal integration with quantified benefit: fusing clinical features with a "
            "10-gene panel adds +0.050 C-index over clinical-only and halves fold variance "
            "(0.045 -> 0.023), evidence that expression stabilises the clinical signal.")
bullet_item("Honest external validation: two independent GEO cohorts, reporting both the success "
            "(GSE31210) and the failure (GSE68465) with identifiable causes.")

# Architecture note (TikZ diagram lives in the LaTeX source; described here).
para("Figure 1 (see sagam_paper.tex / poster) shows the architecture: five base learners feed "
     "leakage-free out-of-fold scores into a B-spline expansion and an elastic-net CoxNet GAM "
     "meta-learner, which emits both a risk score and the per-learner trust functions.",
     size=9, italic=True, space_after=6)

# ── II. RELATED WORK ─────────────────────────────────────────────────────────
heading("II. Related Work", level=1)
heading("A. Survival Models in Oncology", level=2)
para("The Cox proportional-hazards model [2] assumes a log-linear covariate-hazard relationship; "
     "CoxNet [3] adds LASSO/elastic-net regularisation for high-dimensional genomics. These are "
     "interpretable but cannot represent nonlinear interactions. RSF [4], GBS [5], XGBoost-Cox "
     "[6], and DeepSurv [7] recover such nonlinearity and improve discrimination, but each is a "
     "black box on its own.", size=10, space_after=4)
heading("B. Ensemble Stacking for Survival", level=2)
para("Stacking (super-learning) [8] trains a meta-learner on out-of-fold base predictions. For "
     "survival, linear CoxNet meta-learners [9] assign a single static weight per learner and so "
     "cannot express that a learner may be reliable in one region of the risk spectrum and "
     "uninformative in another. SAGAM makes those weights functions of the risk score.",
     size=10, space_after=4)
heading("C. Portability and Interpretability", level=2)
para("LUAD expression signatures [10],[11] suffer from cross-platform portability loss [12]; we "
     "measure this directly on two Affymetrix platforms. Post-hoc tools such as SHAP [13] and "
     "partial-dependence plots [14] explain single predictions of a fixed model but do not "
     "characterise the ensemble trust structure — how the combiner's reliance on each component "
     "varies with predicted risk. SAGAM's smooth functions fill that gap.", size=10, space_after=4)

# ── III. METHODOLOGY ─────────────────────────────────────────────────────────
heading("III. Methodology", level=1)
heading("A. Multi-Modal Feature Space", level=2)
bullet_item("Clinical (16): AJCC pathological stage, T/N/M substages, age, sex, grade, "
            "ethnicity, prior diagnosis, body weight, aneuploidy score, MSI-MANTIS, MSIsensor, "
            "TMB, tumour break load, and Buffa/Winter/Ragnum hypoxia scores.")
bullet_item("Expression (10 genes): DKK1, FAM83A, RHOV, IRX5, SFTA3, CD1B, PKP2, TNS4, LYPD3, "
            "TFAP2A — spanning immune (CD1B), invasion (RHOV, LYPD3), and Wnt/EGFR (DKK1, FAM83A) "
            "biology. RSEM counts are log2(x+1)-transformed.")
heading("B. Base-Learner Suite", level=2)
bullet_item("RSF: 200 trees, sqrt(p) features/split, min leaf 5.")
bullet_item("GBS: 200 stages, learning rate 0.05, max depth 3.")
bullet_item("XGBoost-Cox: eta=0.05, depth 3, row/col subsample 0.8, up to 300 rounds, early "
            "stopping patience 20.")
bullet_item("DeepSurv: 128->64 blocks with batch normalisation + ReLU + dropout(0.3); Adam "
            "(lr=1e-3, weight decay 1e-4), <=300 epochs, patience 25.")
bullet_item("ExprCox: elastic-net CoxNet (L1-ratio 0.9) on the 10-gene panel; alpha tuned on a "
            "20% internal split.")
heading("C. Leakage-Free Nested Cross-Validation", level=2)
bullet_item("Outer: 5-fold StratifiedKFold (on event indicator, seed 42).")
bullet_item("Early-stopping isolation: a disjoint 15% set is carved BEFORE the inner loop and "
            "used only for XGBoost/DeepSurv early stopping.")
bullet_item("Inner: 3-fold KFold on the remaining data produces the OOF score matrix.")
bullet_item("Meta-learner penalty tuned on a held-out 20% of OOF scores; test samples touch no "
            "fitting or tuning step. All preprocessing fit on training folds only.")
heading("D. B-Spline GAM Meta-Learner", level=2)
para("Each OOF score s_k is expanded into J=4 cubic B-spline bases (degree 3, no intercept); the "
     "concatenated matrix Z (5 learners x 4 = 20 features) feeds an elastic-net CoxNet "
     "(L1-ratio 0.9). The smooth contribution of learner k is:", size=10, space_after=3)
para("    f_k(s) = sum_j beta_kj * B_kj(s),    j = 1..4;    risk = sum_k f_k(s_k)",
     size=9, italic=True, space_after=4)
para("Large |f_k'(s)| marks a trust zone where the meta-learner relies on learner k; flat "
     "segments (f_k ~ 0) mean it is deferred. Each f_k is a single continuous curve over the "
     "whole risk range, giving a global account of ensemble behaviour distinct from per-patient "
     "attributions such as SHAP.", size=10, space_after=6)

# ── IV. EXPERIMENTAL SETUP ───────────────────────────────────────────────────
heading("IV. Experimental Setup", level=1)
heading("A. Datasets", level=2)
add_table(
    headers=["Cohort", "n", "Events", "Rate", "Platform"],
    rows=[
        ["TCGA-LUAD", "497", "180", "36.2%", "cBio + RNA-seq"],
        ["GSE31210", "226", "35", "15.5%", "Affy HG-U133A"],
        ["GSE68465", "432", "226", "52.3%", "Affy HG-U133 Plus 2.0"],
    ],
    col_widths_cm=[3.6, 1.0, 1.5, 1.7, 5.0],
    caption_label="TABLE I", caption="Dataset characteristics.")
para("Cohort note: the clinical cohort (valid endpoints, no expression requirement) comprises 501 "
     "patients (181 events). The multi-modal cohort is obtained by an inner join with RNA-seq, "
     "which drops the 4 patients lacking panel-gene expression (one an event), giving n=497 (180 "
     "events). All multi-modal, KM, and interpretability results use the 497-patient cohort; "
     "clinical-only baselines use the 501.", size=8, italic=True, space_after=6)
heading("B. Evaluation Metrics", level=2)
bullet_item("C-index [15]: primary discrimination (0.5 random; 0.65-0.70 clinically useful).")
bullet_item("Integrated Brier Score (IBS) [16]: calibration (0.25 = uninformative).")
bullet_item("IPCW time-dependent AUC [17] at 1/3/5 years; log-rank test for tertile separation; "
            "multivariate-Cox hazard ratios. External CIs from 1000-sample bootstrap.")
heading("C. Comparators", level=2)
para("Stage-only Cox; Clinical CoxNet; Clinical+Genomic CoxNet; individual base learners; linear "
     "stacking (CoxNet on raw scores, no spline); Clinical-only SAGAM; Expression-only CoxNet.",
     size=10, space_after=6)

# ── V. RESULTS ───────────────────────────────────────────────────────────────
heading("V. Results", level=1)
heading("A. Three-Way Nested-CV Comparison", level=2)
add_table(
    headers=["Model", "Mean C", "SD", "Δ vs Clin."],
    rows=[
        ["Expression-only", "0.6549", "0.0201", "+0.035"],
        ["Clinical-only SAGAM", "0.6197", "0.0447", "---"],
        ["**Multi-Modal SAGAM**", "**0.6700**", "**0.0225**", "**+0.050**"],
        ["Stage-only Cox", "0.6542", "0.0511", "+0.034"],
        ["Clinical CoxNet", "0.6455", "0.0279", "+0.026"],
        ["Clinical+Genomic CoxNet", "0.6412", "0.0322", "+0.022"],
        ["Linear Stacking", "0.6274", "0.0550", "+0.008"],
    ],
    col_widths_cm=[4.6, 1.5, 1.3, 1.9],
    caption_label="TABLE II",
    caption="Three-way nested-CV comparison on TCGA-LUAD (n=497, 180 events).")
para("Multi-Modal SAGAM (0.6700 +/- 0.0225) exceeds Clinical-only SAGAM (0.6197 +/- 0.0447) by "
     "+0.050 and Expression-only (0.6549 +/- 0.0201) by +0.015. Fold-level SD drops from 0.0447 "
     "to 0.0225 — a 50% variance reduction — so expression features stabilise the estimator in "
     "folds where clinical staging is weakly discriminative (per-fold range 0.635-0.700 vs the "
     "clinical 0.586-0.708).", size=10, space_after=4)

add_figure("model_comparison_bar.png", "Fig. 2",
           "Mean nested-CV C-index across models. SAGAM's gain over linear stacking isolates the "
           "contribution of the B-spline trust functions (same base learners and OOF scores).")

heading("B. Time-Dependent AUC and Calibration", level=2)
add_table(
    headers=["Model", "1-Yr", "3-Yr", "5-Yr"],
    rows=[
        ["Stage Cox", "0.700", "0.663", "0.619"],
        ["Clinical Cox", "0.664", "0.675", "0.653"],
        ["RSF", "0.667", "0.695", "0.705"],
        ["GBS", "0.640", "0.683", "0.636"],
        ["XGBoost-Cox", "0.515", "0.678", "0.628"],
        ["DeepSurv", "0.648", "0.678", "0.710"],
        ["Linear Stacking", "0.672", "0.688", "0.694"],
        ["SAGAM", "0.635", "0.632", "0.659"],
    ],
    col_widths_cm=[3.8, 1.7, 1.7, 1.7],
    caption_label="TABLE III",
    caption="IPCW time-dependent AUC at 1/3/5-year horizons (5-fold nested CV).")
para("SAGAM is competitive at 5 years (0.659) but lower at 1 year (0.635) than Stage Cox (0.700) "
     "and linear stacking (0.672), consistent with a rank-based Cox partial-likelihood objective "
     "that optimises long-horizon ordering over short-term probabilities. Component calibration "
     "is adequate (RSF IBS 0.188, GBS IBS 0.194, both below the uninformative 0.25).",
     size=10, space_after=4)
add_figure("calibration_curves.png", "Fig. 3",
           "Calibration at 1/3/5 years: observed Kaplan-Meier survival per risk-rank bin vs "
           "predicted ordering for the three configurations.")

heading("C. Kaplan-Meier Risk Stratification", level=2)
add_table(
    headers=["Group", "n", "Median OS", "HR vs High", "95% CI", "p"],
    rows=[
        ["Low", "~166", "71.5 mo", "0.375", "0.257-0.547", "<0.001"],
        ["Medium", "~166", "49.3 mo", "0.728", "0.521-1.017", "0.063"],
        ["High", "~165", "32.8 mo", "Ref.", "---", "---"],
    ],
    col_widths_cm=[1.8, 1.2, 2.2, 1.8, 2.4, 1.4],
    caption_label="TABLE IV",
    caption="Risk-tertile survival (Multi-Modal SAGAM, pooled OOF). Log-rank (Low vs High) p<0.001.")
add_figure("kaplan_meier_multimodal.png", "Fig. 4",
           "Kaplan-Meier curves for Multi-Modal SAGAM risk tertiles on TCGA-LUAD (pooled OOF "
           "scores). Log-rank (Low vs High) p<0.001.")

heading("D. Interpretability: Smooth Trust Functions", level=2)
para("Summing absolute spline-coefficient magnitude per learner, GBS dominates (~63%), followed "
     "by DeepSurv (~30%) and RSF (~7%), with XGBoost-Cox and ExprCox each below 1%. The GBS "
     "smooth is an S-curve — flat at low risk, a steep mid-range transition, and a high-risk "
     "plateau — the nonlinear weighting a single scalar cannot represent. Near-zero weight on "
     "XGBoost/ExprCox is itself informative: the meta-learner suppresses redundant signal rather "
     "than double-counting it.", size=10, space_after=3)
add_figure("interpretability_trust_zones.png", "Fig. 5",
           "Per-learner B-spline contribution functions f_k(s_k). Shaded bands are trust zones "
           "(|f_k'| > 30% of max); dashed grey lines are the linear-equivalent fit. The pie "
           "summarises relative contribution.")

heading("E. External Validation", level=2)
add_table(
    headers=["Cohort", "n", "Events", "C-SAGAM", "Log-rank p", "Verdict"],
    rows=[
        ["GSE31210", "226", "35", "**0.661**", "8.5e-4 ***", "pass"],
        ["GSE68465", "432", "226", "0.551", "0.093 NS", "fail"],
    ],
    col_widths_cm=[2.2, 1.0, 1.4, 1.9, 2.2, 1.5],
    caption_label="TABLE V",
    caption="External validation on two independent GEO cohorts (10-gene expression panel).")
para("On GSE31210 (HG-U133A) SAGAM reaches C=0.661 (bootstrap 95% CI 0.567-0.759), the best of "
     "all models on that cohort (DeepSurv 0.626; RSF 0.541; linear stacking 0.492), with log-rank "
     "p=8.5e-4. On GSE68465 (HG-U133 Plus 2.0) SAGAM attains only C=0.551 (p=0.093, NS). Three "
     "measurable causes: (i) gene dropout — 3/10 panel genes absent from the probe set; (ii) "
     "event-rate mismatch (52.3% vs 36.2%); (iii) platform batch effects. This matches the known "
     "portability problem in expression-based prognosis [12]; we report it rather than omit it.",
     size=10, space_after=4)

heading("F. Statistical Significance and Ablation", level=2)
para("Paired Wilcoxon signed-rank tests on the five fold-level C-indices: SAGAM vs Linear "
     "delta=+0.006 (p=0.31); vs DeepSurv delta=-0.002 (p=0.63); vs RSF delta=+0.014 (p=0.09). "
     "With only five paired observations these are underpowered; we present them transparently. "
     "A spline df ablation (clinical-only configuration, where absolute C is lower) confirms J=4: "
     "C = 0.557 (J=3), 0.578 (J=4), 0.549 (J=5), 0.498 (J=6) — J=4 optimal, higher J overfits.",
     size=10, space_after=6)

# ── VI. DISCUSSION ───────────────────────────────────────────────────────────
heading("VI. Discussion", level=1)
heading("A. Why Multi-Modal Fusion Helps", level=2)
para("The +0.050 gain with simultaneous halving of fold variance indicates the expression panel "
     "supplies information orthogonal to staging (immune CD1B; invasion RHOV/LYPD3; Wnt/EGFR "
     "DKK1/FAM83A). The variance reduction matters as much as the mean gain: a model reliable "
     "across folds is more trustworthy for deployment than one occasionally excellent.",
     size=10, space_after=4)
heading("B. Interpretability as the Core Contribution", level=2)
para("The functions f_k(s_k) are part of the model, not a post-hoc approximation. Unlike SHAP "
     "(one prediction at a time), the spline smooth is a global, continuous object: a clinician "
     "can read off, for a given risk score, which components the ensemble leans on and whether it "
     "is confident (steep) or deferring (flat). Automatic suppression of XGBoost/ExprCox reports "
     "redundancy in the base suite.", size=10, space_after=4)
heading("C. Limitations and Future Work", level=2)
bullet_item("External scope: GSE68465 shows platform portability is unresolved; probe-set "
            "imputation or quantile-normalisation transfer is needed before cross-platform use.")
bullet_item("Power: five outer folds limit significance; repeated nested CV would help.")
bullet_item("Short-horizon calibration: 1-year tdAUC lags rank-optimised baselines; an "
            "IPCW-weighted Brier meta-objective could close the gap.")
bullet_item("Biological validation: risk groups are not yet cross-referenced against EGFR/KRAS/ALK "
            "status. Future work: panel recalibration, mutation stratification, comparison with "
            "SurvTRACE [18]/DeepHit [19], and extension to LUSC and larger cohorts.")

# ── VII. CONCLUSION ──────────────────────────────────────────────────────────
heading("VII. Conclusion", level=1)
para("SAGAM is a multi-modal interpretable survival meta-learner whose B-spline GAM combiner "
     "exposes, rather than hides, how the ensemble forms its risk estimate. On TCGA-LUAD it "
     "attains C=0.670 +/- 0.023 under strict nested CV (+0.050 over clinical-only, with half the "
     "fold variance) and separates risk tertiles by 38.7 months of median survival. External "
     "validation confirms generalisability to a matched HG-U133A cohort (C=0.661, p=0.0008) and, "
     "just as informatively, characterises where it fails. The central contribution is the "
     "B-spline trust-function framework — a principled, visualisable account of nonlinear, "
     "score-dependent learner reliance that linear stacking cannot provide. Code, figures, and "
     "trained artefacts are released.", size=10, space_after=6)

# ── REFERENCES ───────────────────────────────────────────────────────────────
heading("References", level=1)
refs = [
    "[1] R. L. Siegel et al., \"Cancer statistics, 2024,\" CA Cancer J. Clin., vol. 74, pp. 12-49, 2024.",
    "[2] D. R. Cox, \"Regression models and life-tables,\" J. R. Stat. Soc. B, vol. 34, pp. 187-202, 1972.",
    "[3] N. Simon et al., \"Regularization paths for Cox's proportional hazards model,\" J. Stat. Softw., vol. 39, 2011.",
    "[4] H. Ishwaran et al., \"Random survival forests,\" Ann. Appl. Stat., vol. 2, pp. 841-860, 2008.",
    "[5] T. Hothorn et al., \"Survival ensembles,\" Biostatistics, vol. 7, pp. 355-373, 2006.",
    "[6] T. Chen and C. Guestrin, \"XGBoost: A scalable tree boosting system,\" KDD, 2016.",
    "[7] J. L. Katzman et al., \"DeepSurv,\" BMC Med. Res. Methodol., vol. 18, 2018.",
    "[8] M. J. van der Laan et al., \"Super learner,\" Stat. Appl. Genet. Mol. Biol., vol. 6, 2007.",
    "[9] E. C. Polley and M. J. van der Laan, \"Super learner in prediction,\" UC Berkeley Working Papers, 2010.",
    "[10] K. Shedden et al., \"Gene expression-based survival prediction in lung adenocarcinoma,\" Nat. Med., vol. 14, 2008.",
    "[11] D. G. Beer et al., \"Gene-expression profiles predict survival of lung adenocarcinoma,\" Nat. Med., vol. 8, 2002.",
    "[12] J. Luo et al., \"A comparison of batch effect removal methods,\" Pharmacogenomics J., vol. 10, 2010.",
    "[13] S. M. Lundberg and S.-I. Lee, \"A unified approach to interpreting model predictions,\" NeurIPS, 2017.",
    "[14] J. H. Friedman, \"Greedy function approximation: A gradient boosting machine,\" Ann. Stat., vol. 29, 2001.",
    "[15] F. E. Harrell et al., \"Evaluating the yield of medical tests,\" JAMA, vol. 247, pp. 2543-2546, 1982.",
    "[16] E. Graf et al., \"Assessment of prognostic classification schemes for survival data,\" Stat. Med., vol. 18, 1999.",
    "[17] H. Uno et al., \"Evaluating prediction rules for t-year survivors,\" J. Am. Stat. Assoc., vol. 102, 2007.",
    "[18] Z. Wang et al., \"SurvTRACE: Transformers for survival analysis,\" ACM BCB, 2022.",
    "[19] C. Lee et al., \"DeepHit: A deep learning approach to survival analysis,\" AAAI, 2018.",
]
for ref in refs:
    p = doc.add_paragraph()
    p.style = doc.styles['Normal']
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    r = p.add_run(ref)
    set_font(r, size=8)

# ── Save (fall through locked/open files to the next free name) ───────────────
candidates = [DOCX_PATH, OUT / "SAGAM_IEEE_Paper_v3.docx",
              OUT / "SAGAM_IEEE_Paper_v4.docx", OUT / "SAGAM_IEEE_Paper_v5.docx"]
for cand in candidates:
    try:
        doc.save(cand)
        DOCX_PATH = cand
        break
    except PermissionError:
        print(f"[!] {cand.name} is open/locked; trying next name...")
else:
    raise SystemExit("All candidate filenames are locked. Close the docs in Word and retry.")
print(f"[OK] Saved -> {DOCX_PATH}")
print(f"     Size: {DOCX_PATH.stat().st_size // 1024} KB")
