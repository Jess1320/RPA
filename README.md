# RPA Download Script

This repository contains a simple Python script that demonstrates how to use Selenium to log into an institutional platform and download daily reports for multiple centers.

## Setup

1. Install the dependencies:

```bash
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and edit the values with your credentials and configuration.

3. Ensure that `chromium-browser` and `chromedriver` are installed. On Ubuntu you can install them with:

```bash
sudo apt-get update
sudo apt-get install -y chromium-browser chromium-chromedriver
```

## Usage

Run the script:

```bash
python rpa_download.py
```

The script will open a browser in headless mode, log in to the platform and download a file for each center specified in the `CENTERS` variable.

## Notes

- The current selectors for elements on the website are placeholders. Update the XPath or CSS selectors in `rpa_download.py` to match the actual page structure.
- Downloads are saved in the folder specified by `DOWNLOAD_DIR`.
