import logging
import glob
import os
import time
from pathlib import Path
from typing import Tuple

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

from zeit_on_tolino.env_vars import EnvVars, MissingEnvironmentVariable
from zeit_on_tolino.web import Delay

ZEIT_LOGIN_URL = "https://epaper.zeit.de/abo/diezeit"
ZEIT_DATE_FORMAT = "%d.%m.%Y"

BUTTON_TEXT_TO_RECENT_EDITION = "ZUR AKTUELLEN AUSGABE"
BUTTON_TEXT_DOWNLOAD_EPUB = "EPUB FÜR E-READER LADEN"
BUTTON_TEXT_EPUB_DOWNLOAD_IS_PENDING = "EPUB FOLGT IN KÜRZE"

log = logging.getLogger(__name__)


def _wait_for_any_element(webdriver: WebDriver, selectors: Tuple[Tuple[str, str], ...], timeout: int = Delay.medium):
    def _find_any(driver: WebDriver):
        for by, value in selectors:
            elements = driver.find_elements(by, value)
            if elements:
                return elements[0]
        return False

    return WebDriverWait(webdriver, timeout).until(_find_any)


def _wait_for_post_login_page(webdriver: WebDriver) -> None:
    post_login_selectors = (
        (By.CLASS_NAME, "page-section-header"),
        (By.XPATH, f'//a[normalize-space()="{BUTTON_TEXT_TO_RECENT_EDITION}"]'),
        (By.XPATH, f'//a[normalize-space()="{BUTTON_TEXT_DOWNLOAD_EPUB}"]'),
    )
    _wait_for_any_element(webdriver, post_login_selectors)


def _get_credentials() -> Tuple[str, str]:
    try:
        username = os.environ[EnvVars.ZEIT_PREMIUM_USER]
        password = os.environ[EnvVars.ZEIT_PREMIUM_PASSWORD]
        return username, password
    except KeyError:
        raise MissingEnvironmentVariable(
            f"Ensure to export your ZEIT username and password as environment variables "
            f"'{EnvVars.ZEIT_PREMIUM_USER}' and '{EnvVars.ZEIT_PREMIUM_PASSWORD}'. For "
            "Github Actions, use repository secrets."
        )


def _login(webdriver: WebDriver) -> None:
    username, password = _get_credentials()
    webdriver.get(ZEIT_LOGIN_URL)

    username_selectors = (
        (By.ID, "login_email"),
        (By.CSS_SELECTOR, 'input[name="email"]'),
        (By.CSS_SELECTOR, 'input[type="email"]'),
    )
    password_selectors = (
        (By.ID, "login_pass"),
        (By.CSS_SELECTOR, 'input[name="password"]'),
        (By.CSS_SELECTOR, 'input[type="password"]'),
    )
    submit_button_selectors = (
        (By.CSS_SELECTOR, "button.submit-button.log"),
        (By.CSS_SELECTOR, 'button[type="submit"]'),
        (By.CSS_SELECTOR, 'input[type="submit"]'),
    )

    try:
        username_field = _wait_for_any_element(webdriver, username_selectors)
        username_field.send_keys(username)
        password_field = _wait_for_any_element(webdriver, password_selectors)
        password_field.send_keys(password)
        btn = _wait_for_any_element(webdriver, submit_button_selectors)
        btn.click()
    except TimeoutException as exc:
        raise RuntimeError("Failed to locate ZEIT login form elements. The ZEIT login page may have changed.") from exc
    time.sleep(Delay.small)

    if "anmelden" in webdriver.current_url:
        raise RuntimeError("Failed to login, check your login credentials.")

    try:
        _wait_for_post_login_page(webdriver)
    except TimeoutException as exc:
        raise RuntimeError("Failed to detect ZEIT post-login page. The ZEIT website may have changed.") from exc


def _get_latest_downloaded_file_path(download_dir: str) -> Path:
    download_dir_files = glob.glob(f"{download_dir}/*")
    latest_file = max(download_dir_files, key=os.path.getctime)
    return Path(latest_file)


def wait_for_downloads(path):
    time.sleep(Delay.small)
    start = time.time()
    while any([filename.endswith(".crdownload") for filename in os.listdir(path)]):
        now = time.time()
        if now > start + Delay.large:
            raise TimeoutError(f"Did not manage to download file within {Delay.large} seconds.")
        else:
            log.info(f"waiting for download to be finished...")
            time.sleep(2)


def download_e_paper(webdriver: WebDriver) -> str:
    _login(webdriver)

    time.sleep(Delay.small)
    for link in webdriver.find_elements(By.TAG_NAME, "a"):
        if link.text == BUTTON_TEXT_TO_RECENT_EDITION:
            link.click()
            break

    if BUTTON_TEXT_EPUB_DOWNLOAD_IS_PENDING in webdriver.page_source:
        raise RuntimeError("New ZEIT release is available, however, EPUB version is not. Retry again later.")

    time.sleep(Delay.small)
    for link in webdriver.find_elements(By.TAG_NAME, "a"):
        if link.text == BUTTON_TEXT_DOWNLOAD_EPUB:
            log.info("clicking download button now...")
            link.click()
            break

    wait_for_downloads(webdriver.download_dir_path)
    e_paper_path = _get_latest_downloaded_file_path(webdriver.download_dir_path)

    if not e_paper_path.is_file():
        raise RuntimeError("Could not download e paper, check your login credentials.")

    return e_paper_path
