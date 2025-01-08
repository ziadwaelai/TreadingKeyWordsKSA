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
def get_top_30_keywords(trending_topics, query, model):
    template = """
    I have the following marketing query: "{query}". 
    Generate a list of the **most relevant and localized Arabic Saudi Arabia keywords** strictly related to this query. 
    You may use these Saudi Arabia trending topics for inspiration: {trending_topics}. 
    Ensure all generated keywords are directly related to the query and avoid unrelated trending topics.
    It's better that the keywords to be single word.
    The output should be a list of keywords separated by commas.
    """


    prompt = ChatPromptTemplate.from_template(template)
    chain = prompt | model

    # Pass trending_topics and query correctly
    return chain.invoke({"trending_topics": trending_topics, "query": query}).content


# Function to update Google Sheet
def update_google_sheet(sheet_name, query_keyword_map, client):
    try:
        sheet = client.open(sheet_name).worksheet("OUTPUT")

        # Clear the sheet before writing
        sheet.clear()

        # Write the headers
        sheet.update("A1", [["Query", "Keywords"]])  # Headers in Row 1

        # Prepare rows for each query and its keywords
        rows = []
        for query, keywords in query_keyword_map.items():
            rows.append([query, ", ".join(keywords)])  # Convert keyword list to comma-separated string

        # Update the sheet with new rows starting from row 2
        sheet.update("A2", rows)

        print("Google Sheet updated successfully!")

    except gspread.exceptions.SpreadsheetNotFound:
        print(f"Error: Google Sheet '{sheet_name}' not found. Check the name and permissions.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")



def is_cell_ready(sheet_name,client):
    try:
        # Open the Google Sheet and select the sheet named 'OUTPUT'
        sheet = client.open(sheet_name).worksheet('INPUT')

        # Get the value of cell D2
        cell_value = sheet.acell('D2').value

        # Check if the value is "Ready"
        return cell_value == "Ready"

    except gspread.exceptions.SpreadsheetNotFound:
        print(f"Error: Google Sheet '{sheet_name}' not found. Check the name and permissions.")
        return False
    except gspread.exceptions.WorksheetNotFound:
        print(f"Error: Worksheet 'OUTPUT' not found in the Google Sheet '{sheet_name}'.")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return False


def update_cell(sheet_name, cell_address, value,client):
    try:

        # Open the Google Sheet and worksheet
        sheet = client.open(sheet_name)
        worksheet = sheet.worksheet("INPUT")

        # Update the specified cell
        worksheet.update_acell(cell_address, value)

        print(f"Updated cell {cell_address} in worksheet 'OUTPUT' with value: {value}")
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"Error: Google Sheet '{sheet_name}' not found. Check the name and permissions.")
    except gspread.exceptions.WorksheetNotFound:
        print(f"Error: Worksheet 'OUTPUT' not found in the Google Sheet '{sheet_name}'.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


def get_queries(sheet_name, client, column="A"):
    try:
        # Open the sheet and worksheet
        sheet = client.open(sheet_name)
        worksheet = sheet.worksheet("INPUT")

        # Fetch all values from the specified column
        queries = worksheet.col_values(ord(column.upper()) - 64)  # Convert column letter to number
        return [query.strip() for query in queries if query.strip()]  # Remove empty strings

    except gspread.exceptions.SpreadsheetNotFound:
        print(f"Error: Google Sheet '{sheet_name}' not found. Check the name and permissions.")
        return []
    except gspread.exceptions.WorksheetNotFound:
        print(f"Error: Worksheet 'INPUT' not found in the Google Sheet '{sheet_name}'.")
        return []
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return []


# Main execution
if __name__ == "__main__":
    # Authenticate and connect to Google Sheets
    scope = ["https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    client = gspread.authorize(creds)

    sheet_name = "Trending Keywords Saudi Based on Input"

    while True:
        update_cell(sheet_name, "C2", "", client)
        if is_cell_ready(sheet_name, client):
            start_time = time.time()

            # Scrape trending topics
            saudi_trends = scrape_saudi_trends()
            if not saudi_trends:
                print("No trending topics found. Exiting.")
                break

            trending_topics = ", ".join(saudi_trends)

            # Fetch queries from the sheet
            queries = get_queries(sheet_name, client)
            if not queries:
                print("No queries found. Exiting.")
                break

            # Generate keywords for each query
            query_keyword_map = {}
            for query in queries:
                try:
                    keywords = get_top_30_keywords(trending_topics, query, model)
                    query_keyword_map[query] = [kw.strip() for kw in keywords.split(",") if kw.strip()]
                except Exception as e:
                    print(f"Error processing query '{query}': {e}")

            # Update Google Sheet
            # remove the first row from the query_keyword_map
            query_keyword_map.pop(queries[0])
            update_google_sheet(sheet_name, query_keyword_map, client)

            # Mark as done
            update_cell(sheet_name, "D2", "Not Ready", client)
            update_cell(sheet_name, "C2", "Done", client)

            print(f"Execution time: {time.time() - start_time:.2f} seconds.")
        else:
            print("Cell D2 is not ready. Waiting for input...")
        time.sleep(10)
