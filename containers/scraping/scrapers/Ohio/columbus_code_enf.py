import os
import time
import math
import datetime
import pytz
import pandas as pd
import undetected_chromedriver as uc
import chromedriver_autoinstaller
from sodapy import Socrata
from datetime import datetime, timedelta
from dotenv import load_dotenv
from utils.lead_database import Lead, Session
from utils.lead_database_operations import add_lead_to_database
from utils.util import get_zipcode, curr_date, status_print, clean_string
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import Select
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options


class ColumbusCodeEnf:
    def __init__(self):
        # Initialization

        self.scraper_name = "columbus_code_enf.py"
        self.county_website = "Columbus Code Enforcement"
        self.url = "https://portal.columbus.gov/permits"



        # Path to the GeckoDriver executable
        gecko_driver_path = '/path/to/geckodriver'

        # Path to the extracted uBlock Origin extension directory
        extension_path = './uBlock0_1.51.1b19.firefox.signed.xpi'

        # Configure Firefox options
        options = Options()
        options.headless = False  # Set to True if you want headless mode

        # Add the uBlock Origin extension
        options.add_argument(f'--extension={extension_path}')

        # Create a Firefox WebDriver instance with the configured options
        driver = webdriver.Firefox(path=gecko_driver_path, options=options)


        # Format date for file name
        current_date = datetime.now(pytz.timezone("America/New_York"))
        formatted_date = current_date.strftime("%Y%m%d")

        self.file_name = "RecordList" + formatted_date + ".csv"
        self.file_path = "/home/dylan/Downloads"
        # self.file_path = "/Users/dylanduhamel/Downloads"
        self.read_file = ""

        # List of keywords to exclude
        self.exclusions = [
            "Permit",
            "construction",
            "GVWR",
            "Builder",
            "vacant",
            "llc",
            "vehicle",
            "car",
            "cars",
            "pool",
            "smoke detector",
            "food truck",
        ]

        status_print(f"Initialized variables -- {self.scraper_name}")

    def download_dataset(self, days):
        status_print(
            f"Chrome driver created. Beginning scraping -- {self.scraper_name}"
        )

        # Compute yesterdays date for getting recent entries
        today = datetime.now()

        # Calculate yesterday's date
        yesterday = today - timedelta(days=days)

        # Format the date in the desired format (month/day/year)
        formatted_date = yesterday.strftime("%m/%d/%Y")

        # Start driver
        self.driver.get(self.url)

        # This will set the value to `undefined`
        self.driver.execute_script("delete navigator.webdriver;")

        try:
            # Wait for a specific element to be present
            element = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except TimeoutException:
            print("Timeout, body not found")

        time.sleep(100)

        # Violations records button
        try:
            # Execute JS event
            js_script = "__doPostBack('ctl00$PlaceHolderMain$TabDataList$TabsDataList$ctl08$LinksDataList$ctl00$LinkItemUrl','')"
            self.driver.execute_script(js_script)
        except NoSuchElementException:
            print("Can not find dropdown.")

        try:
            # Wait for a specific element to be present
            element = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located(
                    (By.ID, "ctl00_PlaceHolderMain_lblPermitListTitle")
                )
            )
        except TimeoutException:
            print("Timeout, record list not found")

        # Time input start
        try:
            # Change the search date range
            start_date_input = self.driver.find_element(
                By.ID, "ctl00_PlaceHolderMain_generalSearchForm_txtGSStartDate"
            )
            # Use JavaScript to set the value of the element
            self.driver.execute_script(
                """
            arguments[0].value = arguments[1];
            arguments[0].dispatchEvent(new Event('change'));
            """,
                start_date_input,
                formatted_date,
            )
        except NoSuchElementException:
            print("Can not input box.")

        # Search
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.ID, "ctl00_PlaceHolderMain_btnNewSearch")
                )
            )
            self.driver.find_element(
                By.ID, "ctl00_PlaceHolderMain_btnNewSearch"
            ).click()
        except NoSuchElementException:
            print("Can not find search button")

        # Download csv
        try:
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located(
                    (
                        By.ID,
                        "ctl00_PlaceHolderMain_dgvPermitList_gdvPermitList_gdvPermitListtop4btnExport",
                    )
                )
            )
            self.driver.find_element(
                By.ID,
                "ctl00_PlaceHolderMain_dgvPermitList_gdvPermitList_gdvPermitListtop4btnExport",
            ).click()
        except NoSuchElementException:
            print("Can not find download button.")

        # Wait for the file to be downloaded
        while not os.path.exists(os.path.join(self.file_path, self.file_name)):
            time.sleep(1)

        # Relinquish resources
        self.driver.quit()

        status_print(f"Scraping complete. Driver relinquished -- {self.scraper_name}")

    def start(self):
        status_print(f"Beginning data format and transfer to DB -- {self.scraper_name}")

        # Create a new database Session
        session = Session()

        # Path to downloaded CSV
        # Format for local data set
        self.read_file = self.file_path + "/" + self.file_name

        try:
            # Load the csv file into a DataFrame
            df = pd.read_csv(self.read_file)
        except Exception as e:
            print(f"Failed to load CSV file: {e}")
            exit()

        # Convert the Description to lowercase for case-insensitive matching
        df["Description"] = df["Description"].str.lower()

        # Handle empty or missing values
        df = df.dropna(subset=["Address", "Description"])

        # Create a new DataFrame to drop exclusions
        selected_rows = pd.DataFrame(columns=df.columns)

        # Remove rows where an exclusion keyword is found
        for exclusion in self.exclusions:
            selected_rows = selected_rows[
                ~selected_rows["Description"].str.contains(exclusion.lower())
            ]

        # Remove rows where status is closed
        selected_rows = selected_rows[~selected_rows["Status"].str.contains("Closed")]

        # Split the 'Address' field into separate 'Address', 'City_State_Zip' fields
        selected_rows[["Address", "City_State_Zip"]] = selected_rows[
            "Address"
        ].str.split(",", n=1, expand=True)

        # Split the 'City_State_Zip' field into separate 'City', 'State_Zip' fields
        selected_rows[["City", "State_Zip"]] = selected_rows[
            "City_State_Zip"
        ].str.split("OH", n=1, expand=True)

        # Split the 'State_Zip' field into separate 'State', 'Zip' fields
        selected_rows[["State", "Zip"]] = selected_rows["State_Zip"].str.split(
            " ", n=1, expand=True
        )

        # Remove unnecessary columns
        selected_rows = selected_rows.drop(
            columns=[
                "Record Number",
                "Status",
                "Related Records",
                "City_State_Zip",
                "State_Zip",
            ]
        )

        # Populate 'State' column with 'FL'
        selected_rows["State"] = "OH"

        # Reorder the columns
        selected_rows = selected_rows[
            ["Address", "City", "State", "Zip", "Description"]
        ]

        # Remove duplicates based on 'Address'
        selected_rows = selected_rows.drop_duplicates(subset="Address")

        records = selected_rows.to_dict("records")

        status_print(f"Adding records to database -- {self.scraper_name}")

        # Iterate through records
        for record in records:
            # Create new lead
            lead = Lead()

            # Date added to DB
            time_stamp = curr_date()
            lead.date_added = time_stamp

            # Document type
            lead.document_type = "Code Enforcement"

            # Document subtype & description
            lead.document_subtype = record["Description"]

            # Document address
            lead.property_address = clean_string(record["Address"])

            # Document Zip
            lead.property_zipcode = clean_string(record["Zip"])

            # City and State
            lead.property_city = clean_string(record["City"])
            lead.property_state = clean_string(record["State"])

            # Website tracking
            lead.county_website = self.county_website

            print(lead)
            print("\n")

            # session.add(lead)

        # Add new session to DB
        # session.commit()
        # Relinquish resources
        # session.close()

        # Delete the file so it can be run again
        # os.remove(os.path.join(self.file_path, self.file_name))

        status_print(
            f"DB committed and {self.file_name} removed -- {self.scraper_name}"
        )
