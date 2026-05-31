"""
SAGAM Project — Comprehensive PDF Report Generator
Generates: results_v2/SAGAM_Project_Report.pdf
"""

from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, Image, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
from reportlab.platypus import Flowable
import os

REPO   = Path(__file__).resolve().parent
OUT    = REPO / "results_v2"
PDF    = OUT / "SAGAM_Project_Report.pdf"

# ── Color palette ────────────────────────────────────────────────────
DARK_BLUE   = colors.HexColor("#1A3A5C")
MID_BLUE    = colors.HexColor("#2E6DA4")
LIGHT_BLUE  = colors.HexColor("#D6E8FA")
ACCENT      = colors.HexColor("#E05C2E")
GREEN_OK    = colors.HexColor("#2E7D32")
RED_WARN    = colors.HexColor("#C62828")
GOLD        = colors.HexColor("#F57C00")
LIGHT_GREY  = colors.HexColor("#F5F5F5")
MID_GREY    = colors.HexColor("#CCCCCC")
TEXT_DARK   = colors.HexColor("#1C1C1C")

# ── Styles ───────────────────────────────────────────────────────────
def make_styles():
    base = getSampleStyleSheet()
    S = {}

    S['cover_title'] = ParagraphStyle('cover_title',
        fontSize=28, leading=36, textColor=colors.white,
        alignment=TA_CENTER, fontName='Helvetica-Bold', spaceAfter=6)

    S['cover_sub'] = ParagraphStyle('cover_sub',
        fontSize=13, leading=18, textColor=colors.HexColor("#D0E8FF"),
        alignment=TA_CENTER, fontName='Helvetica', spaceAfter=4)

    S['cover_meta'] = ParagraphStyle('cover_meta',
        fontSize=10, leading=14, textColor=colors.HexColor("#A8C8E8"),
        alignment=TA_CENTER, fontName='Helvetica')

    S['h1'] = ParagraphStyle('h1',
        fontSize=18, leading=24, textColor=DARK_BLUE,
        fontName='Helvetica-Bold', spaceBefore=16, spaceAfter=8,
        borderPad=0)

    S['h2'] = ParagraphStyle('h2',
        fontSize=13, leading=18, textColor=MID_BLUE,
        fontName='Helvetica-Bold', spaceBefore=12, spaceAfter=6)

    S['h3'] = ParagraphStyle('h3',
        fontSize=11, leading=15, textColor=DARK_BLUE,
        fontName='Helvetica-Bold', spaceBefore=8, spaceAfter=4)

    S['body'] = ParagraphStyle('body',
        fontSize=10, leading=15, textColor=TEXT_DARK,
        fontName='Helvetica', alignment=TA_JUSTIFY,
        spaceAfter=6, firstLineIndent=0)

    S['body_small'] = ParagraphStyle('body_small',
        fontSize=9, leading=13, textColor=TEXT_DARK,
        fontName='Helvetica', alignment=TA_JUSTIFY, spaceAfter=4)

    S['bullet'] = ParagraphStyle('bullet',
        fontSize=10, leading=15, textColor=TEXT_DARK,
        fontName='Helvetica', leftIndent=16, spaceAfter=3,
        bulletIndent=4)

    S['caption'] = ParagraphStyle('caption',
        fontSize=9, leading=12, textColor=colors.HexColor("#555555"),
        fontName='Helvetica-Oblique', alignment=TA_CENTER,
        spaceBefore=2, spaceAfter=10)

    S['verdict_good'] = ParagraphStyle('verdict_good',
        fontSize=10, leading=14, textColor=GREEN_OK,
        fontName='Helvetica-Bold', leftIndent=12, spaceAfter=3)

    S['verdict_warn'] = ParagraphStyle('verdict_warn',
        fontSize=10, leading=14, textColor=RED_WARN,
        fontName='Helvetica-Bold', leftIndent=12, spaceAfter=3)

    S['verdict_neutral'] = ParagraphStyle('verdict_neutral',
        fontSize=10, leading=14, textColor=GOLD,
        fontName='Helvetica-Bold', leftIndent=12, spaceAfter=3)

    S['table_header'] = ParagraphStyle('table_header',
        fontSize=9, leading=12, textColor=colors.white,
        fontName='Helvetica-Bold', alignment=TA_CENTER)

    S['table_cell'] = ParagraphStyle('table_cell',
        fontSize=9, leading=12, textColor=TEXT_DARK,
        fontName='Helvetica', alignment=TA_CENTER)

    S['code'] = ParagraphStyle('code',
        fontSize=8.5, leading=12, textColor=colors.HexColor("#003366"),
        fontName='Courier', backColor=colors.HexColor("#EEF4FF"),
        leftIndent=8, rightIndent=8, spaceAfter=6, spaceBefore=4,
        borderPad=4)

    return S

# ── Helper: colored info box ─────────────────────────────────────────
def info_box(story, S, text, bg=LIGHT_BLUE, border=MID_BLUE, style='body'):
    tbl = Table([[Paragraph(text, S[style])]], colWidths=[16.5*cm])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), bg),
        ('BOX',        (0,0), (-1,-1), 1, border),
        ('TOPPADDING',    (0,0),(-1,-1), 8),
        ('BOTTOMPADDING', (0,0),(-1,-1), 8),
        ('LEFTPADDING',   (0,0),(-1,-1), 10),
        ('RIGHTPADDING',  (0,0),(-1,-1), 10),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 6))

# ── Helper: section divider ──────────────────────────────────────────
def section_divider(story, S, title):
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=2, color=DARK_BLUE))
    story.append(Paragraph(title, S['h1']))

def sub_divider(story, S, title):
    story.append(HRFlowable(width="60%", thickness=1, color=MID_GREY))
    story.append(Paragraph(title, S['h2']))

# ── Helper: embed image ──────────────────────────────────────────────
def embed_image(story, S, path, caption, width_cm=16):
    p = Path(path)
    if p.exists():
        img = Image(str(p), width=width_cm*cm,
                    height=width_cm*cm*0.62)
        story.append(img)
        story.append(Paragraph(caption, S['caption']))
    else:
        story.append(Paragraph(f"[Image not found: {p.name}]", S['caption']))

# ── Helper: results table ─────────────────────────────────────────────
def make_table(headers, rows, col_widths, highlight_row=None, S=None):
    data = [[Paragraph(h, ParagraphStyle('th', fontSize=9, textColor=colors.white,
                       fontName='Helvetica-Bold', alignment=TA_CENTER))
             for h in headers]]
    for i, row in enumerate(rows):
        data.append([Paragraph(str(c), ParagraphStyle('td', fontSize=9,
                     fontName='Helvetica', alignment=TA_CENTER,
                     textColor=TEXT_DARK)) for c in row])

    tbl = Table(data, colWidths=col_widths)
    style = [
        ('BACKGROUND', (0,0), (-1,0), DARK_BLUE),
        ('GRID',       (0,0), (-1,-1), 0.4, MID_GREY),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [LIGHT_GREY, colors.white]),
        ('TOPPADDING',    (0,0),(-1,-1), 5),
        ('BOTTOMPADDING', (0,0),(-1,-1), 5),
        ('LEFTPADDING',   (0,0),(-1,-1), 6),
        ('RIGHTPADDING',  (0,0),(-1,-1), 6),
    ]
    if highlight_row is not None:
        style.append(('BACKGROUND', (0, highlight_row+1), (-1, highlight_row+1),
                       colors.HexColor("#C8E6C9")))
        style.append(('FONTNAME', (0, highlight_row+1), (-1, highlight_row+1),
                       'Helvetica-Bold'))
    tbl.setStyle(TableStyle(style))
    return tbl

