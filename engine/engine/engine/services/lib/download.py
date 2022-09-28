import requests
from engine.services.log import logs


def test_url_for_download(
    url, url_download_insecure_ssl=True, timeout_time_limit=5, dict_header={}
):
    """Test if url is alive, previous to launch ssh curl in hypervisor
    to download media, domains..."""
    try:
        response = requests.head(
            url,
            allow_redirects=True,
            verify=url_download_insecure_ssl,
            timeout=timeout_time_limit,
            headers=dict_header,
        )
    except requests.exceptions.RequestException as e:
        logs.exception_id.debug("0046")
        return False, e

    if response.status_code != 200:
        error = "status code {}".format(response.status_code)
        return False, error

    content_type = response.headers.get("Content-Type", "")

    if content_type.find("application") < 0 and len(content_type) > 0:
        return False, "Content-Type of HTTP Header is not application"
    else:
        return True, ""


def test_url_google_drive(
    url, url_download_insecure_ssl=True, timeout_time_limit=5, dict_header={}
):
    """Test if url is alive, previously to ssh curl launch in hypervisor
    to download media, domains..."""
    try:
        response = requests.get(
            url,
            allow_redirects=True,
            verify=url_download_insecure_ssl,
            timeout=timeout_time_limit,
            headers=dict_header,
        )
    except requests.exceptions.RequestException as e:
        logs.exception_id.debug("0046")
        return False, e

    if response.status_code != 200:
        error = "status code {}".format(response.status_code)
        return False, error

    if response.headers.get("X-Frame-Options") == "DENY":
        error = "DENY not public url"
        return False, error

    content_type = response.headers.get("Content-Type", "")
    if content_type.find("text/html") < 0:
        return False, "Content-Type of HTTP Header is not text/html"

    html = response.text
    confirm = html[html.find("confirm") : html.find("&amp", html.find("confirm"))]
    if len(confirm) > 0:
        return confirm, ""
    else:
        return False, "Error parsing html from google drive"
