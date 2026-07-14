import yfinance as yf

data = yf.download('0050.TW', start='2026-07-01', auto_adjust=False)
print(data)
print(data.columns)