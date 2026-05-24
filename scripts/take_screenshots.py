"""Auto-login and take screenshots of key pages for defense PPT."""
import time
import os
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE_URL = "http://localhost:5000"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ppt", "screenshots")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def create_driver():
    opts = EdgeOptions()
    opts.use_chromium = True
    opts.add_argument("--window-size=1280,800")
    # NOT headless so we can see what's happening
    driver = webdriver.Edge(options=opts)
    driver.implicitly_wait(5)
    return driver


def login(driver, username="admin", password="admin123456"):
    driver.get(f"{BASE_URL}/login")
    time.sleep(1)
    # Find and fill login form
    username_field = driver.find_element(By.NAME, "account")
    password_field = driver.find_element(By.NAME, "password")
    username_field.clear()
    username_field.send_keys(username)
    password_field.clear()
    password_field.send_keys(password)
    # Click login button
    login_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
    login_btn.click()
    time.sleep(2)
    # Handle forced password change if redirected
    if "/force-change" in driver.current_url:
        print("  [!] Forced password change page - setting new password")
        new_pw = driver.find_element(By.NAME, "new_password")
        confirm_pw = driver.find_element(By.NAME, "confirm_password")
        new_pw.clear()
        new_pw.send_keys("Test123456!")
        confirm_pw.clear()
        confirm_pw.send_keys("Test123456!")
        submit = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        submit.click()
        time.sleep(2)
    print(f"  Logged in. Current URL: {driver.current_url}")


def screenshot(driver, name, url=None, wait_seconds=2):
    if url:
        driver.get(url)
        time.sleep(wait_seconds)
    path = os.path.join(OUTPUT_DIR, f"{name}.png")
    driver.save_screenshot(path)
    print(f"  Saved: {path}")
    return path


def main():
    driver = create_driver()
    try:
        # 1. Login page
        print("[1] Login page")
        screenshot(driver, "01_login", f"{BASE_URL}/login")

        # 2. Login
        print("[2] Logging in...")
        login(driver)

        # 3. Dashboard
        print("[3] Dashboard")
        screenshot(driver, "02_dashboard", f"{BASE_URL}/dashboard")

        # 4. Monitor page
        print("[4] Monitor page")
        screenshot(driver, "03_monitor", f"{BASE_URL}/monitor", wait_seconds=3)

        # 5. Analysis view (upload page)
        print("[5] Analysis view")
        screenshot(driver, "04_analysis_view", f"{BASE_URL}/analysis-view")

        # 6. Rules config
        print("[6] Rules config")
        screenshot(driver, "05_rules", f"{BASE_URL}/admin/rules", wait_seconds=2)

        # 7. Evaluation page
        print("[7] Evaluation page")
        screenshot(driver, "06_evaluation", f"{BASE_URL}/evaluation", wait_seconds=2)

        print("\nDone! Screenshots saved to:", OUTPUT_DIR)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
