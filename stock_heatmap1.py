import yfinance as yf
import pandas as pd
import plotly.express as px

# Define stock tickers (example: S&P 500 tech stocks)
# tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "NFLX", "BRK-B", "JPM"]
tickers = []
count = 0
with open("/Users/a1234/Documents/python/sp500_ticker.txt", encoding="utf-8") as f:
    for line in f:
        count += 1
        tickers.append(line.strip())
        if count > 20:
            break
tickers.sort()

# Download live market data: 1 day
data = yf.download(tickers, period="2d", interval="1d")["Close"]

# Get latest price and previous close
latest_prices = data.iloc[1]
prev_close = data.iloc[0]

# Calculate daily percentage change
price_changes = ((latest_prices - prev_close) / prev_close) * 100

print(latest_prices)
print(prev_close)
print(price_changes)

# Fetch market capitalization for each stock, 0 means default value if no return
market_caps = {ticker: yf.Ticker(ticker).info.get("marketCap", 0) for ticker in tickers}
# Fetch market capitalization for each stock, 0 means default value if no return
sector_map = {ticker: yf.Ticker(ticker).info.get("sector", 0) for ticker in tickers}

# Create DataFrame
df = pd.DataFrame({
    "Stock": tickers,
    "Market Cap": [market_caps[ticker] for ticker in tickers],
    "Price Change": price_changes.values,
    "Sector": [sector_map[ticker] for ticker in tickers]
})

# # Similar as market_caps, get the Sector Information with API
# df["Sector"] = df["Stock"].map(sector_map)

# Remove NaN values
df.dropna(inplace=True)

# Sort data by market cap
df = df.sort_values(by="Market Cap", ascending=False)

# Plot Treemap Heatmap
fig = px.treemap(
    df,
    path=["Sector", "Stock"],  # Sector -> Stock hierarchy
    values="Market Cap",
    range_color=[-10, 10],  # Set range to control color transitions
    color="Price Change",
    color_continuous_scale="RdYlGn",  # Red = Loss, Green = Gain
    title="Live Stock Market Heatmap",
)

fig.show()