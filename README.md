# Tokopedia Reviews Scraper

Tokopedia reviews scraper using pyppeteer.
```
tokped-reviws-scraper.py --url <reviews url> --output <output csv> --chrome-path <path to chromium executable> [--headless]
```
Recommended to use an existing chrome executable. I haven't gotten the automatic installation to work.

Increase the timeout if the reviews in the next page haven't changed and it saves duplicates of the previous page. 
