import json
import logging
import time
from pathlib import Path
from typing import List, Dict
import random
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from tqdm import tqdm
import os
import platform
import subprocess
from selenium.common.exceptions import TimeoutException, WebDriverException

# Configure logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def is_wsl() -> bool:
    """Check if running in WSL."""
    return platform.system() == 'Linux' and 'microsoft' in platform.uname().release.lower()

def get_windows_chrome_path() -> str:
    """Get the path to Chrome in Windows from WSL."""
    possible_paths = [
        '/mnt/c/Program Files/Google/Chrome/Application/chrome.exe',
        '/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    raise FileNotFoundError("Could not find Chrome installation in Windows. Please install Chrome or provide correct path.")

class GrouponScraper:
    """Scraper for Groupon deals with detailed information."""
    
    def __init__(self):
        logger.info("Initializing GrouponScraper...")
        
        # Configure Chrome options
        options = uc.ChromeOptions()
        
        # Basic options
        options.add_argument('--start-maximized')
        options.add_argument('--disable-blink-features=AutomationControlled')
        
        # WSL specific options
        if is_wsl():
            logger.info("Running in WSL environment, configuring accordingly...")
            chrome_path = get_windows_chrome_path()
            options.binary_location = chrome_path
            logger.info(f"Using Chrome binary at: {chrome_path}")
            
            # WSL specific arguments
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-software-rasterizer')
            options.add_argument('--disable-features=VizDisplayCompositor')
            options.add_argument('--disable-extensions')
            options.add_argument('--remote-debugging-port=9222')
            options.add_argument('--window-size=1920,1080')
            
            # Additional preferences
            options.add_experimental_option('excludeSwitches', ['enable-automation'])
            options.add_experimental_option('useAutomationExtension', False)
            
            # Try to kill any existing Chrome processes
            try:
                subprocess.run(['pkill', 'chrome'], stderr=subprocess.DEVNULL)
                logger.info("Killed existing Chrome processes")
            except Exception as e:
                logger.warning(f"Failed to kill existing Chrome processes: {e}")
        
        # Initialize undetected-chromedriver
        try:
            logger.info("Creating Chrome driver...")
            self.driver = uc.Chrome(
                options=options,
                driver_executable_path=None,  # Let it auto-download
                browser_executable_path=options.binary_location if is_wsl() else None,
                headless=False,  # Headless mode often fails in WSL
                use_subprocess=True,
                version_main=None  # Auto-detect version
            )
            self.wait = WebDriverWait(self.driver, 20)
            logger.info("Chrome driver created successfully")
            
            # Test the connection
            self.driver.get('https://www.groupon.com')
            logger.info("Successfully loaded Groupon homepage")
            time.sleep(5)  # Give it time to fully load
            
        except Exception as e:
            logger.error(f"Failed to create Chrome driver: {e}")
            raise
    
    def __del__(self):
        """Clean up browser instance."""
        try:
            if hasattr(self, 'driver'):
                logger.info("Closing Chrome driver...")
                self.driver.quit()
                logger.info("Chrome driver closed successfully")
        except Exception as e:
            logger.error(f"Error closing Chrome driver: {e}")
    
    def random_delay(self):
        """Add random delay between actions."""
        delay = random.uniform(2, 5)
        logger.debug(f"Waiting for {delay:.2f} seconds...")
        time.sleep(delay)
    
    def get_deal_links(self, search_term: str, zip_code: str) -> List[str]:
        """Get all deal links from search results."""
        try:
            # Build search URL
            url = f"https://www.groupon.com/search?query={search_term}&address={zip_code}"
            logger.info(f"Accessing search URL: {url}")
            
            # Load the page
            self.driver.get(url)
            logger.info("Page loaded, waiting for content...")
            self.random_delay()
            
            try:
                # Wait for deal cards to load
                logger.info("Waiting for deal cards to appear...")
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "figure.card-ui, div.deal-card")))
                logger.info("Deal cards found")
            except TimeoutException:
                logger.warning("Timeout waiting for deal cards, checking page source anyway...")
            
            # Get page source and parse with BeautifulSoup
            page_source = self.driver.page_source
            logger.info(f"Page source length: {len(page_source)} characters")
            soup = BeautifulSoup(page_source, 'html.parser')
            links = []
            
            # Find all deal links
            for link in soup.find_all("a", href=True):
                href = link.get('href', '')
                if '/deals/' in href and not href.endswith('/deals/'):
                    full_url = f"https://www.groupon.com{href}" if href.startswith('/') else href
                    if full_url not in links:
                        links.append(full_url)
                        logger.debug(f"Found deal link: {full_url}")
            
            logger.info(f"Found {len(links)} deal links")
            return links
            
        except WebDriverException as e:
            logger.error(f"WebDriver error getting deal links: {e}")
            return []
        except Exception as e:
            logger.error(f"Error getting deal links: {e}")
            return []
    
    def get_deal_details(self, url: str) -> Dict:
        """Get detailed information from a deal page."""
        try:
            logger.info(f"Scraping deal: {url}")
            
            # Load the deal page
            self.driver.get(url)
            logger.info("Deal page loaded, waiting for content...")
            self.random_delay()
            
            try:
                # Wait for main content to load
                logger.info("Waiting for deal title to appear...")
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1, h2.deal-title")))
                logger.info("Deal title found")
            except TimeoutException:
                logger.warning("Timeout waiting for deal title, checking page source anyway...")
            
            # Parse with BeautifulSoup
            page_source = self.driver.page_source
            logger.info(f"Deal page source length: {len(page_source)} characters")
            soup = BeautifulSoup(page_source, 'html.parser')
            deal_data = {
                "url": url,
                "timestamp": time.time()
            }
            
            # Get deal title
            title = soup.find(["h1", "h2"], class_=lambda x: x and "deal-title" in x.lower())
            if title:
                deal_data["title"] = title.get_text(strip=True)
                logger.info(f"Found deal title: {deal_data['title']}")
            
            # Get merchant info
            merchant = soup.find(class_=lambda x: x and "merchant-name" in x.lower())
            if merchant:
                deal_data["merchant"] = merchant.get_text(strip=True)
            
            # Get location/address
            location = soup.find(class_=lambda x: x and "merchant-location" in x.lower())
            if location:
                deal_data["location"] = location.get_text(strip=True)
            
            # Get price options
            options = []
            for option in soup.find_all(class_=lambda x: x and "deal-option" in x.lower()):
                option_data = {}
                
                # Option title
                option_title = option.find(class_=lambda x: x and "option-title" in x.lower())
                if option_title:
                    option_data["title"] = option_title.get_text(strip=True)
                
                # Prices
                original = option.find(class_=lambda x: x and "original-price" in x.lower())
                if original:
                    option_data["original_price"] = original.get_text(strip=True)
                
                current = option.find(class_=lambda x: x and "current-price" in x.lower())
                if current:
                    option_data["current_price"] = current.get_text(strip=True)
                
                discount = option.find(class_=lambda x: x and "discount" in x.lower())
                if discount:
                    option_data["discount"] = discount.get_text(strip=True)
                
                # Number bought
                bought = option.find(class_=lambda x: x and "bought" in x.lower())
                if bought:
                    option_data["bought"] = bought.get_text(strip=True)
                
                if option_data:
                    options.append(option_data)
            
            if options:
                deal_data["options"] = options
            
            # Get fine print
            fine_print = soup.find(class_=lambda x: x and "fine-print" in x.lower())
            if fine_print:
                deal_data["fine_print"] = fine_print.get_text(strip=True)
            
            # Get highlights
            highlights = soup.find(class_=lambda x: x and "highlights" in x.lower())
            if highlights:
                deal_data["highlights"] = [
                    li.get_text(strip=True) 
                    for li in highlights.find_all("li")
                ]
            
            # Get description
            description = soup.find(class_=lambda x: x and "description" in x.lower())
            if description:
                deal_data["description"] = description.get_text(strip=True)
            
            return deal_data
            
        except WebDriverException as e:
            logger.error(f"WebDriver error getting deal details from {url}: {e}")
            return {"url": url, "error": str(e)}
        except Exception as e:
            logger.error(f"Error getting deal details from {url}: {e}")
            return {"url": url, "error": str(e)}
    
    def scrape_deals(self, search_term: str, zip_code: str) -> List[Dict]:
        """Get all deals with detailed information."""
        # Get all deal links first
        links = self.get_deal_links(search_term, zip_code)
        if not links:
            logger.warning("No deals found")
            return []
        
        # Get details for each deal
        deals = []
        for link in tqdm(links, desc="Scraping deals"):
            deal_data = self.get_deal_details(link)
            if deal_data:
                deal_data["zip_code"] = zip_code
                deal_data["search_term"] = search_term
                deals.append(deal_data)
            self.random_delay()
        
        return deals

def main():
    """Main entry point."""
    try:
        # Read zip codes
        with open("zipcodes.txt", "r") as f:
            zip_codes = [line.strip() for line in f if line.strip()]
        
        if not zip_codes:
            raise ValueError("No ZIP codes found in zipcodes.txt")
        
        search_term = "Hydrafacial"
        logger.info(f"Starting scraper with search term '{search_term}' and {len(zip_codes)} ZIP codes")
        
        try:
            scraper = GrouponScraper()
            all_deals = []
            
            # Scrape deals for each zip code
            logger.info(f"Starting scrape for '{search_term}' in {len(zip_codes)} ZIP codes")
            for zip_code in zip_codes:
                logger.info(f"Processing ZIP code: {zip_code}")
                deals = scraper.scrape_deals(search_term, zip_code)
                all_deals.extend(deals)
            
            # Save results
            output_file = log_dir / "deals.json"
            with open(output_file, "w", encoding='utf-8') as f:
                json.dump(all_deals, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Found total {len(all_deals)} deals. Saved to {output_file}")
            
        finally:
            # Clean up
            if 'scraper' in locals():
                del scraper
        
    except Exception as e:
        logger.error(f"Error: {e}")
        raise

if __name__ == "__main__":
    main() 