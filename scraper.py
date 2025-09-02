import time
import argparse
import json
import pandas as pd
from datetime import datetime, timedelta
from config import ALLOWED_ELEMENT_TYPES, ICON_COLOR_MAP
from utils import save_csv
import config
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


def init_driver(headless=True) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("window-size=1920x1080")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )

    print("Attempting to initialize WebDriver with ChromeDriverManager...")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    print("WebDriver initialized successfully using ChromeDriverManager.")
    return driver


def scroll_to_end(driver):
    previous_position = None
    while True:
        current_position = driver.execute_script("return window.pageYOffset;")
        driver.execute_script("window.scrollTo(0, window.pageYOffset + 500);")
        time.sleep(2)
        if current_position == previous_position:
            break
        previous_position = current_position


def parse_table(driver, month, year):
    data = []
    table = driver.find_element(By.CLASS_NAME, "calendar__table")

    for row in table.find_elements(By.TAG_NAME, "tr"):
        row_data = {}
        event_id = row.get_attribute("data-event-id")

        for element in row.find_elements(By.TAG_NAME, "td"):
            class_name = element.get_attribute('class')

            if class_name in ALLOWED_ELEMENT_TYPES:
                class_name_key = ALLOWED_ELEMENT_TYPES.get(
                    f"{class_name}", "cell")

                if "calendar__impact" in class_name:
                    impact_elements = element.find_elements(
                        By.TAG_NAME, "span")
                    color = None
                    for impact in impact_elements:
                        impact_class = impact.get_attribute("class")
                        color = ICON_COLOR_MAP.get(impact_class)
                    row_data[f"{class_name_key}"] = color if color else "impact"

                elif "calendar__detail" in class_name and event_id:
                    detail_url = f"https://www.forexfactory.com/calendar?month={month.lower()}.{year}#detail={event_id}"
                    row_data[f"{class_name_key}"] = detail_url
                elif class_name_key in ["forecast", "previous"]:
                    value = element.get_attribute('innerText')
                    value = value.strip() if value else ""
                    row_data[f"{class_name_key}"] = value if value else "empty"
                elif element.text:
                    row_data[f"{class_name_key}"] = element.text
                else:
                    row_data[f"{class_name_key}"] = "empty"

        if row_data:
            data.append(row_data)

    save_csv(data, month, year)

    return data, month


def get_target_month(arg_month=None):
    now = datetime.now()
    month = arg_month if arg_month else now.strftime("%B")
    year = now.strftime("%Y")
    return month, year

def generate_month_range(start_date, end_date):
    """Generate a list of (month, year) tuples between start_date and end_date"""
    months = []
    current = start_date.replace(day=1)  # Start from first day of the month
    
    while current <= end_date:
        months.append((current.strftime("%B"), current.year))
        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    
    return months


def parse_month_year_string(date_str):
    """Parse date string in format 'jan 2007', 'january 2007', 'Jan 2007', etc."""
    try:
        # Handle different month formats
        parts = date_str.strip().split()
        if len(parts) != 2:
            raise ValueError("Format should be 'month year' (e.g., 'jan 2007')")
        
        month_str, year_str = parts
        year = int(year_str)
        
        # Try full month name first
        try:
            month_num = datetime.strptime(month_str.capitalize(), "%B").month
        except ValueError:
            # Try abbreviated month name
            try:
                month_num = datetime.strptime(month_str.capitalize(), "%b").month
            except ValueError:
                raise ValueError(f"Invalid month: {month_str}")
        
        return datetime(year, month_num, 1)
        
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid date format: {date_str}. Use format like 'jan 2007' or 'january 2007'")


def scrape_month(month, year, url_param=None):
    """Scrape a single month"""
    if url_param:
        url = f"https://www.forexfactory.com/calendar?month={url_param}"
    else:
        month_abbr = month[:3].lower()
        url = f"https://www.forexfactory.com/calendar?month={month_abbr}.{year}"
    
    print(f"\n[INFO] Navigating to {url}")

    driver = init_driver()
    try:
        driver.get(url)
        detected_tz = driver.execute_script("return Intl.DateTimeFormat().resolvedOptions().timeZone")
        print(f"[INFO] Browser timezone: {detected_tz}")
        config.SCRAPER_TIMEZONE = detected_tz
        scroll_to_end(driver)

        print(f"[INFO] Scraping data for {month} {year}")
        parse_table(driver, month, str(year))
        
    except Exception as e:
        print(f"[ERROR] Failed to scrape {month} {year}: {e}")
    finally:
        driver.quit()
        time.sleep(3)


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Forex Factory calendar.")
    parser.add_argument("--months", nargs="+",
                        help='Target months: e.g., this next')
    parser.add_argument("--start", 
                        help='Start month for range scraping (e.g., "jan 2007", "january 2007")')
    parser.add_argument("--end", 
                        help='End month for range scraping (e.g., "jun 2007", "june 2007")')

    args = parser.parse_args()

    # Handle date range scraping
    if args.start and args.end:
        try:
            start_date = parse_month_year_string(args.start)
            end_date = parse_month_year_string(args.end)
            
            if start_date > end_date:
                print("[ERROR] Start date must be before end date")
                return
            
            print(f"[INFO] Scraping date range: {start_date.strftime('%B %Y')} to {end_date.strftime('%B %Y')}")
            
            months_to_scrape = generate_month_range(start_date, end_date)
            
            for month, year in months_to_scrape:
                scrape_month(month, year)
                
        except ValueError as e:
            print(f"[ERROR] {e}")
            return
    
    # Handle individual month parameters (existing functionality)
    elif args.months is not None or (not args.start and not args.end):
        month_params = args.months if args.months else ["this"]

        for param in month_params:
            param = param.lower()
            
            # Determine readable month name and year
            if param == "this":
                now = datetime.now()
                month = now.strftime("%B")
                year = now.year
                scrape_month(month, year, param)
            elif param == "next":
                now = datetime.now()
                next_month = (now.month % 12) + 1
                year = now.year if now.month < 12 else now.year + 1
                month = datetime(year, next_month, 1).strftime("%B")
                scrape_month(month, year, param)
            else:
                month = param.capitalize()
                year = datetime.now().year
                scrape_month(month, year, param)
    
        print("[ERROR] Please provide both --start and --end together for date range scraping. Only one was provided.")


if __name__ == "__main__":
    main()
