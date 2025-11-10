"""Powershop API client."""
import re
import logging
from typing import Optional, Dict, Any

import aiohttp
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)

class PowershopAPIClient:
    """Client for interacting with Powershop API."""
    
    def __init__(self, username: str, password: str):
        """Initialize the API client."""
        self.username = username
        self.password = password
        self.session: Optional[aiohttp.ClientSession] = None
        self.customer_id: Optional[str] = None
        self.base_url = "https://secure.powershop.co.nz"
        self._last_auth_attempt = None
        self._auth_failures = 0
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            # Create session with proper timeout and connector settings
            timeout = aiohttp.ClientTimeout(total=30)
            connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
            self.session = aiohttp.ClientSession(
                timeout=timeout, 
                connector=connector,
                headers={
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            )
        return self.session
    
    async def close(self):
        """Close the session."""
        if self.session and not self.session.closed:
            await self.session.close()
        
    async def authenticate(self) -> bool:
        """Authenticate with Powershop."""
        import asyncio
        from datetime import datetime, timedelta
        
        # Rate limiting: wait between authentication attempts
        if self._last_auth_attempt:
            time_since_last = datetime.now() - self._last_auth_attempt
            if time_since_last < timedelta(seconds=5):
                wait_time = 5 - time_since_last.total_seconds()
                _LOGGER.info(f"Rate limiting: waiting {wait_time:.1f}s before authentication attempt")
                await asyncio.sleep(wait_time)
        
        # Prevent too many failed attempts
        if self._auth_failures >= 3:
            _LOGGER.error("Too many authentication failures. Please check credentials and wait before retrying.")
            return False
        
        self._last_auth_attempt = datetime.now()
        session = await self._get_session()
        
        try:
            # Get login page to extract CSRF token - use root URL
            async with session.get(self.base_url) as login_page:
                login_page.raise_for_status()
                content = await login_page.text()
            
            soup = BeautifulSoup(content, 'html.parser')
            csrf_token_element = soup.find('input', {'name': 'authenticity_token'})
            if not csrf_token_element:
                _LOGGER.error("Could not find CSRF token")
                return False
            
            csrf_token = csrf_token_element['value']
            
            # Perform login - use root URL for login post as well
            login_data = {
                'authenticity_token': csrf_token,
                'email': self.username,
                'password': self.password,
                'remember_me': '0',
                'commit': 'Login'
            }
            
            async with session.post(
                self.base_url,
                data=login_data,
                allow_redirects=True
            ) as response:
                response.raise_for_status()
                content = await response.text()
                
                # Check for authentication success/failure
                soup_response = BeautifulSoup(content, 'html.parser')
                
                # Check for explicit failure messages including account lockout
                error_patterns = [
                    r'login.*failed',
                    r'invalid.*credentials',
                    r'authentication.*failed',
                    r'account.*locked',
                    r'password.*reset',
                    r'too.*many.*attempts'
                ]
                
                for pattern in error_patterns:
                    error_messages = soup_response.find_all(text=re.compile(pattern, re.IGNORECASE))
                    if error_messages:
                        error_msg = '; '.join([msg.strip() for msg in error_messages])
                        _LOGGER.error(f"Login failed with message: {error_msg}")
                        return False
                
                # Check if we're still on the login page (indicates failure)
                login_form = soup_response.find('form', action='/')
                email_input = soup_response.find('input', {'name': 'email'})
                if login_form and email_input:
                    _LOGGER.error("Authentication failed: Still on login page after submission")
                    return False
                
                # Extract customer ID from redirect URL or page content
                if '/customers/' in str(response.url):
                    # Extract from URL like /customers/288352
                    customer_match = re.search(r'/customers/(\d+)', str(response.url))
                    if customer_match:
                        self.customer_id = customer_match.group(1)
                
                if not self.customer_id:
                    # Try multiple patterns to find customer ID in page content
                    search_text = str(response.url) + content
                    customer_patterns = [
                        r'/customers/(\d+)',
                        r'customer[_-]?id["\']?\s*[:=]\s*["\']?(\d+)',
                        r'data-customer[_-]?id["\']?\s*=\s*["\']?(\d+)',
                        r'"customer"[^}]*"id"[:\s]*(\d+)',
                        r'customerId["\']?\s*[:=]\s*["\']?(\d+)'
                    ]
                    
                    for pattern in customer_patterns:
                        matches = re.findall(pattern, search_text, re.IGNORECASE)
                        if matches:
                            self.customer_id = matches[0]
                            break
                
                # Look for other success indicators if no customer ID found
                if not self.customer_id:
                    success_indicators = [
                        'dashboard', 'account', 'balance', 'logout', 'welcome'
                    ]
                    
                    content_lower = content.lower()
                    url_lower = str(response.url).lower()
                    
                    for indicator in success_indicators:
                        if indicator in content_lower or indicator in url_lower:
                            _LOGGER.warning(f"Login appears successful (found '{indicator}') but no customer ID extracted")
                            # Try to proceed anyway - some pages might not have customer ID immediately
                            self.customer_id = "unknown"
                            return True
                
                if self.customer_id and self.customer_id != "unknown":
                    _LOGGER.info(f"Successfully authenticated, customer ID: {self.customer_id}")
                    self._auth_failures = 0  # Reset failure count on success
                    return True
                else:
                    _LOGGER.error(f"Authentication failed: Could not extract customer ID. URL: {response.url}")
                    self._auth_failures += 1
                    return False
                
        except Exception as e:
            _LOGGER.error(f"Authentication error: {e}")
            self._auth_failures += 1
            return False
    
    async def get_rate_data(self) -> Dict[str, Any]:
        """Get current rate data from Powershop."""
        if not self.customer_id:
            raise ValueError("Not authenticated")
        
        session = await self._get_session()
        
        try:
            # If customer ID is unknown, try to discover it by accessing the main page
            if self.customer_id == "unknown":
                async with session.get(self.base_url) as main_response:
                    if main_response.status == 200:
                        main_content = await main_response.text()
                        
                        # Try to extract customer ID from main authenticated page
                        customer_patterns = [
                            r'/customers/(\d+)',
                            r'customer[_-]?id["\']?\s*[:=]\s*["\']?(\d+)',
                        ]
                        
                        for pattern in customer_patterns:
                            matches = re.findall(pattern, str(main_response.url) + main_content, re.IGNORECASE)
                            if matches:
                                self.customer_id = matches[0]
                                _LOGGER.info(f"Discovered customer ID: {self.customer_id}")
                                break
                        
                        if self.customer_id == "unknown":
                            # Still couldn't find it, try to extract rate data from main page
                            return self._extract_rates_from_content(main_content)
            
            # Get balance page which contains rate information
            balance_url = f"{self.base_url}/customers/{self.customer_id}/balance"
            async with session.get(balance_url) as response:
                response.raise_for_status()
                content = await response.text()
            
            # Use the enhanced extraction method
            return self._extract_rates_from_content(content)
            
        except Exception as e:
            _LOGGER.error(f"Error getting rate data: {e}")
            raise
    
    async def get_usage_data(self) -> Dict[str, Any]:
        """Get usage data from Powershop."""
        if not self.customer_id:
            raise ValueError("Not authenticated")
        
        session = await self._get_session()
        
        try:
            # Try CSV endpoint for usage data
            csv_url = f"{self.base_url}/customers/{self.customer_id}/usage.csv"
            async with session.get(csv_url) as response:
                if response.status == 200:
                    # Parse CSV content
                    csv_content = await response.text()
                    lines = csv_content.strip().split('\n')
                    if len(lines) > 1:  # Has header and data
                        return {
                            'csv_data': csv_content,
                            'record_count': len(lines) - 1,
                            'available': True
                        }
            
            return {'available': False}
            
        except Exception as e:
            _LOGGER.error(f"Error getting usage data: {e}")
            return {'available': False}
    
    def _extract_rates_from_content(self, content: str) -> Dict[str, Any]:
        """Extract detailed rate data from any HTML content."""
        soup = BeautifulSoup(content, 'html.parser')
        text_content = soup.get_text()
        
        # Extract time-based rate structure
        rate_periods = self._extract_time_based_rates(text_content, soup)
        
        # Look for basic rate patterns as fallback
        rate_patterns = [
            r'(\d+\.\d+)\s*c/kWh',
            r'(\d+\.\d+)\s*cents\s*per\s*kWh',
            r'Rate:\s*(\d+\.\d+)',
            r'Price:\s*(\d+\.\d+)',
            r'(\d+\.\d+)\s*c\s*/\s*kWh',
            r'(\d+\.\d+)\s*¢/kWh'
        ]
        
        rates = []
        for pattern in rate_patterns:
            matches = re.findall(pattern, text_content, re.IGNORECASE)
            rates.extend([float(match) for match in matches])
        
        # Remove duplicates and sort
        unique_rates = sorted(list(set(rates)))
        
        # Also check tables for structured rate data
        rate_tables = soup.find_all('table')
        for table in rate_tables:
            table_text = table.get_text().lower()
            if 'rate' in table_text or 'price' in table_text or 'kwh' in table_text:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        cell_text = ' '.join([cell.get_text().strip() for cell in cells])
                        rate_match = re.search(r'(\d+\.\d+)', cell_text)
                        if rate_match and 'kwh' in cell_text.lower():
                            rate_value = float(rate_match.group(1))
                            if rate_value not in rates:
                                rates.append(rate_value)
        
        return {
            'rates': unique_rates,
            'primary_rate': unique_rates[0] if unique_rates else None,
            'rate_periods': rate_periods,
            'customer_id': self.customer_id,
            'last_updated': None  # Will be set by sensor
        }
    
    def _extract_time_based_rates(self, text_content: str, soup) -> Dict[str, Any]:
        """Extract time-of-use rate periods and prices."""
        rate_periods = {}
        
        # First, look for data-tooltip attributes which contain the structured data
        tooltip_elements = soup.find_all(attrs={"data-tooltip": True})
        
        for element in tooltip_elements:
            tooltip_text = element.get('data-tooltip', '')
            
            # Clean up tooltip text - normalize whitespace and newlines
            cleaned_tooltip = re.sub(r'\s+', ' ', tooltip_text).strip()
            
            # Pattern for tooltip format: "Off Peak 12am - 7am 19.08 c/kWh" (with flexible whitespace)
            tooltip_patterns = [
                # Standard format with spaces
                r'(Off Peak|Weekday Peak|Weekend Peak|Weekday Shoulder|Weekend Shoulder|Peak|Shoulder)\s+([0-9]{1,2}[ap]m\s*-\s*[0-9]{1,2}[ap]m)\s+(\d+\.\d+)\s*c/kWh',
                # Newline format - match across lines
                r'(Off Peak|Weekday Peak|Weekend Peak|Weekday Shoulder|Weekend Shoulder|Peak|Shoulder)\s*[\n\r\s]*([0-9]{1,2}[ap]m\s*-\s*[0-9]{1,2}[ap]m)\s*[\n\r\s]*(\d+\.\d+)\s*c/kWh'
            ]
            
            matched = False
            for pattern in tooltip_patterns:
                # Try both original and cleaned text
                for text_to_check in [tooltip_text, cleaned_tooltip]:
                    match = re.search(pattern, text_to_check, re.IGNORECASE | re.MULTILINE | re.DOTALL)
                    if match:
                        period_name = match.group(1).strip()
                        time_range = match.group(2).strip()
                        rate = float(match.group(3))
                        
                        rate_periods[period_name] = {
                            'time_range': time_range,
                            'rate': rate,
                            'rate_formatted': f"{rate} c/kWh"
                        }
                        matched = True
                        break
                
                if matched:
                    break
        
        # If we found tooltip data, return it
        if rate_periods:
            return rate_periods
        
        # Clean up text content - remove extra whitespace and normalize
        cleaned_text = re.sub(r'\s+', ' ', text_content).strip()
        
        # Enhanced patterns to match various text structures
        time_patterns = [
            # Pattern 1: "Off Peak 12am - 7am 19.08 c/kWh"
            r'(Off Peak|Weekday Peak|Weekend Peak|Weekday Shoulder|Weekend Shoulder|Peak|Shoulder)\s+([0-9]{1,2}[ap]m\s*-\s*[0-9]{1,2}[ap]m)\s+(\d+\.\d+)\s*c/kWh',
            # Pattern 2: Multi-line format with newlines
            r'(Off Peak|Weekday Peak|Weekend Peak|Weekday Shoulder|Weekend Shoulder|Peak|Shoulder)\s*\n?\s*([0-9]{1,2}[ap]m\s*-\s*[0-9]{1,2}[ap]m)\s*\n?\s*(\d+\.\d+)\s*c/kWh',
            # Pattern 3: More flexible with various whitespace
            r'(Off Peak|Weekday Peak|Weekend Peak|Weekday Shoulder|Weekend Shoulder)\s*[\n\r\s]*([0-9]{1,2}[ap]m\s*-\s*[0-9]{1,2}[ap]m)\s*[\n\r\s]*(\d+\.\d+)\s*c/kWh',
        ]
        
        # Try each pattern against both cleaned and original text
        for text_to_search in [cleaned_text, text_content]:
            for pattern in time_patterns:
                matches = re.finditer(pattern, text_to_search, re.IGNORECASE | re.MULTILINE | re.DOTALL)
                for match in matches:
                    period_name = match.group(1).strip()
                    time_range = match.group(2).strip()
                    rate = float(match.group(3))
                    
                    # Avoid duplicates - use period name + time as key
                    key = f"{period_name}_{time_range}"
                    if key not in rate_periods:
                        rate_periods[period_name] = {
                            'time_range': time_range,
                            'rate': rate,
                            'rate_formatted': f"{rate} c/kWh"
                        }
                        _LOGGER.info(f"Found rate period: {period_name} ({time_range}) = {rate} c/kWh")
        
        # Also try extracting from specific HTML sections
        rate_sections = soup.find_all(['div', 'section', 'table', 'span', 'p'], 
                                    class_=lambda x: x and any(word in x.lower() 
                                    for word in ['rate', 'tariff', 'price', 'plan', 'usage', 'time']))
        
        for section in rate_sections:
            section_text = section.get_text()
            cleaned_section = re.sub(r'\s+', ' ', section_text).strip()
            
            for text_to_search in [section_text, cleaned_section]:
                for pattern in time_patterns:
                    matches = re.finditer(pattern, text_to_search, re.IGNORECASE | re.MULTILINE | re.DOTALL)
                    for match in matches:
                        period_name = match.group(1).strip()
                        time_range = match.group(2).strip()
                        rate = float(match.group(3))
                        
                        # Avoid duplicates
                        key = f"{period_name}_{time_range}"
                        if key not in rate_periods:
                            rate_periods[period_name] = {
                                'time_range': time_range,
                                'rate': rate,
                                'rate_formatted': f"{rate} c/kWh"
                            }
        
        # If we still haven't found periods, try a more aggressive search
        if not rate_periods:
            # Look for any text that contains both time ranges and rates
            aggressive_pattern = r'(\w+\s*\w*)\s*([0-9]{1,2}[ap]m\s*-\s*[0-9]{1,2}[ap]m)\s*(\d+\.\d+)'
            matches = re.finditer(aggressive_pattern, text_content, re.IGNORECASE | re.MULTILINE)
            
            for match in matches:
                potential_period = match.group(1).strip()
                time_range = match.group(2).strip()
                rate = float(match.group(3))
                
                # Only accept if it looks like a rate period name
                if any(keyword in potential_period.lower() for keyword in ['peak', 'shoulder', 'off']):
                    rate_periods[potential_period] = {
                        'time_range': time_range,
                        'rate': rate,
                        'rate_formatted': f"{rate} c/kWh"
                    }
        
        return rate_periods