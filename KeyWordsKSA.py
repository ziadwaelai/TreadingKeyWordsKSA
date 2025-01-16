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
import requests
import json
from datetime import datetime

# API URL and file path
API_URL = "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/riyadh?unitGroup=metric&key=T6LYPSLMFG8EB9RJ99MCG4SC8&contentType=json"
FILE_PATH = "weather_data.txt"


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize the OpenAI model
model = ChatOpenAI(model='gpt-4o', temperature=0.5)

def get_weather_data():
    """Fetch weather data from the API and save it if it's a new day."""
    today = datetime.now().strftime("%Y-%m-%d")
    
    try:
        # Check if the file exists and has today's data
        with open(FILE_PATH, "r") as file:
            saved_data = json.load(file)
            if saved_data.get("date") == today:
                print("Weather data is already saved for today.")
                return saved_data
    
    except (FileNotFoundError, json.JSONDecodeError):
        # File doesn't exist or is not valid JSON, proceed to fetch data
        pass

    # Fetch data from the API
    print("Fetching new weather data from the API...")
    response = requests.get(API_URL)
    
    if response.status_code == 200:
        data = response.json()
        weather_info = {
            "date": today,
            "city": data["address"],
            "temperature": data["days"][0]["temp"],
            "humidity": data["days"][0]["humidity"],
            "conditions": data["days"][0]["conditions"],
            "description": data["days"][0]["description"]
        }

        # Save the new data to the file
        with open(FILE_PATH, "w") as file:
            json.dump(weather_info, file, indent=4)
        
        print("Weather data saved successfully.")
        return weather_info
    else:
        print(f"Failed to fetch weather data. Status code: {response.status_code}")
        return None
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
def get_top_50_keywords(trendsList,weather, model):
    template = """
        Analyze the following trending topics in Saudi Arabia on Twitter (X): {trending_topics}.  
        Additionally, use the {current_weather} weather conditions in Saudi Arabia to identify seasonally relevant keywords.  
        Your task is to generate **up to 50 meaningful Arabic keywords** for content strategy that reflect cultural, seasonal, and local relevance.  

        ### **Guidelines**  
        1. **Cultural and Regional Relevance**:  
        - Focus on the local Saudi dialect ("اللهجة السعودية").  
        - Include terms tied to traditions, events, or locations (e.g., الرياض, جدة, مكة).  
        - Incorporate cultural or national celebrations (e.g., العيد, الحج, اليوم الوطني).  

        2. **Seasonal Relevance**:  
        - For **cold weather**: Include winter-related activities, foods, clothing, or gatherings (e.g., "شتوية," "شال," "جلسة شتوية").  
        - For **hot weather**: Highlight summer-related activities, refreshment, and outdoor fun (e.g., "بحر," "رحلات," "حر").  
        - For **neutral weather**: Focus on cultural events, festivals, and everyday trending phrases.  

        3. **Exclusions**:  
        - **Sports Topics**: Avoid sports-related terms, including team names, matches, or events.  
        - Generic pan-Arabic terms unless highly significant in Saudi Arabia.  
        - Stop words (e.g., "من", "في", "على", "إلى", "هو", "هي", "ما").  
        - Irrelevant content, including:  
            - Political terms.  
            - Personal names unless related to culture, entertainment, or history.  
            - Explicit or inappropriate language.  
        - Hashtags (#) and mentions (@): Extract meaningful content (e.g., "#جلسة_شتوية" → "جلسة شتوية").  

        4. **Formatting**:  
        - Return the keywords as a **clean, comma-separated list**: `keyword1, keyword2, keyword3, ...`.  
        - Ensure all keywords are concise, unique, and culturally relevant.  

        ### **Weather-Specific Notes**  
        - Use the {current_weather} conditions as a guide:  
        - **Cold**: Highlight keywords for winter-related activities, foods, or gatherings.  
        - **Hot**: Focus on summer activities, refreshment, and outdoor fun.  
        - **Neutral**: Prioritize cultural events, festivals, and everyday phrases.  

        ### **Final Output**  
        Provide a concise list of **up to 50 keywords** that reflect Saudi culture, current weather conditions, and Twitter trends. Avoid duplicates and formatting errors.
"""



    prompt = ChatPromptTemplate.from_template(template)
    chain = prompt | model
    return chain.invoke({"trending_topics": trendsList,"current_weather":weather}).content

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
        sheet = client.open(sheet_name).worksheet('Keywords')

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
        
        # Get weather data
        weather = get_weather_data()
        if weather is None:
            weather="the current weather is normal"
        
        # Step 2: Process trends list to generate keywords
        if saudi_trends:
            trendsList = ", ".join(saudi_trends)
            top_30_keywords = get_top_50_keywords(trendsList,weather, model)

            # Remove any duplicates
            top_30_keywords = ",".join(list(set(top_30_keywords.split(',')))) 

            # Step 3: Update Google Sheet
            sheet_name = "Trending Keywords Saudi Based on Input"  
            
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
        
