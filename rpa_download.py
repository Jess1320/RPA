import os
import threading
from datetime import date, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv


load_dotenv('.env')

LOGIN_URL = os.getenv('LOGIN_URL')
USERNAME = os.getenv('USERNAME')
PASSWORD = os.getenv('PASSWORD')
CENTERS = os.getenv('CENTERS', '').split(',')
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads')

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def create_driver(download_dir: str):
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    prefs = {
        'download.default_directory': os.path.abspath(download_dir),
        'download.prompt_for_download': False,
        'download.directory_upgrade': True,
        'safebrowsing.enabled': False,
    }
    options.add_experimental_option('prefs', prefs)
    return webdriver.Chrome(options=options)


def login_and_download(center: str):
    driver = create_driver(DOWNLOAD_DIR)
    wait = WebDriverWait(driver, 20)
    try:
        driver.get(LOGIN_URL)

        # --- Login form ---
        wait.until(EC.visibility_of_element_located((By.ID, 'usuario'))).send_keys(USERNAME)
        driver.find_element(By.ID, 'password').send_keys(PASSWORD)
        driver.find_element(By.ID, 'submit').click()

        # --- Select center ---
        wait.until(EC.visibility_of_element_located((By.ID, 'centro_select')))
        center_select = driver.find_element(By.ID, 'centro_select')
        for option in center_select.find_elements(By.TAG_NAME, 'option'):
            if center.lower() in option.text.lower():
                option.click()
                break
        driver.find_element(By.ID, 'ingresar').click()

        # --- Navigate to menu ---
        wait.until(EC.element_to_be_clickable((By.ID, 'menu_admision'))).click()
        wait.until(EC.element_to_be_clickable((By.ID, 'submenu_pacientes_citados'))).click()

        # --- Fill form fields ---
        today = date.today()
        first_day = today.replace(day=1)
        last_day = today - timedelta(days=1)
        wait.until(EC.visibility_of_element_located((By.ID, 'fechaInicio'))).clear()
        driver.find_element(By.ID, 'fechaInicio').send_keys(first_day.strftime('%d/%m/%Y'))
        driver.find_element(By.ID, 'fechaFin').clear()
        driver.find_element(By.ID, 'fechaFin').send_keys(last_day.strftime('%d/%m/%Y'))
        tipo_archivo = driver.find_element(By.ID, 'tipoArchivo')
        for option in tipo_archivo.find_elements(By.TAG_NAME, 'option'):
            if 'TXT' in option.text:
                option.click()
                break

        driver.find_element(By.ID, 'imprimir').click()
        # Wait for download to start (adjust condition as needed)
        WebDriverWait(driver, 60).until(lambda d: any(fname.endswith('.txt') for fname in os.listdir(DOWNLOAD_DIR)))
    finally:
        driver.quit()


def main():
    threads = []
    for center in filter(None, CENTERS):
        t = threading.Thread(target=login_and_download, args=(center.strip(),))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()


if __name__ == '__main__':
    main()
