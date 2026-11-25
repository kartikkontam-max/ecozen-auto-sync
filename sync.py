import os
import glob
import traceback
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def sync_data():
    user_id = os.environ.get("USER_ID")
    user_password = os.environ.get("USER_PASSWORD")
    web_app_url = os.environ.get("APPS_SCRIPT_URL")

    if not user_id or not user_password or not web_app_url:
        raise ValueError("Error: USER_ID, USER_PASSWORD, or APPS_SCRIPT_URL secret is missing!")

    download_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(download_dir, exist_ok=True)
    
    options = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "directory_upgrade": True
    }
    options.add_experimental_option("prefs", prefs)
    
    # Headless mode is required for GitHub Actions
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    try:
        # 1. Open Login Page
        driver.get("https://ecozen.ai/login.php")
        wait = WebDriverWait(driver, 30)
        
        # Enter Username
        username_box = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='text' or @type='email' or contains(@placeholder, 'User')]")))
        username_box.clear()
        username_box.send_keys(user_id)
        
        next_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Next']")))
        next_btn.click()
        time.sleep(5)
        
        # Enter Password
        password_box = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='password']")))
        password_box.clear()
        password_box.send_keys(user_password)
        
        login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Log In']")))
        login_btn.click()
        time.sleep(8)  # Wait properly for the dashboard to load after login
        
        # Capture screenshot to verify what the cloud browser sees after login
        try:
            driver.save_screenshot("debug_screen.png")
            print("Debug screenshot saved successfully.")
        except Exception as sc_err:
            print("Warning while taking screenshot:", sc_err)
        
        # 2. Click on Retail Care
        retail_care = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Retail Care')]")))
        driver.execute_script("arguments[0].click();", retail_care)
        time.sleep(3)
        
        # 3. Click on Tickets
        tickets_link = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Tickets')]")))
        driver.execute_script("arguments[0].click();", tickets_link)
        time.sleep(5)
        
        # 4. Click the 'Select all' button next to Status
        try:
            select_all_status = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Status')]/following::button[normalize-space()='Select all'][1] | //*[contains(text(), 'Select all')]")))
            driver.execute_script("arguments[0].click();", select_all_status)
            time.sleep(3)
        except Exception as e:
            print("Warning while clicking Status 'Select all':", e)
            
        # 5. Automatically set an exact 1-month date range
        end_date = datetime.today().strftime('%d-%m-%Y')
        start_date = (datetime.today() - relativedelta(months=1)).strftime('%d-%m-%Y')
        print(f"Setting automatic date range: {start_date} to {end_date}")
        
        try:
            date_inputs = driver.find_elements(By.XPATH, "//input[@type='text']")
            valid_date_inputs = []
            for inp in date_inputs:
                val = inp.get_attribute("value")
                if val and ("-" in val or "/" in val) and len(val) >= 8:
                    valid_date_inputs.append(inp)
            
            if len(valid_date_inputs) >= 2:
                driver.execute_script("""
                    arguments[0].removeAttribute('readonly');
                    arguments[0].value = arguments[1];
                    arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                    arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));
                """, valid_date_inputs[0], start_date)
                
                driver.execute_script("""
                    arguments[0].removeAttribute('readonly');
                    arguments[0].value = arguments[1];
                    arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                    arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));
                """, valid_date_inputs[1], end_date)
                
            time.sleep(3)
        except Exception as e:
            print("Error while setting date range:", e)
        
        # 6. Click on the 'Download CSV' button
        download_csv_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Download CSV')]")))
        driver.execute_script("arguments[0].scrollIntoView(true);", download_csv_btn)
        driver.execute_script("arguments[0].click();", download_csv_btn)
        print("Downloading CSV file in the background...")
        
        # 7. Wait for the file to finish downloading
        file_found = False
        timeout_counter = 0
        latest_file = ""
        while not file_found and timeout_counter < 40:
            time.sleep(3)
            list_of_files = glob.glob(os.path.join(download_dir, "*.csv"))
            if list_of_files:
                latest_file = max(list_of_files, key=os.path.getctime)
                if time.time() - os.path.getctime(latest_file) < 120:
                    file_found = True
                    break
            timeout_counter += 1
            
        if file_found:
            print(f"File found: {latest_file}")
            df = pd.read_csv(latest_file)
            df = df.fillna("")
            
            print(f"Total rows found in CSV file: {len(df)}")
            records = df.to_dict(orient="records")
            
            payload = {
                "sheet": "Portal_Sync Data",
                "data": records
            }

            response = requests.post(web_app_url, json=payload)
            print("Server Response:", response.text)
            
            try:
                os.remove(latest_file)
                print("Downloaded CSV file deleted from local storage.")
            except Exception as del_err:
                print("Warning while deleting file:", del_err)
        else:
            raise FileNotFoundError("CSV file not found in the Downloads folder.")
            
    except Exception as e:
        print("Detailed error occurred:")
        traceback.print_exc()
        raise
    finally:
        driver.quit()

if __name__ == "__main__":
    sync_data()
