from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import os
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize the OpenAI model
model = ChatOpenAI(model='gpt-4o', temperature=0.5)

# Function to scrape trending topics in Saudi Arabia
def scrape_saudi_trends():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    try:
        driver.get("https://getdaytrends.com/saudi-arabia/")
        driver.implicitly_wait(10)
        trends = driver.find_elements(By.CSS_SELECTOR, "td.main")
        trending_topics = [trend.text for trend in trends if trend.text.strip()]
        return trending_topics
    except Exception as e:
        print(f"Error occurred: {e}")
        return []
    finally:
        driver.quit()

# Function to process the trends list with the enhanced prompt
def get_top_30_keywords(trendsList, model):
    template = """
The top 30 trending topics in Saudi Arabia are: {trendsList}.  
Using these topics, identify 30 relevant keywords that are likely to generate the highest engagement. These keywords should reflect common themes, important names, events, or culturally significant terms.  
Exclude generic words such as "day," "number," "trend," or other overly broad terms unless they are contextually essential.  
Also, omit any topics or keywords related to politics.  
Ensure the output is formatted as a comma-separated list of unique and meaningful keywords optimized for engagement.
    """
    prompt = ChatPromptTemplate.from_template(template)
    chain = prompt | model
    return chain.invoke({"trendsList": trendsList}).content

# Function to update Google Sheet
def update_google_sheet(sheet_name, keywords):
    try:
        # Authenticate and connect to Google Sheets
        scope = ["https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        client = gspread.authorize(creds)
        # spreadsheets = client.openall()
        # for sheet in spreadsheets:
        #     print(sheet.title)

        # Open the sheet
        sheet = client.open(sheet_name).sheet1

        # Update the sheet with keywords
        for idx, keyword in enumerate(keywords.split(','), start=2):
            sheet.update_cell(idx, 1, keyword.strip())  # Write each keyword in the first column

        # add timestamp
        time_now = time.strftime("%Y-%m-%d %H:%M:%S")
        cell_time_formated = "Last Updated: " + time_now
        sheet.update_cell(2, 3, cell_time_formated)

    except gspread.exceptions.SpreadsheetNotFound:
        print(f"Error: Google Sheet '{sheet_name}' not found. Check the name and permissions.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


# Main execution
if __name__ == "__main__":
    while True:
        start_time = time.time()
        # Step 1: Scrape trending topics
        saudi_trends = scrape_saudi_trends()
        print("Trending Topics in Saudi Arabia:")
        for idx, trend in enumerate(saudi_trends, start=1):
            print(f"{idx}. {trend}")

        # Step 2: Process trends list to generate keywords
        if saudi_trends:
            trendsList = ", ".join(saudi_trends)
            top_30_keywords = get_top_30_keywords(trendsList, model)

            # Step 3: Update Google Sheet
            sheet_name = "Trending Keywords Saudi"  
            
            update_google_sheet(sheet_name, top_30_keywords)

            print("\nTop 30 Keywords updated in Google Sheet:")
            print(top_30_keywords)
        else:
            print("No trends found. Exiting.")

        # Print execution time
        print(f"\nTime taken in minutes: {(time.time() - start_time)/60:.2f}")

        # Wait for 1 hours before running the script again
        print("Script will run again after 1 hours...\n")
        time.sleep(3600) # Sleep for 1 
        

# host server onshobbak  
# fetch tweets 