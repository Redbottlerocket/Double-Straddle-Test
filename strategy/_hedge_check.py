"""
1. Check whether long straddle hedges short straddle losses.
2. Run sensitivity analysis: exit long straddle N days before next earnings.
"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent

t = pd.read_csv(ROOT / "results" / "trades.csv", parse_dates=[
    'earn_dt', 'short_entry_dt', 'long_entry_dt', 'short_exit_dt', 'long_exit_dt'])
t['year'] = t['earn_dt'].dt.year

# ── 1. Do the legs hedge each other? ───────────────────────────────────────
print('=== HEDGE ANALYSIS ===')
corr = t['short_pnl'].corr(t['long_pnl'])
print(f'Correlation short_pnl vs long_pnl: {corr:.3f}')
print('(Negative = hedge. Positive = same direction. Zero = independent.)')
print()

# Cross-tab: did long offset short?
s_win = t['short_pnl'] > 0
l_win = t['long_pnl']  > 0
ct = pd.crosstab(s_win.map({True:'Short WIN', False:'Short LOSE'}),
                 l_win.map({True:'Long WIN',  False:'Long LOSE'}))
ct.index.name = None
ct.columns.name = None
print('Joint outcomes (trades):')
print(ct)
print()

# When short LOSES, how often does long offset?
short_loss = t[t['short_pnl'] < 0]
full_offset = (short_loss['long_pnl'] > short_loss['short_pnl'].abs()).sum()
partial     = ((short_loss['long_pnl'] > 0) & (short_loss['long_pnl'] <= short_loss['short_pnl'].abs())).sum()
no_offset   = (short_loss['long_pnl'] <= 0).sum()
print(f'When short straddle loses ({len(short_loss)} trades):')
print(f'  Long fully covers the loss : {full_offset} trades ({full_offset/len(short_loss)*100:.1f}%)')
print(f'  Long partially offsets     : {partial}  trades ({partial/len(short_loss)*100:.1f}%)')
print(f'  Long also loses (worst)    : {no_offset}  trades ({no_offset/len(short_loss)*100:.1f}%)')
print()

# 2022 specifically
t22 = t[t['year'] == 2022]
sl22 = t22[t22['short_pnl'] < 0]
print(f'2022 -- when short loses ({len(sl22)} trades):')
fo22 = (sl22['long_pnl'] > sl22['short_pnl'].abs()).sum()
pa22 = ((sl22['long_pnl'] > 0) & (sl22['long_pnl'] <= sl22['short_pnl'].abs())).sum()
no22 = (sl22['long_pnl'] <= 0).sum()
print(f'  Long fully covers     : {fo22}')
print(f'  Long partially offsets: {pa22}')
print(f'  Long also loses       : {no22}')
