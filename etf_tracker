import os
import json
import requests
import gspread

# --- CONFIGURATION ---
SPREADSHEET_ID = "1E558JcLuLMyBqclmqrRhvlswMK9FS-NdJw_o3W1C7vI"
WORKSHEET_NAME = "ETFs"
UPDATE_THRESHOLD = 0.5  # % change threshold to flag as a major update (e.g., 0.5%)

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

def main():
    # Get environment secrets
    service_account_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
    fmp_api_key = os.environ.get("FMP_API_KEY")

    if not service_account_str:
        raise ValueError("Error: Missing GOOGLE_SERVICE_ACCOUNT environment variable.")
    if not fmp_api_key:
        raise ValueError("Error: Missing FMP_API_KEY environment variable.")

    # 1. Initialize Google Sheets Client
    print("Connecting to Google Sheets...")
    credentials = json.loads(service_account_str)
    gc = gspread.service_account_from_dict(credentials)
    sheet = gc.open_by_key(SPREADSHEET_ID)

    try:
        worksheet = sheet.worksheet(WORKSHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        print(f"Worksheet '{WORKSHEET_NAME}' not found. Creating it...")
        worksheet = sheet.add_worksheet(title=WORKSHEET_NAME, rows="1000", cols="4")

    # 2. Read Existing Sheet Data for Baseline Comparison
    print("Reading existing worksheet data...")
    existing_records = worksheet.get_all_values()

    previous_holdings = {}
    if len(existing_records) > 1:
        for row in existing_records[1:]:
            if len(row) >= 3 and row[0] and row[1]:
                etf_name_ticker = row[0]
                # Extract ticker from "ETF Name (TICKER)" format
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

    # 3. Fetch ETF Holdings from API
    def fetch_etf_holdings(ticker):
        url = f"https://financialmodelingprep.com/api/v3/etf-holder/{ticker}?apikey={fmp_api_key}"
        try:
            res = requests.get(url, timeout=15)
            if res.status_code == 200:
                data = res.json()
                holdings = {}
                if isinstance(data, list):
                    for item in data:
                        stock = item.get("asset") or item.get("symbol")
                        weight = item.get("weightPercentage")
                        if stock and weight is not None:
                            holdings[stock] = float(weight)
                return holdings
            else:
                print(f"API Error ({res.status_code}) fetching {ticker}")
                return None
        except Exception as e:
            print(f"Exception fetching {ticker}: {e}")
            return None

    # 4. Process Holdings and Identify Updates
    headers = ["Name of ETF (Ticker)", "Stock Holding", "% Holding", "Major Update in Holding"]
    new_sheet_data = [headers]

    print("Fetching live holdings and computing differences...")
    for ticker, etf_name in ETF_LIST.items():
        print(f"Processing {ticker}...")
        current_holdings = fetch_etf_holdings(ticker)

        # Safety Fallback: If API call fails, keep old data to prevent accidental wiping
        if current_holdings is None:
            print(f"Warning: Keeping existing sheet records for {ticker} due to fetch error.")
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

    # 5. Overwrite Worksheet with Clean Data
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
