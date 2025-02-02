from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import os
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
import requests
import json
import re
from datetime import datetime

# Load environment variables
load_dotenv()

# API Credentials
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("Error: OPENAI_API_KEY is missing. Set it in your environment variables.")
if not WEATHER_API_KEY:
    raise ValueError("Error: WEATHER_API_KEY is missing. Set it in your environment variables.")

# API URL and File Path
API_URL = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/riyadh?unitGroup=metric&key={WEATHER_API_KEY}&contentType=json"
FILE_PATH = "weather_data.txt"

# Initialize OpenAI model
model = ChatOpenAI(model='gpt-4o', temperature=0.2)


# Function to fetch weather data
def get_weather_data():
    today = datetime.now().strftime("%Y-%m-%d")

    if os.path.exists(FILE_PATH):
        try:
            with open(FILE_PATH, "r") as file:
                saved_data = json.load(file)
                if saved_data.get("date") == today:
                    print("Weather data is already saved for today.")
                    return saved_data
        except json.JSONDecodeError:
            print("Warning: Corrupt weather data file. Refetching data...")

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

        with open(FILE_PATH, "w") as file:
            json.dump(weather_info, file, indent=4)

        print("Weather data saved successfully.")
        return weather_info

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
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "td.main")))

        trends = driver.find_elements(By.CSS_SELECTOR, "td.main")
        trending_topics = [trend.text.strip() for trend in trends if trend.text.strip()]

        return trending_topics

    except Exception as e:
        print(f"Error occurred: {e}")
        return []

    finally:
        driver.quit()

