import pandas as pd
import yfinance as yf

def fetch_stock_prices_from_list(stock_codes_txt_file) -> pd.DataFrame:
	"""
	Read stock codes from a text file object (one code per line), fetch each
	stock's latest price using yfinance, and output a pandas table containing
	stock code, stock price, and timestamp.
	"""
	stock_codes = [line.strip() for line in stock_codes_txt_file if line.strip()]
	timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

	rows = []
	for code in stock_codes:
		price = None
		try:
			ticker = yf.Ticker(code)

			# Fast path for latest traded price
			fast_info = getattr(ticker, "fast_info", None)
			if fast_info is not None:
				price = fast_info.get("last_price")

			# Fallback if fast_info is unavailable or empty
			if price is None:
				hist = ticker.history(period="1d")
				if not hist.empty:
					price = float(hist["Close"].iloc[-1])
		except Exception:
			price = None

		if price is not None:
			price = f"{float(price):.2f}"

		rows.append(
			{
				"Code": code,
				"Price": price,
				"Timestamp": timestamp,
			}
		)

	df = pd.DataFrame(rows, columns=["Code", "Price", "Timestamp"])
	return df

