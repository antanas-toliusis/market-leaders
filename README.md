# Market Leaders vs Index

A one-page screener of S&P 500 stocks whose relative strength beats the index (S&P 500, equal-weight S&P 500 or Nasdaq-100).

- **RS rating (1–99):** IBD-style 12-month weighted performance (40% latest quarter, 20% each earlier quarter), as a percentile across S&P 500 members. Only stocks scoring above the index are listed.
- **Relative performance:** (1 + stock return) / (1 + index return) − 1 over 1, 3, 6 and 12 months.
- **RS line:** stock price ÷ index price.

Prices refresh automatically every weekday night via GitHub Actions (`.github/workflows/update-data.yml`), using the point-in-time dataset at [Johnbrick123/sp500-data](https://github.com/Johnbrick123/sp500-data) and GICS sectors from [datasets/s-and-p-500-companies](https://github.com/datasets/s-and-p-500-companies).

To refresh manually: Actions → Update prices → Run workflow.

This is a screen, not investment advice.