def get_historical_keywords(sheet_name, days=3):
    """Fetch historical keyword data dynamically, ensuring correct column detection from row 2."""
    try:
        # Connect to Google Sheets
        scope = ["https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        client = gspread.authorize(creds)

        sheet = client.open(sheet_name).worksheet("Keyword rate")  
        data = sheet.get_all_values()  

        if len(data) < 3:
            raise ValueError("❌ The sheet doesn't have enough rows to extract data.")

        headers = data[1]  # ✅ Row 2 contains "High", "Medium", "Low"
        total_columns = len(headers)  # Get the total number of columns

        if total_columns < days * 3:
            raise ValueError("❌ Not enough columns to extract the last three days.")

        historical_keywords = {"High": [], "Medium": [], "Low": []}

        # ✅ Extract data for the last `days`
        start_col = total_columns - (days * 3)  # Start from the last three days

        for i in range(start_col, total_columns, 3):  # Step by 3 columns per day (High, Medium, Low)
            try:
                high_col_index = i
                medium_col_index = i + 1
                low_col_index = i + 2
                high_keywords = [
                    re.sub(r"^\d+\s*-\s*", "", row[high_col_index])  
                    for row in data[2:] if len(row) > high_col_index and row[high_col_index].strip()
                ]
                medium_keywords = [
                    re.sub(r"^\d+\s*-\s*", "", row[medium_col_index])
                    for row in data[2:] if len(row) > medium_col_index and row[medium_col_index].strip()
                ]
                low_keywords = [
                    re.sub(r"^\d+\s*-\s*", "", row[low_col_index])
                    for row in data[2:] if len(row) > low_col_index and row[low_col_index].strip()
                ]
                historical_keywords["High"].extend(high_keywords)
                historical_keywords["Medium"].extend(medium_keywords)
                historical_keywords["Low"].extend(low_keywords)

            except IndexError:
                print(f"⚠️ Warning: Could not process data for column set {(i-start_col)//3 + 1}. Check column structure.")

        # Remove duplicates
        historical_keywords["High"] = list(set(historical_keywords["High"]))
        historical_keywords["Medium"] = list(set(historical_keywords["Medium"]))
        historical_keywords["Low"] = list(set(historical_keywords["Low"]))

        return historical_keywords

    except Exception as e:
        print(f"❌ Error fetching historical keywords: {e}")
        return {"High": [], "Medium": [], "Low": []}


    except Exception as e:
        print(f"❌ Error fetching historical keywords: {e}")
        return "in the last 3 days, the keywords are not available"


# **Agent 1: Clean and Filter Trending Topics**
def clean_trending_topics(trending_topics, historical_keywords):
    """
    Filters and refines trending topics based strictly on past performance.
    """
    template = """
    Analyze these trending Twitter (X) topics in Saudi Arabia: {trending_topics}.  

    **🔹 Strict Filtering Based on Historical Performance:**  
    - **High Engagement Keywords (Prioritize & Keep)**: {high_keywords}  
    - **Medium Engagement Keywords (Rework & Improve)**: {medium_keywords}  
    - **Low Engagement Keywords (Remove or Strongly Modify)**: {low_keywords}  

    **✅ Focus On:**  
    - Topics **strongly linked to high-engagement words from historical data**.  
    - Seasonal and **Saudi culturally relevant discussions**.  

    **❌ Strictly Avoid:**  
    - Generic pan-Arabic terms unless **historically successful**.  
    - Low-engagement topics **unless reworded into trending variations**.  
    - **Irrelevant or off-topic** discussions.
    - **Sports-related topics**
    - **Political terms**
    - **Personal names** unless related to culture, entertainment.

    **🔄 Rework Instead of Removing:**  
    - If a medium or low-performing topic **can be improved**, return a stronger version.  

    **📝 Output Format:**  
    - **Return a comma-separated list of refined trending topics**.  
    - Example: "جلسة شتوية, رؤية 2030, مهرجان الرياض"
    """

    prompt = ChatPromptTemplate.from_template(template)
    chain = prompt | model
    response = chain.invoke({
        "trending_topics": trending_topics,
        "high_keywords": ", ".join(historical_keywords["High"]),
        "medium_keywords": ", ".join(historical_keywords["Medium"]),
        "low_keywords": ", ".join(historical_keywords["Low"]),
    }).content

    return response.split(", ")  # Ensure list output



# **Agent 2: Predict Most Frequent Words for Each Topic**
def predict_frequent_words(cleaned_topics, current_weather, historical_keywords):
    """
    Generates highly relevant words for trending topics using historical performance as the dominant factor.
    """
    template = """
    You must generate **EXACTLY between 45 and 50** culturally relevant Arabic keywords 
    (MUST BE **one-word** terms) for Saudi Twitter (X). 

    **NON-NEGOTIABLE Requirements**:
    1. **All 'High' engagement keywords** must appear in **identical form** (no changes).
    2. **Include a few 'Medium' keywords** but reworked/optimized if needed.
    3. **Avoid or rework 'Low' keywords** unless there's a strong reason to keep them.
    4. **At least 80%** of your final output must be **one-word** terms 
       (e.g., "مطر" or "شتاء" not "مطر غزير").
    6. **Use Najdi/Hijazi dialect** or comedic phrases where suitable.
    7. **No duplicates**. If a word is repeated in historical data, 
       only include it once in the final list.

    **Output Format**:
    - Return a **comma-separated list** of **45–50** unique words 
      (each item is a single Arabic term, except 'High' words if they have 2 words).
    - Example: 
      "مطر, شاهي, الجامعة, برد, شتاء, اجواء, فطور, ضباب, كرك, بطانيات, ..."

    **Context**:
    - Treanding Topics in KSA: {cleaned_topics}
    - Weather Now in KSA: {current_weather}
    - Historical Keywords that used for last 3 days:
        - High Engagement (include exactly): {high_keywords}
        - Medium Engagement (modify as needed): {medium_keywords}
        - Low Engagement (fix or remove): {low_keywords}
    """

    prompt = ChatPromptTemplate.from_template(template)
    chain = prompt | model

    response = chain.invoke({
        "cleaned_topics": ", ".join(cleaned_topics),
        "current_weather": current_weather,
        "high_keywords": ", ".join(historical_keywords["High"]),
        "medium_keywords": ", ".join(historical_keywords["Medium"]),
        "low_keywords": ", ".join(historical_keywords["Low"]),
    }).content

    return response.split(", ")  # Structured list output

# **Agent 3: Localize Keywords for Saudi Arabia**
def localize_keywords_ksa(predicted_words,high_keywords):
    """
    Localizes keywords strictly based on historical success, dialect, and humor.
    """
    template = """
    **Transform the following words into hyper-localized Saudi terms**  
    ensuring that **most words remain ONE WORD** unless necessary for improvement. 
    **Use Saudi dialects, humor, and cultural relevance** to enhance the keywords.
    **Make sure that the final list is between 45 and 50 words**.

    **✅ Localization Rules**  
    - Convert **MSA to Saudi dialects** (Najdi, Hijazi).  
    - Adapt words to **weather trends** (cold, heat, sandstorms).  
    - **Ensure at least 80% of words remain one-word terms**.  
    - **No weak past words unless fully reworked**.  
    - **Use Saudi humor & meme culture** (if applicable).
    - **retrun the high keywords as is**.  

    **🔍 Predicted Words**: {predicted_words}
    **🔍 High Keywords**: {high_keywords}

    **📝 Output Format:**  
    - **Return a comma-separated list of refined, culturally adapted keywords.**  
    - Example Output:  
      "مطر, برد, الجامعة, شاهي, شتاء, نار, فطور, كرك, بطانيات"
    """

    prompt = ChatPromptTemplate.from_template(template)
    chain = prompt | model

    response = chain.invoke({
        "predicted_words": ", ".join(predicted_words)
        ,"high_keywords": ", ".join(high_keywords)
        }
        ).content

    return response.split(", ")  # Ensure structured output

# Function to update Google Sheets
def update_google_sheet(sheet_name, keywords, column="A"):
    try:
        scope = ["https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        client = gspread.authorize(creds)

        sheet = client.open(sheet_name).worksheet("Keywords")

        # Ensure keywords are formatted correctly
        if not isinstance(keywords, list):
            keywords_list = [keyword.strip() for keyword in keywords.split(',') if keyword.strip()]
            update_data = [[kw] for kw in keywords_list]
        else:
            update_data = [[kw] if isinstance(kw, str) else kw for kw in keywords]  # Ensure each entry is a list

        if update_data:  # Ensure we have data to update
            range_str = f"{column}2:{column}{len(update_data) + 1}"
            sheet.update(range_str, update_data)

        # Add timestamp in column C
        time_now = time.strftime("%Y-%m-%d %H:%M:%S")
        cell_time_formatted = f"✅Last Updated: {time_now}"
        sheet.update_cell(2, 3, cell_time_formatted)

        print(f"Google Sheet updated successfully in column {column}.")

    except Exception as e:
        print(f"Error updating Google Sheets: {e}")


# **Main Execution**
if __name__ == "__main__":
    while True:
        start_time = time.time()

        saudi_trends = scrape_saudi_trends()
        historical_keywords = get_historical_keywords("Target", days=1)
        print("Historical Keywords high:", historical_keywords["High"])

        cleaned_topics = clean_trending_topics(saudi_trends, historical_keywords)
        weather_description = get_weather_data()["description"] if get_weather_data() else "الطقس معتدل"

        predicted_words = predict_frequent_words(cleaned_topics, weather_description, historical_keywords)
        localized_keywords = localize_keywords_ksa(predicted_words,historical_keywords["High"])

        # Remove duplicates
        localized_keywords = list(set(localized_keywords))

        # Update Google Sheet
        update_google_sheet("Trending Keywords Saudi Based on Input", localized_keywords)
        # update_google_sheet("Trending Keywords Saudi", cleaned_topics, column="B")
        # update_google_sheet("Trending Keywords Saudi", saudi_trends, column="D")

        print(f"\n✅ Time taken: {(time.time() - start_time) / 60:.2f} minutes")
        print("⏳ Script will run again in 1 hour...\n")
        time.sleep(18000)
