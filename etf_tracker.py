import os
import json
import requests
import gspread
from bs4 import BeautifulSoup
import yfinance as yf

# --- CONFIGURATION ---
SPREADSHEET_ID = "1E558JcLuLMyBqclmqrRhvlswMK9FS-NdJw_o3W1C7vI"
WORKSHEET_NAME = "ETFs"
UPDATE_THRESHOLD = 0.5  # % change threshold to flag as a major update

# Tickers & Names
ETF_LIST = {
    "BWET": "BREAKWAVE TANKER SHIPPING ETF",
    "ROAM": "Emerging Markets ETF",
    "VOLT": "Tema Electrification ETF",
    "FXI": "iShares China Large-Cap ETF",
    "AIPO": "AI & Power Infra ETF",
    "CHAT": "Gen AI & Tech ETF",
    "BAI": "AI Innovation & Tech ETF",
    "SMH": "VanEck Semiconductor ETF",
    "IAK": "iShares US Insurance ETF"
}

def fetch_full_etf_holdings(ticker):
    """
    Fetches 100% of ETF holdings from StockAnalysis.
    Falls back to yfinance top holdings if scraping is blocked.
    """
    holdings = {}
    url = f"https://stockanalysis.com/etf/{ticker.lower()}/holdings/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            table = soup.find("table")
            if table:
                rows = table.find_all("tr")
                for row in rows[1:]:
                    cols = row.find_all("td")
                    if len(cols) >= 3:
                        symbol = cols[0].text.strip()
                        name = cols[1].text.strip()
                        weight_str = cols[2].text.strip().replace("%", "").replace(",", "")

                        # Prefer ticker symbol, fall back to holding name
                        stock_id = symbol if (symbol and symbol != "-") else name

                        try:
                            weight = float(weight_str)
                            if stock_id:
                                holdings[stock_id] = round(weight, 2)
                        except ValueError:
                            continue

                if holdings:
                    print(f"Successfully retrieved {len(holdings)} holdings for {ticker}.")
                    return holdings
    except Exception as e:
        print(f"Full fetch failed for {ticker}: {e}")

    # Fallback to yfinance top holdings
    print(f"Falling back to yfinance top holdings for {ticker}...")
    try:
        etf = yf.Ticker(ticker)
        funds_data = getattr(etf, "funds_data", None)
        if funds_data and hasattr(funds_data, "top_holdings") and funds_data.top_holdings is not None:
            df = funds_data.top_holdings
            if not df.empty:
                for stock_identifier, row in df.iterrows():
                    weight = row.get("Holding Percent", 0)
                    if weight <= 1.0:
                        weight = weight * 100
                    holdings[str(stock_identifier)] = round(float(weight), 2)
    except Exception as e:
        print(f"yfinance fallback failed for {ticker}: {e}")

    return holdings

def main():
    service_account_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
    if not service_account_str:
        raise ValueError("Error: Missing GOOGLE_SERVICE_ACCOUNT environment variable.")

    # 1. Initialize Google Sheets Client
    print("Connecting to Google Sheets...")
    credentials = json.loads(service_account_str)
    gc = gspread.service_account_from_dict(credentials)
    sheet = gc.open_by_key(SPREADSHEET_ID)

    try:
        worksheet = sheet.worksheet(WORKSHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        print(f"Worksheet '{WORKSHEET_NAME}' not found. Creating it...")
        worksheet = sheet.add_worksheet(title=WORKSHEET_NAME, rows="2000", cols="4")

    # 2. Read Existing Sheet Data for Baseline Comparison
    print("Reading existing worksheet data...")
    existing_records = worksheet.get_all_values()

    previous_holdings = {}
    if len(existing_records) > 1:
        for row in existing_records[1:]:
            if len(row) >= 3 and row[0] and row[1]:
                etf_name_ticker = row[0]
                if "(" in etf_name_ticker and ")" in etf_name_ticker:
                    ticker = etf_name_ticker.split("(")[-1].replace(")", "").strip()
                else:
                    ticker = etf_name_ticker.strip()

                stock = row[1].strip()
                try:
                    pct = float(row[2].replace("%", "").strip())
                    if ticker not in previous_holdings:
                        previous_holdings[ticker] = {}
                    previous_holdings[ticker][stock] = pct
                except ValueError:
                    continue

    # 3. Process Holdings and Identify Updates
    headers = ["Name of ETF (Ticker)", "Stock Holding", "% Holding", "Major Update in Holding"]
    new_sheet_data = [headers]

    print("Fetching live full holdings and computing differences...")
    for ticker, etf_name in ETF_LIST.items():
        print(f"Processing {ticker}...")
        current_holdings = fetch_full_etf_holdings(ticker)

        # Fallback if API returns empty data
        if not current_holdings:
            print(f"Warning: No holdings found for {ticker}. Keeping existing records.")
            if ticker in previous_holdings:
                for stock, weight in previous_holdings[ticker].items():
                    new_sheet_data.append([
                        f"{etf_name} ({ticker})",
                        stock,
                        f"{weight:.2f}%",
                        "Fetch Failed (Kept Previous)"
                    ])
            continue

        prev_holdings_dict = previous_holdings.get(ticker, {})
        is_first_run_for_etf = ticker not in previous_holdings
        etf_display_name = f"{etf_name} ({ticker})"

        # A. Process active and new holdings
        sorted_holdings = sorted(current_holdings.items(), key=lambda x: x[1], reverse=True)

        for stock, current_weight in sorted_holdings:
            prev_weight = prev_holdings_dict.get(stock)

            if is_first_run_for_etf:
                update_text = "Initial Entry"
            elif prev_weight is None:
                update_text = "New Holding Added"
            else:
                diff = current_weight - prev_weight
                if diff >= UPDATE_THRESHOLD:
                    update_text = f"Increased {diff:.2f}%"
                elif diff <= -UPDATE_THRESHOLD:
                    update_text = f"Decreased {abs(diff):.2f}%"
                else:
                    update_text = "-"

            new_sheet_data.append([
                etf_display_name,
                stock,
                f"{current_weight:.2f}%",
                update_text
            ])

        # B. Detect completely sold holdings
        if not is_first_run_for_etf:
            for stock, prev_weight in prev_holdings_dict.items():
                if stock not in current_holdings:
                    new_sheet_data.append([
                        etf_display_name,
                        stock,
                        "0.00%",
                        f"Sold Entirely (was {prev_weight:.2f}%)"
                    ])

    # 4. Overwrite Worksheet with Clean Data
    print(f"Updating '{WORKSHEET_NAME}' tab with {len(new_sheet_data) - 1} records...")
    worksheet.clear()
    worksheet.update(values=new_sheet_data, range_name='A1')

    # Apply Header Formatting
    try:
        worksheet.format("A1:D1", {
            "backgroundColor": {"red": 0.88, "green": 0.88, "blue": 0.88},
            "textFormat": {"bold": True}
        })
    except Exception as e:
        print(f"Header formatting warning: {e}")

    print("Process complete!")

if __name__ == "__main__":
    main()
