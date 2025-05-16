import requests
from bs4 import BeautifulSoup
import json
from typing import List, Dict
import time
import random
from pathlib import Path
import logging
import sys
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential
import cloudscraper
import re

# Configure logging to output to both file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("scraper.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class GrouponScraper:
    def __init__(self):
        try:
            print("Initializing scraper...")
            # Initialize cloudscraper to bypass cloudflare
            self.scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'mobile': False
                },
                debug=True
            )
            
            # Initialize fake user agent
            self.ua = UserAgent()
            print("Scraper initialized successfully")
            
        except Exception as e:
            print(f"Error initializing scraper: {str(e)}")
            raise

    def get_random_headers(self):
        """Generate random headers for each request."""
        headers = {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        }
        print(f"\nUsing headers:\n{json.dumps(headers, indent=2)}")
        return headers

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def make_request(self, url: str) -> str:
        """Make a request with retry logic and rotating headers."""
        try:
            print(f"\nMaking request to: {url}")
            headers = self.get_random_headers()
            
            response = self.scraper.get(
                url,
                headers=headers,
                timeout=30
            )
            
            # Print response details
            print(f"\nResponse Status: {response.status_code}")
            print("\nResponse Headers:")
            print(json.dumps(dict(response.headers), indent=2))
            
            content = response.text
            print(f"\nResponse length: {len(content)} characters")
            
            # store the response in a file
            with open("response.html", "w", encoding='utf-8') as f:
                f.write(content)
            
            # Check for common blocking patterns
            if "captcha" in content.lower():
                print("WARNING: Captcha detected in response!")
            if "cloudflare" in content.lower():
                print("WARNING: Cloudflare challenge detected!")
            if "access denied" in content.lower():
                print("WARNING: Access denied message detected!")
            if "robot" in content.lower() or "bot" in content.lower():
                print("WARNING: Bot detection message found!")
            
            # Save the response for debugging
            debug_dir = Path("debug")
            debug_dir.mkdir(exist_ok=True)
            debug_file = debug_dir / f"response_{int(time.time())}.html"
            with open(debug_file, "w", encoding='utf-8') as f:
                f.write(content)
            print(f"\nFull response saved to: {debug_file}")
            
            return content
            
        except Exception as e:
            print(f"Error making request: {str(e)}")
            print("Full error details:")
            import traceback
            traceback.print_exc()
            raise

    def get_deal_links(self, search_term: str, zip_code: str) -> List[str]:
        """Get all deal links from search results."""
        try:
            base_url = "https://www.groupon.com/search"
            url = f"{base_url}?query={search_term}&address={zip_code}"
            print(f"\nSearching for deals at: {url}")
            
            html_content = self.make_request(url)
            print(f"\nParsing HTML content (length: {len(html_content)})")
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Print page title and basic info
            print(f"\nPage Title: {soup.title.string if soup.title else 'No title found'}")
            
            # Debug: Print all links
            print("\nAll links found in the page:")
            all_links = soup.find_all('a', href=True)
            print(f"Total links found: {len(all_links)}")
            for link in all_links:
                print(f"Link: {link['href']}")
            
            # Debug: Look for common elements
            print("\nCommon page elements:")
            print(f"<figure> elements: {len(soup.find_all('figure'))}")
            print(f"Elements with 'deal' in class: {len(soup.find_all(class_=re.compile('deal')))}")
            print(f"Elements with 'card' in class: {len(soup.find_all(class_=re.compile('card')))}")
            
            links = []
            link_selectors = [
                "a[href*='/deals/']",
                "figure.card-ui a",
                "div.deal-card a",
                "[data-bhw='DealCard'] a",
                "a[href*='groupon.com/deals']",
                ".deal a",
                ".card a"
            ]
            
            for selector in link_selectors:
                print(f"\nTrying selector: {selector}")
                found_elements = soup.select(selector)
                print(f"Found {len(found_elements)} elements")
                
                for link in found_elements:
                    href = link.get('href', '')
                    print(f"Processing href: {href}")
                    if '/deals/' in href and not href.endswith('/deals/'):
                        full_url = f"https://www.groupon.com{href}" if href.startswith('/') else href
                        if full_url not in links:
                            links.append(full_url)
                            print(f"Added deal link: {full_url}")
            
            print(f"\nTotal deal links found: {len(links)}")
            return links
            
        except Exception as e:
            print(f"Error getting deal links: {str(e)}")
            print("Full error details:")
            import traceback
            traceback.print_exc()
            return []

    def scrape_deals(self, search_term: str, zip_code: str) -> List[Dict]:
        """Get all deals with detailed information."""
        try:
            print(f"\nScraping deals for search term '{search_term}' in ZIP code {zip_code}")
            deals = []
            
            # Get all deal links first
            links = self.get_deal_links(search_term, zip_code)
            print(f"Found {len(links)} links to process")
            
            # Process each link
            for link in links:
                try:
                    print(f"\nProcessing deal: {link}")
                    html_content = self.make_request(link)
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    deal_data = {
                        "url": link,
                        "zip_code": zip_code,
                        "search_term": search_term,
                        "timestamp": time.time()
                    }
                    
                    # Get deal title
                    title = soup.find(["h1", "h2"], class_=lambda x: x and "deal-title" in x.lower())
                    if title:
                        deal_data["title"] = title.get_text(strip=True)
                        print(f"Found title: {deal_data['title']}")
                    
                    # Get merchant name
                    merchant = soup.find(class_=lambda x: x and "merchant-name" in x.lower())
                    if merchant:
                        deal_data["merchant"] = merchant.get_text(strip=True)
                        print(f"Found merchant: {deal_data['merchant']}")
                    
                    # Get price information
                    price_options = []
                    for option in soup.find_all(class_=lambda x: x and "deal-option" in x.lower()):
                        option_data = {}
                        
                        # Get original price
                        original_price = option.find(class_=lambda x: x and "original-price" in x.lower())
                        if original_price:
                            option_data["original_price"] = original_price.get_text(strip=True)
                        
                        # Get current price
                        current_price = option.find(class_=lambda x: x and "current-price" in x.lower())
                        if current_price:
                            option_data["current_price"] = current_price.get_text(strip=True)
                        
                        if option_data:
                            price_options.append(option_data)
                            print(f"Found price option: {option_data}")
                    
                    if price_options:
                        deal_data["price_options"] = price_options
                    
                    # Get deal highlights
                    highlights = soup.find(class_=lambda x: x and "highlights" in x.lower())
                    if highlights:
                        deal_data["highlights"] = [
                            item.get_text(strip=True)
                            for item in highlights.find_all("li")
                        ]
                        print(f"Found {len(deal_data['highlights'])} highlights")
                    
                    # Get fine print
                    fine_print = soup.find(class_=lambda x: x and "fine-print" in x.lower())
                    if fine_print:
                        deal_data["fine_print"] = fine_print.get_text(strip=True)
                        print("Found fine print information")
                    
                    deals.append(deal_data)
                    print(f"Successfully processed deal: {link}")
                    
                    # Add a delay between processing deals
                    delay = random.uniform(2, 5)
                    print(f"Waiting {delay:.2f} seconds before next deal...")
                    time.sleep(delay)
                    
                except Exception as e:
                    print(f"Error processing deal {link}: {str(e)}")
                    print("Full error details:")
                    import traceback
                    traceback.print_exc()
                    continue
            
            print(f"\nSuccessfully processed {len(deals)} deals for ZIP code {zip_code}")
            return deals
            
        except Exception as e:
            print(f"Error in scrape_deals: {str(e)}")
            print("Full error details:")
            import traceback
            traceback.print_exc()
            return []

def main():
    """Main entry point."""
    try:
        print("\n=== Starting Groupon Scraper ===\n")
        
        # Read zip codes
        with open("zipcodes.txt", "r") as f:
            zip_codes = [line.strip() for line in f if line.strip()]
        
        if not zip_codes:
            raise ValueError("No ZIP codes found in zipcodes.txt")
        
        print(f"Loaded {len(zip_codes)} ZIP codes")
        
        search_term = "Hydrafacial"
        print(f"\nSearch term: {search_term}")
        
        scraper = GrouponScraper()
        all_deals = []
        
        # Scrape deals for each zip code
        for zip_code in zip_codes:
            print(f"\nProcessing ZIP code: {zip_code}")
            deals = scraper.scrape_deals(search_term, zip_code)
            all_deals.extend(deals)
            time.sleep(random.uniform(10, 15))
        
        # Save results
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / "deals.json"
        
        with open(output_file, "w", encoding='utf-8') as f:
            json.dump(all_deals, f, indent=2, ensure_ascii=False)
        
        print(f"\nFound total {len(all_deals)} deals")
        print(f"Results saved to: {output_file}")
        
    except Exception as e:
        print(f"\nError in main: {str(e)}")
        print("Full error details:")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 