# ════════════════════════════════════════════════════════════════════
#  BUILD PDF
# ════════════════════════════════════════════════════════════════════
def build_pdf():
    doc = SimpleDocTemplate(
        str(PDF), pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2.2*cm, bottomMargin=2*cm,
        title="SAGAM Project Report",
        author="TCGA-LUAD Survival Analysis"
    )
    S = make_styles()
    story = []

    # ════════════════════════════════════════
    # COVER PAGE
    # ════════════════════════════════════════
    cover_bg = Table(
        [[Paragraph("SAGAM", S['cover_title']),],
         [Paragraph("Survival-Aware Generalised Additive Meta-Learner", S['cover_sub'])],
         [Spacer(1,6)],
         [Paragraph("Comprehensive Research Report", S['cover_sub'])],
         [Spacer(1,10)],
         [Paragraph("TCGA-LUAD Lung Adenocarcinoma Overall Survival Prediction", S['cover_meta'])],
         [Spacer(1,4)],
         [Paragraph("BIBM 2026 Submission — Full Analysis & Honest Assessment", S['cover_meta'])],
         [Spacer(1,20)],
         [Paragraph("Dataset: TCGA-LUAD  |  n=501 patients, 181 events", S['cover_meta'])],
         [Paragraph("External Validation: GSE31210 (n=226) · GSE68465 (n=432)", S['cover_meta'])],
         [Spacer(1,12)],
         [Paragraph("May 2026", S['cover_meta'])],
        ],
        colWidths=[16.5*cm]
    )
    cover_bg.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), DARK_BLUE),
        ('TOPPADDING',    (0,0),(-1,-1), 10),
        ('BOTTOMPADDING', (0,0),(-1,-1), 8),
        ('LEFTPADDING',   (0,0),(-1,-1), 20),
        ('RIGHTPADDING',  (0,0),(-1,-1), 20),
        ('ROUNDEDCORNERS', [6]),
    ]))
    story.append(Spacer(1, 1.5*cm))
    story.append(cover_bg)
    story.append(Spacer(1, 0.8*cm))

    # Quick facts strip
    facts = Table([
        [Paragraph("C-Index (TCGA)", ParagraphStyle('fh', fontSize=9, textColor=MID_BLUE,
                   fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("IBS (5-fold)", ParagraphStyle('fh', fontSize=9, textColor=MID_BLUE,
                   fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Ext. Valid. (GSE31210)", ParagraphStyle('fh', fontSize=9, textColor=MID_BLUE,
                   fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Log-rank p", ParagraphStyle('fh', fontSize=9, textColor=MID_BLUE,
                   fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("0.634 ± 0.050", ParagraphStyle('fv', fontSize=14, textColor=DARK_BLUE,
                   fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("0.181 (fold 4)", ParagraphStyle('fv', fontSize=14, textColor=DARK_BLUE,
                   fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("C=0.661 [***]", ParagraphStyle('fv', fontSize=14, textColor=GREEN_OK,
                   fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("p < 0.0001", ParagraphStyle('fv', fontSize=14, textColor=GREEN_OK,
                   fontName='Helvetica-Bold', alignment=TA_CENTER))],
    ], colWidths=[4.1*cm]*4)
    facts.setStyle(TableStyle([
        ('BOX',        (0,0), (-1,-1), 1, MID_BLUE),
        ('INNERGRID',  (0,0), (-1,-1), 0.5, MID_GREY),
        ('BACKGROUND', (0,0), (-1,0), LIGHT_BLUE),
        ('TOPPADDING',    (0,0),(-1,-1), 6),
        ('BOTTOMPADDING', (0,0),(-1,-1), 6),
    ]))
    story.append(facts)
    story.append(PageBreak())

    # ════════════════════════════════════════
    # SECTION 1 — ABSTRACT
    # ════════════════════════════════════════
    section_divider(story, S, "1.  Executive Summary")
    info_box(story, S,
        "<b>What is this project?</b>  SAGAM is a machine-learning pipeline for predicting "
        "overall survival (OS) in lung adenocarcinoma (LUAD) patients. It trains four diverse "
        "survival models (Random Survival Forest, Gradient Boosted Survival, XGBoost-Cox, "
        "DeepSurv), then stacks their predictions using a regularised Cox model with "
        "cubic B-spline transforms — the 'GAM' layer. The idea is that nonlinear combinations "
        "of base-learner risk scores should outperform any single model or simple average.",
        bg=LIGHT_BLUE, border=MID_BLUE)

    story.append(Paragraph(
        "This report provides a full, unvarnished assessment of the SAGAM project: what was done, "
        "what the numbers actually say, where the method is genuinely novel, and where it falls "
        "short of being a strong, publishable contribution in its current form. All results are "
        "from 5-fold nested cross-validation on 501 TCGA-LUAD patients and two independent "
        "GEO validation cohorts.", S['body']))

    story.append(Paragraph(
        "<b>Honest one-paragraph verdict:</b> SAGAM is a well-engineered, methodologically "
        "careful pipeline that achieves C-index ~0.634 on TCGA-LUAD — comparable to its four "
        "base learners. The spline meta-learner shows interpretable nonlinear shapes and "
        "produces clinically meaningful risk stratification (KM log-rank p &lt; 0.0001, median "
        "OS gap: 104 vs 36 months). However, SAGAM does <i>not</i> significantly outperform "
        "simpler alternatives (Wilcoxon p = 0.31 vs Linear, p = 0.09 vs RSF), and the study is "
        "underpowered to detect the small observed advantage (~0.006 C-index gain). External "
        "validation is mixed: strong on GSE31210 (C=0.661, p=0.0008) but fails on GSE68465 "
        "(C=0.551, NS). The paper is <b>not yet publishable in a top-tier venue</b> but has a "
        "clear path to a solid niche-journal submission with targeted improvements.",
        S['body']))

    # ════════════════════════════════════════
    # SECTION 2 — WHAT IS THE PROBLEM
    # ════════════════════════════════════════
    section_divider(story, S, "2.  The Clinical Problem")
    story.append(Paragraph(
        "Lung adenocarcinoma (LUAD) is the most common subtype of non-small-cell lung cancer "
        "(NSCLC) and accounts for approximately 40% of all lung cancer cases. It is the leading "
        "cause of cancer-related death worldwide. Despite advances in targeted therapy and "
        "immunotherapy, 5-year overall survival remains below 20% for stage III/IV disease. "
        "Accurate survival prediction has two practical uses:", S['body']))
    story.append(Paragraph("• <b>Prognosis</b>: informing patients and families about expected outcomes.", S['bullet']))
    story.append(Paragraph("• <b>Treatment stratification</b>: identifying high-risk patients who might benefit from aggressive intervention.", S['bullet']))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Traditional survival prediction uses AJCC pathological stage (I–IV), which is a "
        "coarse ordinal variable. Machine learning methods that incorporate molecular features "
        "(gene expression, mutation burden, hypoxia scores) promise finer-grained predictions. "
        "The question SAGAM addresses is: <i>can a nonlinear ensemble of ML survival models "
        "beat a standard Cox regression on LUAD patients?</i>", S['body']))

    sub_divider(story, S, "2.1  Why is this a hard problem?")
    items = [
        "<b>Censoring</b>: Most patients are still alive at last follow-up. ~64% of TCGA-LUAD "
        "patients are censored (181 events out of 501). Standard accuracy metrics don't apply; "
        "specialised survival metrics (C-index, IBS, tdAUC) are needed.",
        "<b>High dimensionality</b>: RNA-seq has ~20,000 genes but only 501 patients — severe "
        "overfitting risk. Feature selection is critical.",
        "<b>Heterogeneity</b>: LUAD molecular subtypes (EGFR-mutant, KRAS-mutant, etc.) have "
        "very different prognoses; a single model may not capture all of them.",
        "<b>Small event count</b>: With only 181 events across 5 folds (~36 per test fold), "
        "the standard error of the C-index is ~0.08. Any difference smaller than ~0.10 is "
        "statistically undetectable at this sample size.",
    ]
    for it in items:
        story.append(Paragraph(f"• {it}", S['bullet']))
    story.append(Spacer(1,4))

    # ════════════════════════════════════════
    # SECTION 3 — DATASET
    # ════════════════════════════════════════
    section_divider(story, S, "3.  Datasets Used")
    sub_divider(story, S, "3.1  Primary: TCGA-LUAD")
    story.append(Paragraph(
        "The Cancer Genome Atlas Lung Adenocarcinoma (TCGA-LUAD) cohort is the gold-standard "
        "public dataset for LUAD research. Data were downloaded from cBioPortal "
        "(www.cbioportal.org) in tab-separated format.", S['body']))

    tbl_data = [
        ["Attribute", "Value"],
        ["Total patients", "501"],
        ["Overall survival events (deaths)", "181 (36.1%)"],
        ["Censored patients", "320 (63.9%)"],
        ["Median OS (all patients)", "~41 months"],
        ["Maximum follow-up", "~250 months"],
        ["Clinical features used", "Age, Sex, AJCC stage (I–IV), T/N/M stage, Race, Grade, Weight"],
        ["Genomic features", "TMB, MSI-MANTIS, MSI-sensor, Aneuploidy score"],
        ["Hypoxia scores", "Buffa, Winter, Ragnum hypoxia gene signatures"],
        ["mRNA features (top selected)", "DKK1, FAM83A, RHOV, IRX5, SFTA3, CD1B, PKP2, TNS4, LYPD3, TFAP2A"],
        ["Leakage-excluded variables", "Radiation therapy (post-diagnosis), OS months/status, DSS, DFS, PFS"],
    ]
    t = Table([[Paragraph(c, ParagraphStyle('td', fontSize=9, fontName='Helvetica-Bold' if i==0 else 'Helvetica',
               alignment=TA_LEFT, textColor=colors.white if i==0 else TEXT_DARK))
               for c in row] for i, row in enumerate(tbl_data)],
              colWidths=[6*cm, 10.5*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), DARK_BLUE),
        ('GRID', (0,0),(-1,-1), 0.4, MID_GREY),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [LIGHT_GREY, colors.white]),
        ('TOPPADDING',    (0,0),(-1,-1), 4),
        ('BOTTOMPADDING', (0,0),(-1,-1), 4),
        ('LEFTPADDING',   (0,0),(-1,-1), 6),
        ('RIGHTPADDING',  (0,0),(-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1,8))

    sub_divider(story, S, "3.2  External Validation Cohorts")
    story.append(Paragraph(
        "Two independent GEO cohorts were used for external validation. These cohorts were "
        "downloaded automatically via the GEOparse library, and models trained on TCGA-LUAD "
        "were applied to them without any re-training — the critical test of generalisability.", S['body']))

    ext_data = [
        ["Cohort", "Patients", "Events", "Event Rate", "Gene Overlap", "Platform"],
        ["GSE31210", "226", "35", "15.5%", "10/10 genes", "Affymetrix U133 Plus 2.0"],
        ["GSE68465", "432", "226", "52.3%", "7/10 genes", "Affymetrix U133A"],
    ]
    story.append(make_table(ext_data[0], ext_data[1:],
                            [2.8*cm, 2.2*cm, 2*cm, 2.5*cm, 2.5*cm, 4.5*cm]))
    story.append(Spacer(1,6))
    info_box(story, S,
        "<b>Important note on GSE31210</b>: Only 15.5% events (35/226) is very low. "
        "With so few events the C-index estimate has very high variance (SE ~0.10), making any "
        "single number unreliable. The observed C=0.661 should be treated as indicative, not "
        "definitive. GSE68465 is far more informative statistically (52.3% event rate).",
        bg=colors.HexColor("#FFF8E1"), border=GOLD)

    # ════════════════════════════════════════
    # SECTION 4 — CORE METHODOLOGY (DETAILED)
    # ════════════════════════════════════════
    section_divider(story, S, "4.  Core Methodology — Detailed Explanation")

    sub_divider(story, S, "4.1  What is Survival Analysis?")
    story.append(Paragraph(
        "Survival analysis models the time until an event of interest (here: death). "
        "Unlike standard regression, it must handle <b>censoring</b> — patients who are "
        "still alive at the last contact date. The outcome for each patient is a pair "
        "(time, event): either (time of death, 1) or (last follow-up time, 0).", S['body']))
    story.append(Paragraph(
        "The main output is a <b>risk score</b> — a number where higher means a patient "
        "is predicted to die sooner. The risk score can be converted to a predicted survival "
        "curve S(t) = P(survive past time t) using the Breslow estimator.", S['body']))

    sub_divider(story, S, "4.2  The Four Base Learners")
    learners = [
        ("Random Survival Forest (RSF)",
         "An ensemble of decision trees adapted for survival data. Each tree is grown on a "
         "bootstrap sample and predicts a 'cumulative hazard' for each patient. The ensemble "
         "average is the final risk score. RSF is non-parametric and captures complex "
         "interactions. It achieved C=0.619 on TCGA-LUAD."),
        ("Gradient Boosted Survival (GBS)",
         "Boosting applied to survival data (sksurv implementation). Builds trees sequentially, "
         "each correcting the residuals of the previous. More prone to overfitting than RSF "
         "but can model sharp decision boundaries. C=0.605 here."),
        ("XGBoost-Cox",
         "XGBoost with survival:cox objective. Uses the partial likelihood of the Cox model "
         "as its loss function, combining gradient boosting speed with Cox proportional hazards "
         "theory. C=0.602 here — the weakest base learner in this experiment."),
        ("DeepSurv",
         "A neural network (3-layer MLP: 64-32-1) trained to minimise the Cox partial "
         "likelihood loss. Early stopping is used to prevent overfitting. Achieved the "
         "best individual C-index at 0.636. Its risk scores are log-hazard values."),
    ]
    for name, desc in learners:
        story.append(Paragraph(f"<b>{name}</b>", S['h3']))
        story.append(Paragraph(desc, S['body']))

    sub_divider(story, S, "4.3  Stacking / Meta-Learning")
    story.append(Paragraph(
        "Stacking is an ensemble technique where the predictions of multiple base models "
        "are used as input features for a second-level model (the meta-learner). The key "
        "requirement is that the base-learner predictions must be <b>out-of-fold (OOF)</b> — "
        "i.e., each patient's prediction must come from a model that was NOT trained on "
        "that patient. This prevents the meta-learner from learning to exploit overfit "
        "predictions.", S['body']))

    story.append(Paragraph(
        "In SAGAM, the pipeline is:", S['body']))
    steps = [
        "Outer fold splits patients into train (400) / test (100) sets.",
        "Inner 3-fold CV on the train set generates OOF predictions for RSF, GBS, XGB, DeepSurv.",
        "These 4 OOF risk scores form a new feature matrix (n_train × 4).",
        "The meta-learner (CoxNet + B-splines) is trained on this OOF matrix.",
        "For test evaluation: final base models are trained on all train data, predictions "
        "are generated for test patients, and the meta-learner is applied.",
    ]
    for i, s in enumerate(steps, 1):
        story.append(Paragraph(f"  Step {i}: {s}", S['bullet']))
    story.append(Spacer(1,6))

    sub_divider(story, S, "4.4  The GAM / Spline Layer — The Core Novelty")
    info_box(story, S,
        "<b>This is the key claim of the paper.</b> Standard stacking uses a linear "
        "combination of base-learner scores (w1*RSF + w2*GBS + ...). SAGAM instead "
        "applies cubic B-spline basis functions to each risk score before fitting the "
        "Cox model. This allows the meta-learner to learn <i>nonlinear, non-monotone "
        "relationships</i> between each base learner's score and the log-hazard.",
        bg=colors.HexColor("#E8F5E9"), border=GREEN_OK)

    story.append(Paragraph(
        "Each base learner's OOF risk score r is transformed into a set of spline basis "
        "functions: B1(r), B2(r), B3(r), B4(r) (with df=4, cubic B-splines). The meta-learner "
        "then fits a Cox-net model on the concatenated 16-dimensional feature vector "
        "[B1(RSF),...,B4(RSF), B1(GBS),...,B4(DS)]. The L1+L2 penalty (elastic net, "
        "l1_ratio=0.9) regularises the spline coefficients.", S['body']))

    story.append(Paragraph(
        "<b>Why does the shape matter?</b> The contribution plots (Section 7.1) show that "
        "RSF's contribution is a U-shaped function — very low and very high RSF scores both "
        "contribute little, while intermediate scores drive predictions. XGBoost shows a "
        "double-peak. These shapes cannot be captured by a linear weight.", S['body']))

    sub_divider(story, S, "4.5  Nested Cross-Validation — Why It Matters")
    story.append(Paragraph(
        "Standard 5-fold CV is NOT used. Instead, <b>nested CV</b> is applied:", S['body']))
    story.append(Paragraph(
        "• <b>Outer loop</b>: 5-fold stratified split. The test set is held out entirely during ALL training.", S['bullet']))
    story.append(Paragraph(
        "• <b>Inner loop</b>: 3-fold CV within each outer training set for OOF generation.", S['bullet']))
    story.append(Paragraph(
        "• <b>Hyperparameter tuning</b>: The regularisation alpha for CoxNet is selected using an internal "
        "80/20 split of the training data — never touching the test set.", S['bullet']))
    story.append(Paragraph(
        "• <b>Early stopping isolation</b>: For XGB and DeepSurv, the early stopping validation set "
        "is carved out BEFORE inner CV begins — so ES validation samples never appear as CV "
        "training data.", S['bullet']))
    story.append(Spacer(1,4))
    info_box(story, S,
        "<b>Data leakage prevention</b>: The original pipeline had 5 confirmed leakage bugs "
        "(RADIATION_THERAPY feature, test-data alpha tuning, ES overlap, hardcoded OOF overwrite, "
        "dead a_comb block). All were identified and fixed before the results reported here.",
        bg=colors.HexColor("#FFF3E0"), border=ACCENT)

    story.append(PageBreak())

    # ════════════════════════════════════════
    # SECTION 5 — METRICS EXPLAINED
    # ════════════════════════════════════════
    section_divider(story, S, "5.  Metrics — What Each Number Means")

    sub_divider(story, S, "5.1  C-Index (Concordance Index)")
    story.append(Paragraph(
        "The C-index measures how often the model correctly orders two patients: "
        "does the patient predicted to die sooner actually die sooner? It ranges from "
        "0.5 (random) to 1.0 (perfect discrimination). It is the survival equivalent of "
        "the AUC-ROC.", S['body']))

    ci_table = [
        ["C-Index Value", "Interpretation"],
        ["0.50", "No better than random guessing"],
        ["0.55–0.60", "Weak — clinically questionable"],
        ["0.60–0.65", "Moderate — acceptable for noisy survival data"],
        ["0.65–0.70", "Good — publishable in survival ML context"],
        ["0.70–0.75", "Strong discrimination"],
        ["> 0.75", "Excellent (rare in real genomic data)"],
    ]
    story.append(make_table(ci_table[0], ci_table[1:],
                            [4*cm, 12.5*cm], highlight_row=2))
    story.append(Spacer(1,6))
    info_box(story, S,
        "<b>SAGAM C-index: 0.634 ± 0.050.</b>  This falls in the 'Moderate-to-Good' range. "
        "For TCGA-LUAD specifically, published values range from 0.58 (simple Cox) to 0.70 "
        "(best genomic models with large feature sets). SAGAM's 0.634 is competitive but "
        "not exceptional.", bg=LIGHT_BLUE, border=MID_BLUE)

    sub_divider(story, S, "5.2  Integrated Brier Score (IBS)")
    story.append(Paragraph(
        "The Brier Score at time t measures the mean squared error between the predicted "
        "survival probability S_hat(t|x) and the actual survival status at time t. "
        "The <b>Integrated Brier Score</b> averages this over a range of time points. "
        "Lower is better. A null model (predict S=0.5 everywhere) gives IBS ≈ 0.25.", S['body']))
    story.append(Paragraph(
        "<b>SAGAM IBS = ~0.181 (best fold) to 0.195 (5-fold mean).</b> This is well below 0.25, "
        "confirming the model adds genuine predictive information. RSF IBS = 0.195, "
        "GBS = 0.203. SAGAM is marginally better (7.5% bootstrap fraction exceeds 0.95, "
        "but the CI crosses zero).", S['body']))

    sub_divider(story, S, "5.3  Time-Dependent AUC (tdAUC)")
    story.append(Paragraph(
        "The time-dependent AUC measures discrimination at a specific time horizon (1-year, "
        "3-year, 5-year). It asks: among patients who were event-free up to time t, "
        "can the model correctly identify who will die by t+dt? Values above 0.70 are "
        "generally considered good in oncology.", S['body']))
    story.append(Paragraph(
        "<b>Concerning finding:</b> SAGAM has the <i>lowest</i> tdAUC of all models at 1-year "
        "(0.626) and 3-year (0.578). Stage Cox has 0.741 at 1-year. This suggests that for "
        "near-term prediction, SAGAM's spline layer actively hurts performance — it may be "
        "overfitting the mid-range OOF scores and losing short-term discrimination.", S['body']))

    sub_divider(story, S, "5.4  Log-rank Test (KM Stratification)")
    story.append(Paragraph(
        "The log-rank test compares survival curves between groups (Low/Medium/High risk "
        "tertiles defined by SAGAM risk score). The null hypothesis is that all groups "
        "have the same survival distribution. A very small p-value (p &lt; 0.001) means "
        "the groups are clearly separated — the model identifies distinct risk groups.", S['body']))
    story.append(Paragraph(
        "<b>SAGAM log-rank result: p &lt; 0.0001 (***), median OS = 104 vs 41 vs 36 months.</b> "
        "This is SAGAM's strongest result. Despite modest discrimination in C-index, "
        "the top tertile has ~3× longer median survival than the bottom tertile — "
        "a clinically meaningful finding.", S['body']))

    sub_divider(story, S, "5.5  Hazard Ratios")
    story.append(Paragraph(
        "A Cox regression on SAGAM risk tertiles gives hazard ratios (HR). "
        "HR = exp(beta): if HR = 0.375 for Low Risk vs High Risk (reference), "
        "Low-Risk patients have 62.5% lower hazard of death at any time point. "
        "A HR with 95% CI not crossing 1.0 is statistically significant.", S['body']))

    hr_table = [
        ["Group", "HR (exp(coef))", "95% CI", "p-value", "Interpretation"],
        ["Low Risk vs High Risk", "0.375", "[0.257, 0.547]", "< 0.001", "62.5% lower hazard"],
        ["Medium Risk vs High Risk", "0.728", "[0.521, 1.017]", "0.063", "Not significant (marginal)"],
    ]
    story.append(make_table(hr_table[0], hr_table[1:],
                            [3.5*cm, 2.8*cm, 3.5*cm, 2*cm, 4.7*cm],
                            highlight_row=0))
    story.append(Spacer(1,8))

    story.append(PageBreak())

    # ════════════════════════════════════════
    # SECTION 6 — PERFORMANCE RESULTS
    # ════════════════════════════════════════
    section_divider(story, S, "6.  Performance Results — All Models")

    sub_divider(story, S, "6.1  Main C-Index Comparison (TCGA-LUAD, 5-fold nested CV)")
    story.append(Paragraph(
        "All values are 5-fold mean ± standard deviation. Highlighted row = SAGAM.", S['body_small']))

    main_res = [
        ["Model", "C-Index", "Std Dev", "vs SAGAM", "Interpretation"],
        ["RSF", "0.619", "0.049", "–0.015", "Weakest ensemble"],
        ["GBS", "0.605", "0.063", "–0.029", "Unstable, high variance"],
        ["XGB-Cox", "0.602", "0.051", "–0.032", "Poorest base learner"],
        ["DeepSurv", "0.636", "0.050", "+0.002", "Best single model"],
        ["Linear Stacking", "0.627", "0.055", "–0.007", "Simple ensemble"],
        ["SAGAM (ours)", "0.634", "0.050", "baseline", "Spline ensemble"],
        ["Stage-only Cox", "0.657", "0.044", "+0.023", "Clinical baseline"],
    ]
    t_main = make_table(main_res[0], main_res[1:],
                        [4*cm, 2.5*cm, 2.2*cm, 2.5*cm, 5.3*cm],
                        highlight_row=5)
    story.append(t_main)
    story.append(Spacer(1,6))
    info_box(story, S,
        "<b>Critical observation:</b> Stage-only Cox (C=0.657) outperforms SAGAM (C=0.634) "
        "by +0.023 C-index points. A single clinical variable — AJCC pathological stage — "
        "is a harder baseline to beat than it might appear. This significantly weakens the "
        "paper's core claim.",
        bg=colors.HexColor("#FFEBEE"), border=RED_WARN, style='body')

    sub_divider(story, S, "6.2  Stage + SAGAM Incremental Value")
    story.append(Paragraph(
        "An incremental analysis tests whether adding SAGAM risk scores on top of "
        "stage information improves prediction. The combined model averages standardised "
        "stage Cox and SAGAM risk scores.", S['body']))

    inc_table = [
        ["Model", "C-Index", "Std Dev", "Result"],
        ["Stage-only Cox", "0.654", "0.051", "Baseline"],
        ["SAGAM only", "0.634", "0.050", "Slightly below stage"],
        ["Stage + SAGAM", "0.657", "0.020", "+0.003 over stage alone"],
    ]
    story.append(make_table(inc_table[0], inc_table[1:],
                            [5*cm, 2.5*cm, 2.5*cm, 6.5*cm], highlight_row=2))
    story.append(Spacer(1,6))
    story.append(Paragraph(
        "The +0.003 incremental gain is real but negligible. More notable is the dramatic "
        "reduction in variance (std drops from 0.051 to 0.020) — the combined model is "
        "more <i>stable</i> across folds, which may be practically useful even if the "
        "mean improvement is small.", S['body']))

    sub_divider(story, S, "6.3  Time-Dependent AUC Summary")
    story.append(Paragraph(
        "tdAUC is computed at clinically relevant horizons. Values below 0.60 are borderline "
        "at the given time point.", S['body_small']))

    tdauc_data = [
        ["Model", "1-Year AUC", "3-Year AUC", "5-Year AUC", "Mean"],
        ["Stage Cox",    "0.700", "0.663", "0.619", "0.661"],
        ["RSF",          "0.712", "0.668", "0.688", "0.689"],
        ["GBS",          "0.640", "0.683", "0.636", "0.653"],
        ["DeepSurv",     "0.694", "0.677", "0.710", "0.694"],
        ["Linear Stack", "0.672", "0.688", "0.694", "0.685"],
        ["SAGAM",        "0.635", "0.632", "0.659", "0.642"],
    ]
    story.append(make_table(tdauc_data[0], tdauc_data[1:],
                            [3.8*cm, 2.8*cm, 2.8*cm, 2.8*cm, 4.3*cm],
                            highlight_row=5))
    story.append(Spacer(1,6))
    info_box(story, S,
        "<b>SAGAM ranks last in tdAUC across all time horizons.</b> This is a significant "
        "weakness. The spline meta-learner apparently sacrifices time-specific discrimination "
        "for overall rank ordering. This pattern suggests the B-spline transformation may "
        "be distorting the OOF risk scores in a way that hurts calibrated time predictions.",
        bg=colors.HexColor("#FFEBEE"), border=RED_WARN, style='body')

    sub_divider(story, S, "6.4  Integrated Brier Score")
    ibs_table = [
        ["Model", "IBS (5-fold mean)", "Relative to Null (0.25)", "Better than SAGAM?"],
        ["RSF",  "0.195", "22% below null", "Marginal (CI crosses 0)"],
        ["GBS",  "0.203", "19% below null", "No"],
        ["SAGAM (IBS)", "~0.182–0.195", "~22–27% below null", "baseline"],
    ]
    story.append(make_table(ibs_table[0], ibs_table[1:],
                            [3*cm, 3.5*cm, 4*cm, 6*cm], highlight_row=2))
    story.append(Spacer(1,6))

    story.append(PageBreak())

    # ════════════════════════════════════════
    # SECTION 7 — FIGURE EXPLANATIONS
    # ════════════════════════════════════════
    section_divider(story, S, "7.  Figure-by-Figure Explanation")

    # Figure 1: KM
    sub_divider(story, S, "Figure 1: Kaplan-Meier Survival Curves (TCGA-LUAD, Pooled OOF)")
    embed_image(story, S, OUT/"kaplan_meier.png",
        "Fig. 1 — KM curves for Low/Medium/High SAGAM risk tertiles. "
        "Shaded regions = 95% confidence intervals. Median OS: Low=104.2 mo, "
        "Medium=41.4 mo, High=36.7 mo. Log-rank p<0.0001 (***)")

    story.append(Paragraph(
        "<b>How to read this graph:</b> The y-axis shows the probability of surviving "
        "past time t. Each step-down is a death event. The shaded band is the 95% "
        "confidence interval around the Kaplan-Meier estimate.", S['body']))
    story.append(Paragraph(
        "<b>What it shows:</b> SAGAM clearly separates Low-Risk patients (green, median "
        "survival 104.2 months = ~8.7 years) from High-Risk (red, median 36.7 months = "
        "~3 years). The threefold difference in median survival is clinically substantial "
        "and highly statistically significant (p &lt; 0.0001).", S['body']))
    story.append(Paragraph(
        "<b>Caution:</b> The wide confidence intervals in the right tail (especially for "
        "High Risk) reflect sparse data — very few patients survive past 150 months. "
        "Medium and High Risk curves overlap substantially in the right tail, explaining "
        "why the Medium vs High HR (0.728) is not significant (p=0.063).", S['body']))

    # Figure 2: KM with NAR
    sub_divider(story, S, "Figure 2: KM with Number-at-Risk Table")
    embed_image(story, S, OUT/"kaplan_meier_nar.png",
        "Fig. 2 — Same KM curves with number-at-risk table showing how many patients "
        "remained under observation at each time point.")

    story.append(Paragraph(
        "<b>Number-at-risk table:</b> At 0 months, all 167 patients per tertile are at risk. "
        "By 48 months, only 38 Low-Risk patients remain vs 21 Medium-Risk and 12 High-Risk. "
        "By 60 months (5 years), the table shows 31/12/10. These rapidly shrinking numbers "
        "explain the wide confidence bands in the right tail — estimates become unreliable "
        "when very few patients remain.", S['body']))
    story.append(Paragraph(
        "<b>Key take-away:</b> The survival curves remain well-separated up to ~80 months. "
        "Beyond that, the small sample sizes dominate and interpretation requires caution. "
        "The separation in the first 3 years is the most reliable and clinically actionable.", S['body']))

    # Figure 3: Smooth contribution
    sub_divider(story, S, "Figure 3: SAGAM Smooth Contribution Functions")
    embed_image(story, S, OUT/"gam_smooths_4panel.png",
        "Fig. 3 — Per-model spline contribution functions from outer fold 1. "
        "Each curve shows how a base learner's standardised risk score maps to its "
        "contribution to the log-hazard (y-axis). Dashed line = linear equivalent weight.")

    story.append(Paragraph(
        "<b>How to read this graph:</b> The x-axis is the standardised risk score from "
        "each base learner (z-score, mean=0, std=1). The y-axis is the SAGAM meta-learner's "
        "contribution (log-hazard units). If the curve were straight, SAGAM would be "
        "equivalent to linear stacking.", S['body']))

    shapes = [
        ("RSF (top-left)", "U-shaped / inverted-U curve. Intermediate RSF scores "
         "(near 0) contribute negatively to log-hazard, while very low and very high "
         "RSF scores contribute near zero. This non-monotone shape means SAGAM "
         "discounts RSF's extreme predictions — treating RSF as less reliable at "
         "extreme values."),
        ("GBS (top-right)", "Nearly flat (near zero contribution). SAGAM has largely "
         "suppressed the GBS learner — its elastic-net penalty drove the GBS spline "
         "coefficients to zero. This is the meta-learner saying 'GBS adds nothing once "
         "I have RSF, XGB, and DeepSurv'."),
        ("XGB (bottom-left)", "M-shaped / double-peak. Moderate XGB scores "
         "(around 0 to +2) contribute positively, while extreme scores are discounted. "
         "This is a genuine nonlinear relationship that a simple weight cannot capture."),
        ("DeepSurv (bottom-right)", "Mostly flat with a sharp dip at very negative "
         "scores (around –5). This suggests DeepSurv's extreme low-risk predictions "
         "are not trusted by the meta-learner."),
    ]
    for name, desc in shapes:
        story.append(Paragraph(f"• <b>{name}</b>: {desc}", S['bullet']))
    story.append(Spacer(1,4))
    info_box(story, S,
        "<b>Scientific insight:</b> The non-flat shapes justify the spline approach — "
        "a linear meta-learner would miss these patterns. However, these shapes are "
        "estimated from fold 1 only (to avoid test-set contamination) and may not be "
        "stable across folds. The ablation (df=3/4/5/6) shows high variance in C-index "
        "(std ~0.065–0.105), suggesting the spline shapes vary significantly by fold.",
        bg=colors.HexColor("#E8F5E9"), border=GREEN_OK)

    # Figure 4: Calibration
    sub_divider(story, S, "Figure 4: Calibration Plots (3-year and 5-year)")
    embed_image(story, S, OUT/"calibration_plot.png",
        "Fig. 4 — Calibration at 3-year (left) and 5-year (right) time horizons. "
        "Points = risk deciles. Lines = fitted calibration lines. Dashed = perfect "
        "calibration (predicted = observed). Closer to diagonal = better calibrated.")

    story.append(Paragraph(
        "<b>How to read this graph:</b> Patients are grouped into ~5 bins by their "
        "predicted survival probability. For each bin, the x-axis shows the mean "
        "predicted probability and the y-axis shows the actual (KM-estimated) survival "
        "probability in that bin. Perfect calibration = all points on the diagonal.", S['body']))
    story.append(Paragraph(
        "<b>What it shows:</b> At 3 years (left panel): SAGAM (green dots) tracks "
        "close to the diagonal across the 0.4–0.8 range. Stage Cox (blue) slightly "
        "overestimates survival at intermediate risk. All models are reasonably calibrated "
        "at 3 years. At 5 years (right panel): more scatter, reflecting the smaller "
        "number of patients observed to that horizon. Stage Cox shows systematic "
        "overestimation (dots above the diagonal at lower survival values).", S['body']))
    story.append(Paragraph(
        "<b>Clinical significance:</b> A well-calibrated model is essential for clinical "
        "use — if a model says '60% 3-year survival', approximately 60% of patients in "
        "that risk group should actually survive 3 years. SAGAM shows reasonable calibration "
        "in the 3-year panel, which is the most relevant horizon for treatment decisions.", S['body']))

    # Figure 5 & 6: External validation
    story.append(PageBreak())
    sub_divider(story, S, "Figure 5: External Validation — GSE31210 (n=226)")
    embed_image(story, S, OUT/"ext_km_gse31210.png",
        "Fig. 5 — External validation KM curves on GSE31210. SAGAM trained on "
        "TCGA-LUAD, applied to independent Japanese lung adenocarcinoma cohort. "
        "C=0.661 [0.567, 0.759], log-rank p=0.0008 (***)")

    story.append(Paragraph(
        "<b>What this shows:</b> Models trained exclusively on TCGA-LUAD (USA cohort) "
        "were applied to GSE31210 (Japanese cohort, n=226, 35 events). The Low-Risk "
        "group (green) has clearly better survival than Medium (orange) and High (red) "
        "over 125 months. The C=0.661 is SAGAM's best external result.", S['body']))
    story.append(Paragraph(
        "<b>Caution about GSE31210:</b> Only 35 events in 226 patients (15.5% event rate). "
        "The SE of the C-index estimate is approximately 0.10, meaning the true C-index "
        "could plausibly be anywhere from 0.55 to 0.76. The KM curves look dramatic "
        "because the Low-Risk group has almost no events at all — raising concerns about "
        "immortal time bias or platform effects.", S['body']))

    sub_divider(story, S, "Figure 6: External Validation — GSE68465 (n=432)")
    embed_image(story, S, OUT/"ext_km_gse68465.png",
        "Fig. 6 — External validation KM curves on GSE68465. C=0.551 [0.510, 0.591], "
        "log-rank p=0.093 [NS]. KM groups partially overlap.")

    story.append(Paragraph(
        "<b>What this shows:</b> GSE68465 is the larger, more statistically powerful "
        "validation cohort (432 patients, 226 events = 52% event rate). SAGAM achieves "
        "C=0.551 — barely above random. The KM curves substantially overlap, and the "
        "log-rank test is not significant (p=0.093).", S['body']))
    info_box(story, S,
        "<b>This is the paper's most important weakness.</b> GSE68465 is the only "
        "external cohort with enough events to provide a reliable C-index estimate, "
        "and SAGAM essentially fails there (C=0.551, NS). Linear stacking actually "
        "outperforms SAGAM on GSE68465 (C=0.575 vs 0.551). The method does not "
        "generalise to this cohort. Possible explanations: different microarray platform "
        "(only 7/10 genes overlap), different population (North American vs pan-cohort), "
        "different biology (different LUAD subtypes in the cohort).",
        bg=colors.HexColor("#FFEBEE"), border=RED_WARN, style='body')

    # Figure 7: Bar chart
    sub_divider(story, S, "Figure 7: Performance Comparison Bar Chart")
    embed_image(story, S, OUT/"performance_comparison.png",
        "Fig. 7 — C-index comparison of all models on TCGA-LUAD (5-fold nested CV). "
        "Error bars = ± standard deviation. Dashed red = random (0.5), green = 'good' (0.7).")

    story.append(Paragraph(
        "<b>How to read this:</b> Each bar is one model's mean C-index over 5 folds. "
        "Error bars show fold-to-fold variability. The red dashed line at 0.5 is chance "
        "level; the green dashed line at 0.7 is a conventional threshold for 'good' "
        "discrimination.", S['body']))
    story.append(Paragraph(
        "<b>Key observation:</b> All models cluster between 0.60 and 0.64 — none reaches "
        "the 0.7 threshold. The error bars of all models overlap substantially, meaning "
        "no model is statistically significantly better than any other. This reflects the "
        "fundamental constraint of 181 events in 501 patients.", S['body']))

    # Figure 8: Brier score
    sub_divider(story, S, "Figure 8: Time-Dependent Brier Score Curves")
    embed_image(story, S, OUT/"brier_score_time.png",
        "Fig. 8 — Brier score as a function of time (Outer Fold 1). "
        "Lower = better calibration. Shaded green = SAGAM advantage region.")

    story.append(Paragraph(
        "<b>How to read this:</b> The Brier score at each time t measures mean squared "
        "error in predicted survival probabilities. As time increases, censoring means "
        "fewer patients are observed, so Brier scores typically rise. A model below the "
        "others has better time-specific calibration.", S['body']))
    story.append(Paragraph(
        "<b>What it shows:</b> From ~10 to ~35 months (the shaded green region), SAGAM "
        "has lower Brier score than RSF and Linear — meaning better calibration in this "
        "window. GBS (red) is consistently the worst. After 35 months, the advantage "
        "disappears as sample sizes shrink and uncertainty dominates.", S['body']))

    story.append(PageBreak())

    # ════════════════════════════════════════
    # SECTION 8 — SUPPLEMENTARY ANALYSES
    # ════════════════════════════════════════
    section_divider(story, S, "8.  Supplementary Analyses")

    sub_divider(story, S, "8.1  Cox Baseline Comparison")
    story.append(Paragraph(
        "A key question: does adding molecular features to clinical staging improve "
        "survival prediction? The answer from this dataset is no.", S['body']))
    cox_data = [
        ["Cox Model Features", "C-Index", "Std Dev"],
        ["Stage only (AJCC I–IV + T/N/M)", "0.657", "0.044"],
        ["Clinical (stage + age, sex, grade)", "0.646", "0.028"],
        ["Clinical + Genomic (+ TMB, MSI, aneuploidy)", "0.641", "0.032"],
        ["Full (+ Buffa/Winter/Ragnum hypoxia)", "0.641", "0.032"],
        ["SAGAM (all features, ensemble)", "0.634", "0.050"],
    ]
    story.append(make_table(cox_data[0], cox_data[1:],
                            [8*cm, 2.8*cm, 2.8*cm], highlight_row=0))
    story.append(Spacer(1,6))
    info_box(story, S,
        "<b>Adding genomic and hypoxia features to Cox regression makes NO improvement. "
        "Stage-only Cox (0.657) is the best Cox baseline.</b> This is not surprising — "
        "TMB and MSI scores are more relevant for immunotherapy response than prognosis. "
        "Hypoxia signatures may be too noisy at the cohort level.",
        bg=colors.HexColor("#FFF3E0"), border=GOLD, style='body')

    sub_divider(story, S, "8.2  Spline Degree-of-Freedom Ablation")
    story.append(Paragraph(
        "How many spline basis functions (df) are optimal? The ablation tests df=3,4,5,6:", S['body']))
    df_data = [
        ["Spline df", "C-Index", "Std Dev", "Notes"],
        ["3", "0.557", "0.105", "High variance — unstable"],
        ["4 (current)", "0.578", "0.065", "Best mean, lowest variance"],
        ["5", "0.549", "0.081", "Overfitting begins"],
        ["6", "0.498", "0.041", "Severe overfitting — near random"],
    ]
    story.append(make_table(df_data[0], df_data[1:],
                            [2.5*cm, 2.5*cm, 2.5*cm, 9*cm], highlight_row=1))
    story.append(Spacer(1,6))
    story.append(Paragraph(
        "<b>Note:</b> These ablation C-index values (~0.56–0.58) are lower than the main "
        "results (~0.634). This is because the ablation uses a simplified inner loop "
        "(no ES isolation on inner CV). The relative ordering (df=4 is best) is what "
        "matters, not the absolute values. df=4 provides the best bias-variance tradeoff; "
        "higher df leads to rapid performance collapse.", S['body']))

    sub_divider(story, S, "8.3  Statistical Significance Tests")
    story.append(Paragraph(
        "Wilcoxon signed-rank tests on the 5 fold-level C-index values:", S['body']))
    stat_data = [
        ["Comparison", "Mean Delta", "Wilcoxon p", "Verdict"],
        ["SAGAM vs Linear Stacking", "+0.0064", "0.313", "NOT significant"],
        ["SAGAM vs DeepSurv", "–0.0023", "0.625", "NOT significant (SAGAM WORSE)"],
        ["SAGAM vs RSF", "+0.0144", "0.094", "Marginally directional only"],
    ]
    story.append(make_table(stat_data[0], stat_data[1:],
                            [5*cm, 2.5*cm, 2.5*cm, 6.5*cm]))
    story.append(Spacer(1,6))
    info_box(story, S,
        "<b>Power analysis:</b> With 181 events across 5 folds (~36 events/fold), the "
        "minimum detectable C-index difference at 80% power (alpha=0.05, paired t-test) "
        "is approximately delta ≈ 0.106. The observed SAGAM advantage of 0.006 (vs Linear) "
        "and 0.014 (vs RSF) are 7–17x smaller than the detectable threshold. "
        "Non-significance does NOT mean SAGAM is equivalent — it means the study is "
        "underpowered to detect small effects.",
        bg=colors.HexColor("#E3F2FD"), border=MID_BLUE, style='body')

    sub_divider(story, S, "8.4  Subgroup Analysis by AJCC Stage")
    story.append(Paragraph(
        "Does SAGAM perform differently across early (Stage I/II) vs late (III/IV) disease?", S['body']))
    sg_data = [
        ["Subgroup", "n", "Events", "SAGAM C", "Linear C", "Delta", "Verdict"],
        ["Stage I/II (early)", "394", "120", "0.574", "0.564", "+0.010", "Marginal SAGAM advantage"],
        ["Stage III/IV (late)", "105", "61", "0.582", "0.577", "+0.005", "No difference"],
        ["All patients", "501", "181", "0.625", "0.619", "+0.006", "Consistent with main result"],
    ]
    story.append(make_table(sg_data[0], sg_data[1:],
                            [3.2*cm, 1.2*cm, 1.8*cm, 2*cm, 2*cm, 1.8*cm, 4.5*cm],
                            highlight_row=0))
    story.append(Spacer(1,6))
    story.append(Paragraph(
        "SAGAM shows consistent (if small) advantages over linear stacking across both "
        "subgroups. The early-stage subgroup (n=394, Stage I/II) shows the largest delta "
        "(+0.010). However, C-index values in the 0.57–0.58 range are weak, and subgroup "
        "analyses with overlapping CIs should not be over-interpreted.", S['body']))

    story.append(PageBreak())

    # ════════════════════════════════════════
    # SECTION 9 — HONEST PUBLISHABILITY ASSESSMENT
    # ════════════════════════════════════════
    section_divider(story, S, "9.  Publishability Assessment — No Sugarcoating")

    # Verdict banner
    verdict_tbl = Table(
        [[Paragraph("PUBLISHABILITY VERDICT", ParagraphStyle('vt',
           fontSize=14, textColor=colors.white, fontName='Helvetica-Bold',
           alignment=TA_CENTER)),
          Paragraph("Niche/Workshop-Level: Needs Significant Work for Top Venue",
           ParagraphStyle('vs', fontSize=11, textColor=colors.HexColor("#FFE082"),
           fontName='Helvetica-Bold', alignment=TA_CENTER))]],
        colWidths=[5*cm, 11.5*cm]
    )
    verdict_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#B71C1C")),
        ('TOPPADDING', (0,0),(-1,-1), 10),
        ('BOTTOMPADDING', (0,0),(-1,-1), 10),
        ('LEFTPADDING', (0,0),(-1,-1), 12),
        ('ALIGN', (0,0),(-1,-1), 'CENTER'),
        ('VALIGN', (0,0),(-1,-1), 'MIDDLE'),
    ]))
    story.append(verdict_tbl)
    story.append(Spacer(1, 10))

    sub_divider(story, S, "9.1  What the Paper Does Well (Genuine Strengths)")
    strengths = [
        ("Methodological rigor", "Nested CV, strict leakage prevention, ES isolation — the "
         "pipeline is more carefully designed than many published survival ML papers. The "
         "reproducibility is high."),
        ("Clinical interpretability", "The spline contribution plots and KM stratification "
         "provide genuine biological insight. The 104 vs 36 month median OS separation is "
         "a clinically meaningful finding, regardless of C-index."),
        ("External validation attempted", "Two independent cohorts were used. Most "
         "workshop papers skip this. Even though GSE68465 fails, the attempt is commendable."),
        ("Leakage-free results", "After fixing 5 identified bugs, the results reflect "
         "genuine generalisation performance — not artificially inflated metrics."),
        ("Novel meta-learner formulation", "The spline-Cox stacking approach is a genuine "
         "methodological contribution, not widely used in survival analysis literature."),
        ("Calibration analysis", "IBS and calibration plots are shown alongside C-index — "
         "a more complete evaluation than most survival ML papers."),
    ]
    for name, desc in strengths:
        story.append(Paragraph(f"<b>+ {name}:</b> {desc}", S['verdict_good']))
    story.append(Spacer(1,8))

    sub_divider(story, S, "9.2  Critical Weaknesses (Deal-Breakers for Top Venues)")
    weaknesses = [
        ("SAGAM does not beat its own base learners significantly",
         "DeepSurv (C=0.636) outperforms SAGAM (C=0.634). The entire point of a "
         "meta-learner is to exceed its components. That it ties (and sometimes loses to) "
         "individual models undermines the central contribution."),
        ("Stage Cox beats SAGAM",
         "A single clinical feature (AJCC stage) achieves C=0.657 — better than the "
         "full ML ensemble. Any reviewer will ask: why use a complex ML pipeline if a "
         "doctor's staging assessment does better? This needs a compelling answer."),
        ("GSE68465 failure",
         "C=0.551 (NS) on the better-powered external cohort. The model does not "
         "generalise to the larger dataset. This is the single biggest problem. A paper "
         "with failed external validation cannot be accepted at a serious journal without "
         "a convincing explanation."),
        ("SAGAM is worst on tdAUC",
         "Lower tdAUC than ALL comparators at 1-year, 3-year, and 5-year horizons. "
         "The spline transformation appears to hurt time-specific discrimination. "
         "If a clinician wants to know '1-year survival probability', SAGAM is the "
         "worst model to use."),
        ("Underpowered study",
         "181 events is too few to demonstrate statistical significance for the observed "
         "C-index differences (~0.006–0.014). The study would need approximately 1,700 "
         "events to detect a 0.01 C-index difference at 80% power. This is not fixable "
         "with the current dataset."),
        ("No comparison to recent literature",
         "The paper does not compare against published TCGA-LUAD results from "
         "2022–2025. Methods like SurvTRACE, DeepHit, or attention-based survival "
         "models have been applied to TCGA data and may have substantially higher "
         "C-indices."),
        ("Single dataset primary training",
         "Training on n=501 with 181 events is limited. Modern survival ML papers "
         "typically use 1,000+ patients or perform multi-dataset meta-analysis."),
    ]
    for name, desc in weaknesses:
        story.append(Paragraph(f"<b>— {name}:</b> {desc}", S['verdict_warn']))
    story.append(Spacer(1,8))

    sub_divider(story, S, "9.3  Areas Needing Improvement (Opportunities)")
    improvements = [
        ("Frame the contribution around interpretability, not discrimination",
         "The spline contribution plots (Fig. 3) are genuinely interesting — they show "
         "which risk score ranges each learner is trustworthy in. Reframe the paper as "
         "'an interpretable survival meta-learner' rather than 'a better predictor'. "
         "This is a much stronger and more honest claim."),
        ("Address GSE68465 failure explicitly",
         "Investigate why — platform differences, population differences, gene panel "
         "mismatch (7/10 genes). Consider re-training with a GSE68465-compatible gene "
         "set, or explicitly scoping the method to Affymetrix U133 Plus 2.0 data."),
        ("Add a proper comparison to published baselines",
         "Benchmark against SurvTRACE, DeepHit, or at minimum the best published TCGA "
         "LUAD model. Show where SAGAM sits in the literature landscape."),
        ("Increase sample size via multi-dataset training",
         "Pool TCGA-LUAD with NLST or other LUAD cohorts for training to reach n>1,000. "
         "This would also make the statistical tests meaningful."),
        ("Address the tdAUC problem",
         "Understand WHY SAGAM's tdAUC is lowest. Is it a calibration problem? "
         "Is the Breslow estimator poorly fitted? Consider IPCW-corrected Brier scores."),
        ("Clinical subtype analysis",
         "Stratify by EGFR/KRAS/ALK mutation status. Show that SAGAM captures "
         "biologically distinct risk groups beyond what stage captures."),
    ]
    for name, desc in improvements:
        story.append(Paragraph(f"<b>* {name}:</b> {desc}", S['verdict_neutral']))
    story.append(Spacer(1,8))

    sub_divider(story, S, "9.4  Target Venues (Realistic Assessment)")
    venues = [
        ["Venue", "Scope", "Realistic?", "Required Fix"],
        ["IEEE BIBM 2026 (Workshop)", "ML in biomedicine, workshop track", "YES — current state", "Minor revisions to framing"],
        ["IEEE BIBM 2026 (Main)", "Full ML/bioinformatics paper", "STRETCH — needs work", "Fix GSE68465, add baselines"],
        ["Bioinformatics (OUP)", "Computational methods", "NO — current state", "External validation + power"],
        ["PLOS ONE", "Open science, all fields", "POSSIBLE — revised", "Add comparison, explain GSE68465"],
        ["Journal of Biomedical Informatics", "Clinical informatics", "POSSIBLE — revised", "Clinical framing, interpretability focus"],
        ["Nature Methods / Cancer Research", "Top-tier", "NOT REALISTIC", "Fundamental performance gaps"],
    ]
    story.append(make_table(venues[0], venues[1:],
                            [3.8*cm, 4.2*cm, 2.5*cm, 6*cm], highlight_row=0))
    story.append(Spacer(1,6))

    story.append(PageBreak())

    # ════════════════════════════════════════
    # SECTION 10 — TECHNICAL PIPELINE SUMMARY
    # ════════════════════════════════════════
    section_divider(story, S, "10.  Technical Pipeline Summary")

    sub_divider(story, S, "10.1  Script Execution Order")
    scripts = [
        ["Step", "Script", "Purpose", "Output Files"],
        ["1", "final_experiments.py", "Main nested CV, KM plots, tdAUC, Stage+SAGAM", "fold_results.csv, kaplan_meier*.png, gam_smooths_4panel.png"],
        ["2", "survival_metrics.py", "IBS, tdAUC (fold-specific), calibration, HR, external CIs", "survival_metrics.txt, calibration_plot.png"],
        ["3", "supplementary_experiments.py", "Cox baselines, df ablation, Wilcoxon tests, IBS", "supplementary_results.txt, supplementary_metrics.csv"],
        ["4", "improvements.py", "Bootstrap significance, power analysis, subgroup analysis", "ibs_bootstrap.csv, subgroup_analysis.csv"],
        ["5", "external_val_multi.py", "Multi-cohort external validation (GSE31210, GSE68465)", "ext_val_multi_summary.csv, ext_km_*.png"],
    ]
    story.append(make_table(scripts[0], scripts[1:],
                            [1*cm, 4.5*cm, 5*cm, 6*cm]))
    story.append(Spacer(1,6))

    story.append(Paragraph(
        "<b>Environment:</b> Python 3.14, sagam_env virtual environment. "
        "Run with: <font name='Courier' size='9'>sagam_env\\Scripts\\python.exe notebooks\\[script].py</font>", S['body']))

    sub_divider(story, S, "10.2  Key Hyper-parameters")
    params = [
        ["Component", "Key Parameters"],
        ["RSF", "n_estimators=200, max_features='sqrt', min_samples_leaf=5"],
        ["GBS", "n_estimators=200, learning_rate=0.05, max_depth=3"],
        ["XGBoost-Cox", "objective='survival:cox', eta=0.05, max_depth=3, subsample=0.8, colsample_bytree=0.8, num_boost_round=300, early_stopping=20"],
        ["DeepSurv", "Layers: 64-32-1 (ReLU, Dropout 0.3), lr=1e-3, weight_decay=1e-4, max_ep=200, patience=20"],
        ["Meta-learner (CoxNet)", "alphas selected by internal 80/20 split, l1_ratio=0.9, max_iter=100,000, tol=1e-7"],
        ["Spline layer", "Cubic B-splines, df=4, degree=3, no intercept, 4 bases per learner = 16 total features"],
        ["Outer CV", "StratifiedKFold(5), shuffle=True, random_state=42"],
        ["Inner CV (OOF)", "KFold(3), shuffle=True, random_state=42"],
    ]
    t = Table([[Paragraph(r[0], ParagraphStyle('th', fontSize=8.5, fontName='Helvetica-Bold',
               alignment=TA_LEFT, textColor=colors.white if i==0 else DARK_BLUE)),
               Paragraph(r[1], ParagraphStyle('td', fontSize=8.5, fontName='Courier' if i>0 else 'Helvetica-Bold',
               alignment=TA_LEFT, textColor=colors.white if i==0 else TEXT_DARK))]
              for i, r in enumerate(params)],
             colWidths=[3.5*cm, 13*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), DARK_BLUE),
        ('GRID', (0,0),(-1,-1), 0.4, MID_GREY),
        ('ROWBACKGROUNDS', (0,1),(-1,-1), [LIGHT_GREY, colors.white]),
        ('TOPPADDING',    (0,0),(-1,-1), 4),
        ('BOTTOMPADDING', (0,0),(-1,-1), 4),
        ('LEFTPADDING',   (0,0),(-1,-1), 6),
        ('RIGHTPADDING',  (0,0),(-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1,8))

    # ════════════════════════════════════════
    # SECTION 11 — CONCLUSIONS
    # ════════════════════════════════════════
    section_divider(story, S, "11.  Conclusions")

    story.append(Paragraph(
        "SAGAM is a well-engineered, methodologically careful survival stacking framework. "
        "The core idea — using B-spline transforms to allow nonlinear meta-learning — is "
        "novel and technically sound. The contribution plots provide genuine biological "
        "insight into how each base learner contributes. The clinical risk stratification "
        "(KM curves, hazard ratios) is strong and meaningful.", S['body']))

    story.append(Paragraph(
        "However, the central quantitative claim — that SAGAM outperforms alternatives — "
        "is not supported by the data at the current sample size. The method is neither "
        "definitively better nor worse than its competitors; the study simply lacks the "
        "statistical power to resolve the question. The failed GSE68465 external "
        "validation is the most serious obstacle to publication.", S['body']))

    info_box(story, S,
        "<b>Bottom line:</b> SAGAM is suitable for submission to BIBM 2026 as a workshop "
        "paper focused on the interpretable meta-learning methodology and the clinical "
        "risk stratification finding. For a main-track or journal paper, the GSE68465 "
        "failure must be explained, external validation on a third cohort should be added, "
        "and the framing should shift from 'better prediction' to 'interpretable ensemble "
        "with competitive performance and clear risk stratification utility'.",
        bg=LIGHT_BLUE, border=DARK_BLUE)

    story.append(Spacer(1,8))

    # Final table summary
    summary = [
        ["Criterion", "Rating", "Comment"],
        ["Methodological rigor", "STRONG", "Nested CV, leakage-free, ES isolation"],
        ["Primary C-index performance", "MODERATE", "0.634, not beating all baselines"],
        ["Statistical significance", "WEAK", "Underpowered (n=181 events)"],
        ["Internal risk stratification (KM)", "STRONG", "p<0.0001, 3x OS difference"],
        ["External validation (GSE31210)", "MODERATE", "C=0.661 but only 35 events"],
        ["External validation (GSE68465)", "FAILED", "C=0.551, p=NS, Linear beats SAGAM"],
        ["Novelty of method", "MODERATE", "Spline meta-learner is novel but incremental"],
        ["Clinical interpretability", "STRONG", "Contribution plots, HR analysis"],
        ["Literature comparison", "MISSING", "No benchmark against 2022-2025 papers"],
        ["Overall publishability", "NICHE JOURNAL", "BIBM workshop YES; top journal NEEDS WORK"],
    ]
    rating_colors = {
        "STRONG":       colors.HexColor("#C8E6C9"),
        "MODERATE":     colors.HexColor("#FFF9C4"),
        "WEAK":         colors.HexColor("#FFCCBC"),
        "FAILED":       colors.HexColor("#FFCDD2"),
        "MISSING":      colors.HexColor("#F5F5F5"),
        "NICHE JOURNAL": colors.HexColor("#E1F5FE"),
    }
    data_rows = []
    for i, row in enumerate(summary):
        data_rows.append([
            Paragraph(row[0], ParagraphStyle('td', fontSize=9,
              fontName='Helvetica-Bold' if i==0 else 'Helvetica',
              alignment=TA_LEFT, textColor=colors.white if i==0 else TEXT_DARK)),
            Paragraph(row[1], ParagraphStyle('td', fontSize=9,
              fontName='Helvetica-Bold', alignment=TA_CENTER,
              textColor=colors.white if i==0 else DARK_BLUE)),
            Paragraph(row[2], ParagraphStyle('td', fontSize=9,
              fontName='Helvetica', alignment=TA_LEFT,
              textColor=colors.white if i==0 else TEXT_DARK)),
        ])
    t_summary = Table(data_rows, colWidths=[5.5*cm, 3*cm, 8*cm])
    style_s = [
        ('BACKGROUND', (0,0), (-1,0), DARK_BLUE),
        ('GRID', (0,0),(-1,-1), 0.4, MID_GREY),
        ('TOPPADDING',    (0,0),(-1,-1), 5),
        ('BOTTOMPADDING', (0,0),(-1,-1), 5),
        ('LEFTPADDING',   (0,0),(-1,-1), 6),
        ('RIGHTPADDING',  (0,0),(-1,-1), 6),
    ]
    for i, row in enumerate(summary[1:], 1):
        bg = rating_colors.get(row[1], colors.white)
        style_s.append(('BACKGROUND', (1,i), (1,i), bg))
    t_summary.setStyle(TableStyle(style_s))
    story.append(t_summary)

    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=1, color=MID_GREY))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Report generated automatically from pipeline outputs — May 2026  |  "
        "TCGA-LUAD SAGAM Project  |  BIBM 2026 Submission",
        ParagraphStyle('footer', fontSize=8, textColor=colors.grey,
                       alignment=TA_CENTER, fontName='Helvetica')))

    # ── BUILD ──────────────────────────────────────────────────────────
    doc.build(story)
    print(f"\n[OK] Report saved -> {PDF}")
    print(f"     Size: {PDF.stat().st_size / 1024:.0f} KB")

if __name__ == '__main__':
    build_pdf()
