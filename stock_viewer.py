#!/usr/bin/env python3
"""
Tkinter Stock Price Viewer
- Fetches price data via yfinance
- Plots Adjusted Close with optional moving averages
- Shows Volume in a separate panel
- Quick range buttons (1M, 3M, 6M, YTD, 1Y, 5Y, Max)
- Interval selector (1d, 1wk, 1mo, 1h, 30m, etc.)

Usage:
  pip install yfinance matplotlib pandas
  python stock_viewer.py
"""

import threading
import datetime as dt
from dataclasses import dataclass

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import pandas as pd
import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import matplotlib.dates as mdates
import yfinance as yf


# ---- Helpers ----

def parse_date(s: str, fallback: dt.date) -> dt.date:
    s = (s or "").strip()
    if not s:
        return fallback
    try:
        # Expecting YYYY-MM-DD
        y, m, d = [int(x) for x in s.split("-")]
        return dt.date(y, m, d)
    except Exception as _:
        raise ValueError(f"Invalid date: '{s}'. Expected YYYY-MM-DD")


@dataclass
class AppState:
    symbol: str = "AAPL"
    start: dt.date = dt.date.today() - dt.timedelta(days=365)
    end: dt.date = dt.date.today()
    interval: str = "1d"
    ma5: bool = True
    ma20: bool = True
    ma50: bool = True
    ma200: bool = False


class StockApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Stock Price Viewer (Tkinter + Matplotlib)")
        self.geometry("1050x700")
        self.minsize(900, 600)

        self.state = AppState()

        self._build_ui()

        # Initial values
        self.symbol_var.set(self.state.symbol)
        self.start_var.set(self.state.start.isoformat())
        self.end_var.set(self.state.end.isoformat())
        self.interval_var.set(self.state.interval)
        self.ma5_var.set(self.state.ma5)
        self.ma20_var.set(self.state.ma20)
        self.ma50_var.set(self.state.ma50)

        self._fetch_and_plot_async()

    # ---- UI ----
    def _build_ui(self):
        root = self

        # Top controls frame
        controls = ttk.Frame(root, padding=8)
        controls.pack(side=tk.TOP, fill=tk.X)

        # Row 1: symbol, dates, interval, load
        self.symbol_var = tk.StringVar()
        self.start_var = tk.StringVar()
        self.end_var = tk.StringVar()
        self.interval_var = tk.StringVar()

        ttk.Label(controls, text="Symbol").grid(row=0, column=0, sticky="w", padx=(0,4))
        ttk.Entry(controls, textvariable=self.symbol_var, width=12).grid(row=0, column=1, sticky="w")

        ttk.Label(controls, text="Start (YYYY-MM-DD)").grid(row=0, column=2, sticky="w", padx=(16,4))
        ttk.Entry(controls, textvariable=self.start_var, width=14).grid(row=0, column=3, sticky="w")

        ttk.Label(controls, text="End").grid(row=0, column=4, sticky="w", padx=(16,4))
        ttk.Entry(controls, textvariable=self.end_var, width=14).grid(row=0, column=5, sticky="w")

        ttk.Label(controls, text="Interval").grid(row=0, column=6, sticky="w", padx=(16,4))
        self.interval_cb = ttk.Combobox(
            controls, textvariable=self.interval_var, width=8, state="readonly",
            values=("1d","1wk","1mo","1h","30m","15m","5m","1m")
        )
        self.interval_cb.grid(row=0, column=7, sticky="w")

        self.load_btn = ttk.Button(controls, text="Load / Refresh", command=self._fetch_and_plot_async)
        self.load_btn.grid(row=0, column=8, padx=(16,0))

        # Row 2: quick ranges and MA toggles
        quick = ttk.Frame(controls)
        quick.grid(row=1, column=0, columnspan=9, sticky="w", pady=(8,0))

        ttk.Label(quick, text="Quick range:").pack(side=tk.LEFT, padx=(0,6))
        ranges = [
            ("1M", dict(days=30)),
            ("3M", dict(days=90)),
            ("6M", dict(days=182)),
            ("YTD", "ytd"),
            ("1Y", dict(days=365)),
            ("5Y", dict(days=365*5)),
            ("Max", "max"),
        ]
        for title, payload in ranges:
            ttk.Button(quick, text=title, command=lambda p=payload: self._set_quick_range(p)).pack(side=tk.LEFT, padx=2)

        # MAs
        self.ma5_var = tk.BooleanVar(value=True)
        self.ma20_var = tk.BooleanVar(value=True)
        self.ma50_var = tk.BooleanVar(value=True)

        ma_frame = ttk.Frame(controls)
        ma_frame.grid(row=2, column=0, columnspan=9, sticky="w", pady=(8,0))

        ttk.Label(ma_frame, text="Overlays:").pack(side=tk.LEFT, padx=(0,6))
        ttk.Checkbutton(ma_frame, text="MA5", variable=self.ma5_var, command=self._fetch_and_plot_async).pack(side=tk.LEFT,padx=2)
        ttk.Checkbutton(ma_frame, text="MA20", variable=self.ma20_var, command=self._fetch_and_plot_async).pack(side=tk.LEFT,padx=2)
        ttk.Checkbutton(ma_frame, text="MA50", variable=self.ma50_var, command=self._fetch_and_plot_async).pack(side=tk.LEFT,padx=2)

        ttk.Button(ma_frame, text="Save PNG…", command=self._save_png).pack(side=tk.LEFT, padx=(16,0))

        # Plot area
        self.plot_frame = ttk.Frame(root, padding=4)
        self.plot_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.fig = Figure(figsize=(10,6), dpi=100)
        self.ax_price = self.fig.add_subplot(2,1,1)
        self.ax_vol = self.fig.add_subplot(2,1,2, sharex=self.ax_price)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.toolbar = NavigationToolbar2Tk(self.canvas, self.plot_frame)
        self.toolbar.update()

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status = ttk.Label(root, textvariable=self.status_var, anchor="w", relief=tk.SUNKEN, padding=4)
        status.pack(side=tk.BOTTOM, fill=tk.X)

        for i in range(9):
            controls.grid_columnconfigure(i, weight=1 if i in (3,5) else 0)

    # ---- Quick ranges ----
    def _set_quick_range(self, payload):
        today = dt.date.today()
        if payload == "ytd":
            start = dt.date(today.year, 1, 1)
            end = today
        elif payload == "max":
            # Yahoo! Finance 'max' range is handled by leaving dates blank; but we set a very early start.
            start = dt.date(1980, 1, 1)
            end = today
        else:
            delta = dt.timedelta(**payload)
            start = today - delta
            end = today

        self.start_var.set(start.isoformat())
        self.end_var.set(end.isoformat())
        self._fetch_and_plot_async()

    # ---- Fetch + Plot ----
    def _fetch_and_plot_async(self):
        # Read state and validate before launching thread
        try:
            symbol = (self.symbol_var.get() or "").strip().upper()
            if not symbol:
                raise ValueError("Ticker cannot be empty")

            start = parse_date(self.start_var.get(), dt.date.today() - dt.timedelta(days=365))
            end = parse_date(self.end_var.get(), dt.date.today())
            if end < start:
                raise ValueError("End date is before start date")

            interval = self.interval_var.get() or "1d"
        except Exception as e:
            messagebox.showerror("Input error", str(e))
            return

        self.load_btn.configure(state=tk.DISABLED)
        self.status_var.set(f"Loading {symbol} {interval} from {start} to {end}…")

        t = threading.Thread(target=self._fetch_and_plot, args=(symbol, start, end, interval), daemon=True)
        t.start()

    def _fetch_and_plot(self, symbol: str, start: dt.date, end: dt.date, interval: str):
        try:
            # yfinance end date is exclusive for daily+; add one day to include 'end'
            end_inclusive = end + dt.timedelta(days=1)
            df = yf.download(symbol, start=start.isoformat(), end=end_inclusive.isoformat(), interval=interval, progress=False, auto_adjust=True, threads=True)
            if df is None or df.empty:
                raise RuntimeError("No data returned. Try a different symbol, date range, or interval.")
            # Ensure DateTimeIndex in local tz naive
            df = df.copy()
            df.index = pd.to_datetime(df.index)

        except Exception as e:
            self.after(0, lambda: self._on_fetch_error(e))
            return

        # Compute MAs
        price_col = "Adj Close" if "Adj Close" in df.columns else "Close"
        ma_cols = []
        if self.ma5_var.get():
            df["MA5"] = df[price_col].rolling(window=5).mean()
            ma_cols.append("MA5")
        if self.ma20_var.get():
            df["MA20"] = df[price_col].rolling(window=20).mean()
            ma_cols.append("MA20")
        if self.ma50_var.get():
            df["MA50"] = df[price_col].rolling(window=50).mean()
            ma_cols.append("MA50")

        # Plot on UI thread
        self.after(0, lambda: self._draw_plot(symbol, df, price_col, ma_cols, interval, start, end))

    def _on_fetch_error(self, e: Exception):
        self.load_btn.configure(state=tk.NORMAL)
        self.status_var.set("Error")
        messagebox.showerror("Download error", str(e))

    def _draw_plot(self, symbol: str, df: pd.DataFrame, price_col: str, ma_cols: list, interval: str, start: dt.date, end: dt.date):
        self.fig.clear()
        self.ax_price = self.fig.add_subplot(2,1,1)
        self.ax_vol = self.fig.add_subplot(2,1,2, sharex=self.ax_price)

        self.ax_price.plot(df.index, df[price_col], linewidth=1.2, label=price_col)
        for c in ma_cols:
            self.ax_price.plot(df.index, df[c], linewidth=1.0, linestyle="--", label=c)

        self.ax_price.set_title(f"{symbol}  •  {price_col}  •  {interval}   ({start} → {end})")
        self.ax_price.set_ylabel("Price")
        self.ax_price.grid(True, linestyle=":", alpha=0.5)
        self.ax_price.legend(loc="upper left", fontsize=9)

        if "Volume" in df.columns:
            try:
            # Pre-coerce Volume if present
                vol = df['Volume'].to_numpy()
                lst = [v[0] for v in vol]
                self.ax_vol.bar(df.index, lst, linewidth=0)  # <- key fix
            except Exception as e:
                messagebox.showerror("Volume error", str(e))
            self.ax_vol.set_ylabel("Volume")
            self.ax_vol.grid(True, linestyle=":", alpha=0.3)

        self.ax_vol.xaxis.set_major_locator(mdates.AutoDateLocator())
        self.ax_vol.xaxis.set_major_formatter(mdates.ConciseDateFormatter(mdates.AutoDateLocator()))
        for label in self.ax_vol.get_xticklabels():
            label.set_rotation(0)

        self.fig.tight_layout()
        self.canvas.draw_idle()

        self.status_var.set(f"Loaded {symbol}: {len(df)} rows")
        self.load_btn.configure(state=tk.NORMAL)

    # ---- Save ----
    def _save_png(self):
        fname = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG Image","*.png")],
            title="Save chart as PNG"
        )
        if not fname:
            return
        try:
            self.fig.savefig(fname, dpi=150, bbox_inches="tight")
            self.status_var.set(f"Saved: {fname}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))


if __name__ == "__main__":
    app = StockApp()
    # Use ttk theme if available
    try:
        style = ttk.Style(app)
        # Choose a platform-appropriate theme
        preferred = "vista" if app.tk.call("tk", "windowingsystem") == "win32" else "clam"
        style.theme_use(preferred)
    except Exception:
        pass
    app.mainloop()
