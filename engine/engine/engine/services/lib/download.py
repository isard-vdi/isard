import requests


def test_url_for_download(url,url_download_insecure_ssl=True,
                          timeout_time_limit=5, dict_header={}):
    """Test if url is alive, previous to launch ssh curl in hypervisor
    to download media, domains..."""
    try:
        response = requests.head(url,
                                 allow_redirects=True,
                                 verify=url_download_insecure_ssl,
                                 timeout=timeout_time_limit,
                                 headers=dict_header)
    except requests.exceptions.RequestException as e:
        return False,e

    if response.status_code != 200:
        error = 'status code {}'.format(response.status_code)
        return False,error

    content_type = response.headers.get('Content-Type','')

    if content_type.find('application') < 0:
        return False, 'Content-Type of HTTP Header is not application'
    else:
        return True, ''
