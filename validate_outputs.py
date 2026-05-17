import pandas as pd
import numpy as np
import json

print('=== OVERALL FORECAST ===')
df = pd.read_csv('artifacts/forecast_outputs/ops72h_overall_forecast.csv')
print('rows:', len(df))
print('columns:', list(df.columns))
print('NaN:', df.isna().sum().sum())

if 'hybrid_pred' in df.columns:
    hp = df['hybrid_pred'].astype(float)
    print('hybrid_pred min:', round(hp.min(), 2))
    print('hybrid_pred max:', round(hp.max(), 2))
    print('hybrid_pred negatives:', (hp < 0).sum())
    std = hp.std()
    print('hybrid_pred std:', round(std, 3))
    print('flat (std<1):', std < 1.0)
    print('sample values:', hp.head(5).round(2).tolist())

if 'lstm_pred' in df.columns:
    lp = df['lstm_pred'].astype(float)
    print('lstm_pred min:', round(lp.min(), 2), 'max:', round(lp.max(), 2))

if 'arimax_pred' in df.columns:
    ap = df['arimax_pred'].astype(float)
    print('arimax_pred min:', round(ap.min(), 2), 'max:', round(ap.max(), 2))

print()
print('=== DEPARTMENT FORECAST ===')
dept_df = pd.read_csv('artifacts/forecast_outputs/ops72h_department_forecast.csv')
print('rows:', len(dept_df))
print('NaN:', dept_df.isna().sum().sum())

if 'department' in dept_df.columns:
    depts = dept_df['department'].unique().tolist()
    print('departments:', depts)
    for d in depts:
        sub = dept_df[dept_df['department'] == d]
        hp_std = round(sub['hybrid_pred'].std(), 2) if 'hybrid_pred' in sub.columns else 'N/A'
        print(f'  {d}: {len(sub)} rows, hybrid_pred std={hp_std}')

print()
print('=== METRICS CSV ===')
mdf = pd.read_csv('artifacts/metrics_72h/ops72h_model_metrics.csv')
print(mdf.to_string())

print()
print('=== MANIFEST ===')
with open('artifacts/manifests/ops72h_training_summary.json') as f:
    manifest = json.load(f)
print('fallback_used:', manifest.get('fallback_used'))
print('best_model:', manifest.get('best_model'))
print('weights:', manifest.get('weights'))
print('training_source:', manifest.get('training_source'))
print('timestamp:', manifest.get('timestamp'))
