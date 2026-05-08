import pandas as pd
from pathlib import Path

PATH = Path('data/updated_exports/what_if_scenarios.csv')

required_cols = [
    'scenario_id','scenario_name','scenario_category','department','time_window',
    'demand_multiplier','arrival_increase_percent','bed_capacity_change_percent',
    'doctor_availability_change_percent','nurse_availability_change_percent',
    'or_booking_change_percent','appointment_change_percent','discharge_delay_hours',
    'severity_level','probability_level','operational_risk','affected_resources',
    'expected_system_response','recommended_action','escalation_required','notes'
]

severity_allowed = {'Low','Medium','High','Critical'}
prob_allowed = {'Rare','Unlikely','Possible','Likely','Very Likely','VeryLikely'}
risk_allowed = {'Low','Moderate','High','Critical'}
esc_allowed = {'Yes','No'}


def main():
    if not PATH.exists():
        raise SystemExit(f'Missing {PATH}')
    df = pd.read_csv(PATH)
    assert len(df) >= 40, f'Expected >=40 rows, got {len(df)}'
    missing = [c for c in required_cols if c not in df.columns]
    assert not missing, f'Missing columns: {missing}'
    assert df['scenario_id'].is_unique, 'scenario_id values must be unique'

    sev = set(df['severity_level'].dropna().unique().tolist())
    prob = set(df['probability_level'].dropna().unique().tolist())
    risk = set(df['operational_risk'].dropna().unique().tolist())
    esc = set(df['escalation_required'].dropna().unique().tolist())

    assert sev.issubset(severity_allowed), f'Invalid severity values: {sev-severity_allowed}'
    assert prob.issubset(prob_allowed), f'Invalid probability values: {prob-prob_allowed}'
    assert risk.issubset(risk_allowed), f'Invalid operational_risk values: {risk-risk_allowed}'
    assert esc.issubset(esc_allowed), f'Invalid escalation_required values: {esc-esc_allowed}'

    print('OK')
    print('rows',len(df))
    print('cols',len(df.columns))
    print('categories',sorted(df['scenario_category'].unique().tolist()))
    print('departments',sorted(df['department'].unique().tolist()))


if __name__ == '__main__':
    main()

