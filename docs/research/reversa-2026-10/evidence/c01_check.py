import yfinance as yf, pandas as pd
tick = {"CABK.MC":"CaixaBank","SAB.MC":"Sabadell","BKT.MC":"Bankinter","BBVA.MC":"BBVA","SAN.MC":"Santander","NTGY.MC":"Naturgy","ELE.MC":"Endesa","IBE.MC":"Iberdrola","REP.MC":"Repsol","^IBEX":"IBEX 35"}
px = yf.download(list(tick), start="2022-06-01", end="2022-07-25", auto_adjust=True, progress=False)["Close"]
ret = px.pct_change()*100
d0, d1 = "2022-07-12", "2022-07-13"
print("Close-to-close returns (%):")
print(ret.loc[[d0,d1]].T.rename(index=tick).round(2))
ar = ret.sub(ret["^IBEX"], axis=0).drop(columns="^IBEX")
print("\nMarket-adjusted abnormal return, event day + next day (CAR[0,1], %):")
print(ar.loc[[d0,d1]].sum().rename(index=tick).sort_values().round(2))
# market model alternative
est = ret.loc["2022-06-01":"2022-07-08"]
import numpy as np
mm = {}
for t in tick:
    if t=="^IBEX": continue
    x, y = est["^IBEX"].dropna(), est[t].dropna()
    b, a = np.polyfit(x.loc[y.index], y, 1)
    mm[tick[t]] = round(float((ret.loc[[d0,d1], t] - (a + b*ret.loc[[d0,d1], "^IBEX"])).sum()),2)
print("\nMarket-model CAR[0,1] with ~25-day estimation window (illustrative only):", mm)
