import os
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt

# Load SQLite DB path from env var or default to runtime.db
DB_PATH = os.environ.get("SQLITE_DB_PATH", "runtime.db")
# Ensure the directory exists
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def fetch_data(hours=24):
    """Fetch runtime data from the last N hours."""
    con = sqlite3.connect(DB_PATH)
    query = f"""
    SELECT ts, fn, duration_ms
    FROM function_runtime
    WHERE ts >= strftime('%s','now','-{hours} hours')
    """
    df = pd.read_sql_query(query, con)
    con.close()
    df['ts'] = pd.to_datetime(df['ts'], unit='s')
    df.set_index('ts', inplace=True)
    return df


def save_csv(df, out_csv):
    """Save the DataFrame to CSV."""
    df.to_csv(out_csv)
    print(f"✅ CSV saved to: {out_csv}")


def plot_trend(df, out_path):
    """Plot runtime trend over time."""
    df2 = df.pivot(columns='fn', values='duration_ms').resample('1H').mean().ffill()
    plt.figure(figsize=(10,5))
    for fn in df2.columns:
        plt.plot(df2.index, df2[fn], label=fn)
    plt.title(f'Function Runtime Over Time ({len(df2)} hrs)')
    plt.xlabel('Timestamp')
    plt.ylabel('Runtime (ms)')
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def plot_bar(df, out_path):
    """Plot average runtime as bar chart."""
    df2 = df.pivot(columns='fn', values='duration_ms').resample('1H').mean()
    avg = df2.mean()
    plt.figure(figsize=(8,4))
    plt.bar(avg.index, avg.values)
    plt.title('Average Function Runtime (Last 24h)')
    plt.xlabel('Function')
    plt.ylabel('Average Runtime (ms)')
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


if __name__ == "__main__":
    df = fetch_data(hours=24)
    if df.empty:
        print("⚠️ No records in the last 24 hours. Ensure decorator is applied.")
    else:
        base_dir = os.path.dirname(DB_PATH) or '.'
        # Save CSV
        csv_path = os.path.join(base_dir, "runtime.csv")
        save_csv(df, csv_path)
        # Save plots
        plot_trend(df, os.path.join(base_dir, "runtime_trend.png"))
        plot_bar(df,   os.path.join(base_dir, "runtime_bar.png"))
        print(f"✅ Reports generated: {csv_path}, runtime_trend.png, runtime_bar.png")
