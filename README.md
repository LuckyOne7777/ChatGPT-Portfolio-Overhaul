# ChatGPT Micro-Cap Portfolio Tracker

A Flask + Python app that tracks and visualizes a simulated portfolio’s performance, comparing it to the S&P 500 baseline.  
Originally built for my AI-led micro-cap experiment, now open for others to use.

### Frontend Help Wanted!!!

I’m currently looking for **frontend contributors** to help improve the project’s UI.  

Areas where help is needed:  
-  Graph rendering (fixing data points not loading properly)  
-  Email login page (debugging and styling issues)  
-  General UI/UX improvements  

Check out the [Contributing Guide](https://github.com/LuckyOne7777/ChatGPT-Portfolio-Overhaul/blob/main/CONTRIBUTING.md) to learn how to get involved.


**Note: Very early in devolopment. Some features won't work as expected.**

---

## Features
- **Portfolio processing** – Calculates current equity, PnL, and cash after each run.
- **SPX baseline comparison** – Always aligned to the same number of data points as the portfolio.
- **Graph generation** – Side-by-side chart of ChatGPT's portfolio vs. S&P 500.
- **Date alignment fixes** – weekends/holidays forward-filled so both data sets match exactly.
- **Duplicate prevention** – If you process the portfolio multiple times in a day, previous rows for that day are overwritten.
- **Authentication** – Each user has their own portfolio & CSV logs (Flask + SQLite).
- **Deployed capital tracking** – Accurate across sessions.

---

## How To Run
First, install necessary libraries:

```bash
pip install -r requirements.txt
```

Then run the script `app.py`.

```bash
python portfolio_app/app.py
```

The output should look like this:
```bash
 * Serving Flask app 'app'
 * Debug mode: on
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on http://127.0.0.1:5000
Press CTRL+C to quit
 * Restarting with watchdog (windowsapi)
 * Debugger is active!
 * Debugger PIN: 575-595-068
```

Open the link `http://127.0.0.1:5000` in your browser (CTRL + click in most terminals).

That's it! from there you can interact with the webpage.

## Contact

Find a bug or have a suggestion?

Gmail: nathanbsmith.business@gmail.com 





