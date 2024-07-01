import datetime
import logging
import time

from bs4 import BeautifulSoup
from dateutil.parser import parse
from dateutil.rrule import DAILY, rrule
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from utils.lead_database import Lead, Session
from utils.lead_database_operations import add_lead_to_database
from utils.util import curr_date, status_print

logging.basicConfig(
    filename="processing.log", level=logging.ERROR, format="%(asctime)s - %(message)s"
)


class NassauCountyTaxdeed:
    def __init__(self):
        # Initialization

        # Chrome driver
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        self.driver = webdriver.Chrome(options=options)

        # This is used for status tracking
        self.scraper_name = "nassau_county_taxdeed.py"
        self.county_website = "Nassau County Taxdeed"

        status_print(f"Initialized variables -- {self.scraper_name}")

    def start(self, end_date):
        # Get today's date and add one day to get tomorrow's date
        start_date = datetime.datetime.now() + datetime.timedelta(days=1)
        end_date = parse(end_date)
        # Generate a list of all dates from start_date to end_date
        dates = list(rrule(DAILY, dtstart=start_date, until=end_date))

        # Create new database session
        session = Session()

        # Iterate over the dates CLERMONT
        for date in dates:
            # Get URL with current date
            self.url = f"https://nassau.realtaxdeed.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE={date}"
            # Initialize driver
            self.driver.get(self.url)

            try:
                # Wait until an auction item is present in the webpage
                WebDriverWait(self.driver, 1.0).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "AUCTION_ITEM"))
                )

                # Wait if the element is loading the waiting records
                WebDriverWait(self.driver, 10).until_not(
                    EC.presence_of_element_located((By.CLASS_NAME, "Loading"))
                )

                html_doc = self.driver.page_source
                soup = BeautifulSoup(html_doc, "html.parser")

                # Check number of pages
                max_pages_elem = soup.find(id="maxWA")
                if max_pages_elem:
                    try:
                        max_pages = int(max_pages_elem.get_text(strip=True))
                    except ValueError:
                        max_pages = 1
                else:
                    max_pages = 1

                all_items = []

                for current_page in range(1, max_pages + 1):
                    if current_page > 1:
                        # If it's not the first page, click the next page button
                        WebDriverWait(self.driver, 1.0).until(
                            EC.presence_of_element_located((By.CLASS_NAME, "PageRight"))
                        )
                        next_page_btn = self.driver.find_element(
                            By.CLASS_NAME, "PageRight"
                        )
                        next_page_btn.click()

                        # Wait until an auction item is present in the webpage
                        time.sleep(2)

                        # Wait for the page to load
                        WebDriverWait(self.driver, 10).until_not(
                            EC.presence_of_element_located((By.CLASS_NAME, "Loading"))
                        )

                        # Parse the new page source
                        html_doc = self.driver.page_source
                        soup = BeautifulSoup(html_doc, "html.parser")

                    # Extract items
                    head_w_div = soup.find(class_="Head_W")
                    items = head_w_div.find_all(class_="AUCTION_ITEM")
                    all_items.extend(items)

                for item in all_items:
                    details_table = item.find(class_="AUCTION_DETAILS")
                    rows = details_table.find_all("tr")
                    data = {
                        row.th.get_text(strip=True): row.td.get_text(strip=True)
                        for row in rows
                    }

                    auction_type = data.get("Auction Type:", None)
                    property_address = data.get("Property Address:", None)
                    appraised_value = data.get("Appraised Value:", None)

                    # Find city and zip code
                    for i, row in enumerate(rows):
                        if row.th.get_text(strip=True) == "Property Address:":
                            city_zip_data = rows[i + 1].td.get_text(strip=True)
                            break
                    else:
                        city_zip_data = None

                    # Getting city and zip data extracted
                    try:
                        if city_zip_data is not None and "FL-" in city_zip_data:
                            city, zip_code = map(str.strip, city_zip_data.split(","))
                            zip_code = zip_code.split("- ")[1]
                        else:
                            raise ValueError("City zip data is None")
                    except ValueError as e:
                        print(f"Error splitting city and zip data: '{e}'")
                        city, zip_code = None, None

                    # Find Auction type [Document type]
                    for i, row in enumerate(rows):
                        if row.th.get_text(strip=True) == "Auction Type:":
                            self.auction_type_data = rows[i].td.get_text(strip=True)
                            break
                    else:
                        self.auction_type_data = f"N/A - {self.county_website}"

                    # Check if it has been seen before
                    if property_address is not None:
                        # Check if the first segment of the address (before the first space) is a full number
                        first_segment = property_address.split(" ")[0]
                        if not first_segment.isdigit():
                            # It's not a valid address, so skip this iteration of the loop
                            continue

                        # Create new lead
                        lead = Lead()

                        # Document type
                        lead.document_type = (
                            "Foreclosure"
                            if self.auction_type_data == "FORECLOSURE"
                            else (
                                "Taxdeed"
                                if self.auction_type_data == "TAXDEED"
                                else self.auction_type_data
                            )
                        )

                        # Address
                        lead.property_address = property_address

                        # City and State
                        lead.property_city = city
                        lead.property_zipcode = zip_code[:5]
                        lead.property_state = "Florida"

                        # Website tracking
                        lead.county_website = self.county_website

                        # print(lead)
                        # print("\n")

                        # Add lead to db
                        session.add(lead)

                        # Add to visited list

            except Exception as e:
                print(f"AUCTION_ITEM element not found. Moving on.")

        # Add new session to DB
        session.commit()
        # Relinquish resources
        session.close()

        # Relinquish resources
        self.driver.quit()

        status_print(f"DB committed -- {self.scraper_name}")
