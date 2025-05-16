import requests
from bs4 import BeautifulSoup
import json
from typing import List, Dict
import time
import random
from pathlib import Path
import logging
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential
import cloudscraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GrouponScraper:
    def __init__(self):
        # Initialize cloudscraper to bypass cloudflare
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }
        )
        
        # Initialize fake user agent
        self.ua = UserAgent()
        
        # List of common referrers
        self.referrers = [
            'https://www.google.com/',
            'https://www.bing.com/',
            'https://www.facebook.com/',
            'https://t.co/',
            'https://www.instagram.com/'
        ]

    def get_random_headers(self):
        """Generate random headers for each request."""
        return {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'Referer': random.choice(self.referrers)
        }

    def random_delay(self):
        """Add random delay between requests."""
        # More natural random delay pattern
        delay = random.uniform(3, 7) + random.uniform(0, 2)
        time.sleep(delay)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def make_request(self, url: str) -> str:
        """Make a request with retry logic and rotating headers."""
        headers = self.get_random_headers()
        
        # Add random query parameters to avoid caching
        params = {
            '_': str(int(time.time() * 1000)),
            'nc': random.randint(1000000, 9999999)
        }
        
        response = self.scraper.get(
            url,
            headers=headers,
            params=params,
            timeout=30
        )
        response.raise_for_status()
        return response.text

    def get_deal_links(self, search_term: str, zip_code: str) -> List[str]:
        """Get all deal links from search results."""
        try:
            base_url = "https://www.groupon.com/search"
            url = f"{base_url}?query={search_term}&address={zip_code}"
            logger.info(f"Searching: {url}")
            
            html_content = self.make_request(url)
            soup = BeautifulSoup(html_content, 'html.parser')
            links = []
            
            # Find all deal links with multiple possible selectors
            link_selectors = [
                "a[href*='/deals/']",
                "figure.card-ui a",
                "div.deal-card a",
                "[data-bhw='DealCard'] a"
            ]
            
            for selector in link_selectors:
                for link in soup.select(selector):
                    href = link.get('href', '')
                    if '/deals/' in href and not href.endswith('/deals/'):
                        full_url = f"https://www.groupon.com{href}" if href.startswith('/') else href
                        if full_url not in links:
                            links.append(full_url)
                            logger.debug(f"Found deal link: {full_url}")
            
            logger.info(f"Found {len(links)} deal links")
            return links
            
        except Exception as e:
            logger.error(f"Error getting deal links: {e}")
            return []

    def get_deal_details(self, url: str) -> Dict:
        """Get detailed information from a deal page."""
        try:
            logger.info(f"Scraping deal: {url}")
            
            html_content = self.make_request(url)
            soup = BeautifulSoup(html_content, 'html.parser')
            
            deal_data = {
                "url": url,
                "timestamp": time.time()
            }
            
            # Multiple selector patterns for each field
            selectors = {
                "title": [
                    ["h1.deal-title", "h2.deal-title"],
                    ["h1[data-bhw='DealTitle']", "h2[data-bhw='DealTitle']"],
                    ["[class*='deal-title']", "[class*='dealTitle']"]
                ],
                "merchant": [
                    "[class*='merchant-name']",
                    "[data-bhw='MerchantName']",
                    "[class*='merchantName']"
                ]
            }
            
            # Try different selectors for each field
            for field, selector_list in selectors.items():
                for selector in selector_list:
                    if isinstance(selector, list):
                        element = soup.find(selector)
                    else:
                        element = soup.select_one(selector)
                    
                    if element:
                        deal_data[field] = element.get_text(strip=True)
                        break
            
            # Get price options with multiple selector patterns
            options = []
            option_selectors = [
                "[class*='deal-option']",
                "[data-bhw='DealOption']",
                "[class*='dealOption']"
            ]
            
            for selector in option_selectors:
                for option in soup.select(selector):
                    option_data = {}
                    
                    # Try multiple price selectors
                    price_selectors = {
                        "original_price": [
                            "[class*='original-price']",
                            "[class*='originalPrice']",
                            "[data-bhw='OriginalPrice']"
                        ],
                        "current_price": [
                            "[class*='current-price']",
                            "[class*='currentPrice']",
                            "[data-bhw='CurrentPrice']"
                        ]
                    }
                    
                    for price_field, price_selector_list in price_selectors.items():
                        for price_selector in price_selector_list:
                            price_element = option.select_one(price_selector)
                            if price_element:
                                option_data[price_field] = price_element.get_text(strip=True)
                                break
                    
                    if option_data:
                        options.append(option_data)
                
                if options:
                    break
            
            if options:
                deal_data["options"] = options
            
            return deal_data
            
        except Exception as e:
            logger.error(f"Error getting deal details from {url}: {e}")
            return {"url": url, "error": str(e)}

    def scrape_deals(self, search_term: str, zip_code: str) -> List[Dict]:
        """Get all deals with detailed information."""
        deals = []
        links = self.get_deal_links(search_term, zip_code)
        
        for link in links:
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
        
        scraper = GrouponScraper()
        all_deals = []
        
        # Scrape deals for each zip code
        for zip_code in zip_codes:
            logger.info(f"Processing ZIP code: {zip_code}")
            deals = scraper.scrape_deals(search_term, zip_code)
            all_deals.extend(deals)
            # Add longer delay between zip codes
            time.sleep(random.uniform(10, 15))
        
        # Save results
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / "deals.json"
        
        with open(output_file, "w", encoding='utf-8') as f:
            json.dump(all_deals, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Found total {len(all_deals)} deals. Saved to {output_file}")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        raise

if __name__ == "__main__":
    main() 