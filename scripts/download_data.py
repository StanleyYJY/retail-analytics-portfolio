"""Download the UCI Online Retail II dataset (CC BY 4.0) and convert it to Parquet.

Source: Chen, D. (2012). Online Retail II [Dataset]. UCI Machine Learning Repository.
https://doi.org/10.24432/C5CG6D
"""
from pathlib import Path
import io
import urllib.request
import zipfile

import pandas as pd

URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / "online_retail_ii.parquet"
    if out.exists():
        print(f"already present: {out}")
        return
    zpath = RAW / "online_retail_ii.zip"
    if not zpath.exists():
        print("downloading", URL)
        zpath.write_bytes(urllib.request.urlopen(URL, timeout=120).read())
    with zipfile.ZipFile(zpath) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".xlsx"))
        xlsx = zf.read(name)
    print("reading both sheets (this takes a minute)")
    sheets = pd.read_excel(io.BytesIO(xlsx), sheet_name=None, dtype={"Invoice": str, "StockCode": str})
    df = pd.concat(sheets.values(), ignore_index=True)
    df.columns = ["invoice", "stock_code", "description", "quantity", "invoice_ts", "unit_price", "customer_id", "country"]
    df["customer_id"] = df["customer_id"].astype("Int64").astype("string")
    for col in ("invoice", "stock_code", "description", "country"):
        df[col] = df[col].astype("string")
    df.to_parquet(out, index=False)
    print(f"wrote {len(df):,} rows to {out}")


if __name__ == "__main__":
    main()
