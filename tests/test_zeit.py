import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

from zeit_on_tolino import zeit
from zeit_on_tolino.env_vars import EnvVars, MissingEnvironmentVariable

ZEIT_E_PAPER_URL = "https://epaper.zeit.de/abo/diezeit"


def test__login(webdriver) -> None:
    zeit._login(webdriver)
    assert webdriver.current_url == ZEIT_E_PAPER_URL


def test_download_e_paper(webdriver, tmp_path) -> None:
    e_paper_path = zeit.download_e_paper(webdriver)
    assert isinstance(e_paper_path, Path)
    assert e_paper_path.is_file()
    assert e_paper_path.suffix == ".epub"


def test_no_credentials(webdriver) -> None:
    # delete existing env vars
    if EnvVars.ZEIT_PREMIUM_USER in os.environ and EnvVars.ZEIT_PREMIUM_PASSWORD in os.environ:
        del os.environ[EnvVars.ZEIT_PREMIUM_USER]
        del os.environ[EnvVars.ZEIT_PREMIUM_PASSWORD]

    # verify meaningful error is raised
    with pytest.raises(
        MissingEnvironmentVariable,
        match="Ensure to export your ZEIT username and password as environment variables",
    ):
        zeit.download_e_paper(webdriver)


def test_wrong_credentials(webdriver) -> None:
    # set wrong credentials
    os.environ[EnvVars.ZEIT_PREMIUM_USER] = "foo"
    os.environ[EnvVars.ZEIT_PREMIUM_PASSWORD] = "baa"

    # verify error is raised
    with pytest.raises(RuntimeError, match="Failed to login, check your login credentials."):
        zeit.download_e_paper(webdriver)


def test__wait_for_any_element__finds_first_match() -> None:
    element = object()
    webdriver = MagicMock()
    webdriver.find_elements.side_effect = [
        [],
        [element],
    ]

    result = zeit._wait_for_any_element(
        webdriver,
        ((By.ID, "missing"), (By.ID, "present")),
        timeout=0.1,
    )

    assert result is element


def test__wait_for_any_element__times_out() -> None:
    webdriver = MagicMock()
    webdriver.find_elements.return_value = []

    with pytest.raises(TimeoutException):
        zeit._wait_for_any_element(webdriver, ((By.ID, "missing"),), timeout=0.1)


def test__wait_for_post_login_page__checks_multiple_selectors(monkeypatch) -> None:
    webdriver = MagicMock()
    captured = {}

    def _fake_wait_for_any_element(driver, selectors, timeout=zeit.Delay.medium):
        captured["driver"] = driver
        captured["selectors"] = selectors
        captured["timeout"] = timeout
        return object()

    monkeypatch.setattr(zeit, "_wait_for_any_element", _fake_wait_for_any_element)

    zeit._wait_for_post_login_page(webdriver)

    assert captured["driver"] is webdriver
    assert captured["timeout"] == zeit.Delay.medium
    assert captured["selectors"] == (
        (By.CLASS_NAME, "page-section-header"),
        (By.XPATH, f'//a[normalize-space()="{zeit.BUTTON_TEXT_TO_RECENT_EDITION}"]'),
        (By.XPATH, f'//a[normalize-space()="{zeit.BUTTON_TEXT_DOWNLOAD_EPUB}"]'),
    )
