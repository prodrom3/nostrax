import argparse
import requests
from bs4 import BeautifulSoup

def extract_urls(url, silent=False):
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        urls = [link.get('href') for link in soup.find_all('a')]
        if not silent:
            for url in urls:
                print(url)
        return urls
    except requests.RequestException as e:
        if not silent:
            print(f"Error fetching page: {e}")
        return []

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Extract URLs and paths from a webpage securely.')
    parser.add_argument('-t', '--target', type=str, required=True, help='Specify the target URL')
    parser.add_argument('-s', '--silent', action='store_true', help='Run in silent mode')
    args = parser.parse_args()

    extract_urls(args.target, args.silent)
