"""
Browser automation module for SeerrBridge
Handles Selenium browser initialization and interactions with Debrid Media Manager
"""
import platform
import time
import os
import requests
import zipfile
import io
from loguru import logger
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager, ChromeType
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException,
    NoSuchElementException,
    TimeoutException,
    ElementClickInterceptedException,
    SessionNotCreatedException,
)
from fuzzywuzzy import fuzz
from seerr.config import (
    HEADLESS_MODE,
    RD_ACCESS_TOKEN,
    RD_CLIENT_ID,
    RD_CLIENT_SECRET,
    RD_REFRESH_TOKEN,
    TORRENT_FILTER_REGEX,
    SYSTEM_JUNK_BLACKLIST,
    MAX_MOVIE_SIZE,
    MAX_EPISODE_SIZE,
    USE_DATABASE
)
# Global driver variable to hold the Selenium WebDriver
driver = None
# Global library stats
library_stats = {
    "torrents_count": 0,
    "total_size_tb": 0.0,
    "last_updated": None
}

# Import database modules if using database
if USE_DATABASE:
    from seerr.database import get_db, LibraryStats
    from seerr.db_logger import log_info, log_success, log_warning, log_error
def get_latest_chrome_driver():
    """
    Fetch the latest stable Chrome driver from Google's Chrome for Testing.
    Returns the path to the downloaded chromedriver executable.
    """
    try:
        # Get the current operating system
        current_os = platform.system().lower()
        current_arch = platform.machine().lower()
       
        # Map OS to platform identifier used by Chrome for Testing
        platform_map = {
            'windows': 'win32' if platform.architecture()[0] == '32bit' else 'win64',
            'linux': 'linux64' if current_arch in ['x86_64'] else 'linux-arm64' if current_arch in ['aarch64', 'arm64'] else None,
            'darwin': 'mac-arm64' if current_arch in ['arm64', 'aarch64'] else 'mac-x64'
        }
       
        os_platform = platform_map.get(current_os)
        if not os_platform:
            logger.error(f"Unsupported operating system: {current_os}")
            return None
           
        # Fetch latest stable version information
        logger.info(f"Fetching latest stable Chrome driver information for {os_platform}")
        response = requests.get("https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json")
        response.raise_for_status()
       
        data = response.json()
        stable_version = data['channels']['Stable']['version']
        downloads = data['channels']['Stable']['downloads']['chromedriver']
       
        # Find the download URL for the current platform
        download_url = None
        for item in downloads:
            if item['platform'] == os_platform:
                download_url = item['url']
                break
               
        if not download_url:
            logger.error(f"Could not find Chrome driver download for platform: {os_platform}")
            return None
           
        # Create a directory for the driver if it doesn't exist
        driver_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chromedriver")
        os.makedirs(driver_dir, exist_ok=True)
       
        # Download and extract the driver
        logger.info(f"Downloading Chrome driver v{stable_version} from {download_url}")
        response = requests.get(download_url)
        response.raise_for_status()
       
        # Extract the zip file
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
            zip_file.extractall(driver_dir)
           
        # Find the chromedriver executable in the extracted files
        if current_os == 'windows':
            driver_path = os.path.join(driver_dir, "chromedriver-" + os_platform, "chromedriver.exe")
        else:
            driver_path = os.path.join(driver_dir, "chromedriver-" + os_platform, "chromedriver")
            # Make the driver executable on Unix-like systems
            os.chmod(driver_path, 0o755)
           
        logger.info(f"Successfully downloaded and extracted Chrome driver v{stable_version} to {driver_path}")
        return driver_path
       
    except Exception as e:
        logger.error(f"Error downloading Chrome driver: {e}")
        return None
async def initialize_browser():
    """Initialize the Selenium WebDriver and set up the browser."""
    global driver
    if driver is None:
        logger.info("Starting persistent browser session.")
        # Detect the current operating system
        current_os = platform.system().lower() # Returns 'windows', 'linux', or 'darwin' (macOS)
        current_arch = platform.machine().lower()
        logger.info(f"Detected operating system: {current_os}, architecture: {current_arch}")
        options = Options()
        ### Handle Docker/Linux-specific configurations
        if current_os == "linux" and os.getenv("RUNNING_IN_DOCKER", "false").lower() == "true":
            logger.info("Detected Linux environment inside Docker. Applying Linux-specific configurations.")
            # Explicitly set the Chrome binary location
            options.binary_location = os.getenv("CHROME_BIN", "/usr/bin/google-chrome")
            # Enable headless mode for Linux/Docker environments
            options.add_argument("--headless=new") # Updated modern headless flag
            options.add_argument("--no-sandbox") # Required for running as root in Docker
            options.add_argument("--disable-dev-shm-usage") # Handle shared memory limitations
            options.add_argument("--disable-gpu") # Disable GPU rendering for headless environments
            options.add_argument("--disable-setuid-sandbox") # Bypass setuid sandbox
        ### Handle Windows-specific configurations
        elif current_os == "windows":
            logger.info("Detected Windows environment. Applying Windows-specific configurations.")
        elif current_os == "linux" and current_arch in ['aarch64', 'arm64']:
            logger.info("Detected ARM Linux environment (likely Raspberry Pi). Applying ARM-specific configurations.")
            options.binary_location = "/usr/bin/chromium-browser"
            if HEADLESS_MODE:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-setuid-sandbox")
        if HEADLESS_MODE:
            options.add_argument("--headless=new") # Modern headless mode for Chrome
        options.add_argument("--disable-gpu") # Disable GPU for Docker compatibility
        options.add_argument("--no-sandbox") # Required for running browser as root
        options.add_argument("--disable-dev-shm-usage") # Disable shared memory usage restrictions
        options.add_argument("--disable-setuid-sandbox") # Disable sandboxing for root permissions
        options.add_argument("--enable-logging")
        options.add_argument("--window-size=1920,1080") # Set explicit window size to avoid rendering issues
        # WebDriver options to suppress infobars and disable automation detection
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36")
        
        try:
            # In Docker, prioritize system-installed chromedriver (matches Chrome version from Dockerfile)
            chrome_driver_path = None
            if os.path.exists('/.dockerenv'):
                # Docker environment - check system-installed chromedriver first
                system_paths = ["/usr/local/bin/chromedriver", "/usr/bin/chromedriver"]
                for sys_path in system_paths:
                    if os.path.exists(sys_path):
                        chrome_driver_path = sys_path
                        logger.info(f"Using system-installed Chrome driver: {chrome_driver_path}")
                        break
                
                # If system chromedriver not found, try downloading
                if not chrome_driver_path:
                    chrome_driver_path = get_latest_chrome_driver()
                    if chrome_driver_path and os.path.exists(chrome_driver_path):
                        logger.info(f"Using Chrome driver from Chrome for Testing: {chrome_driver_path}")
            else:
                # Local development - try downloading first
                chrome_driver_path = get_latest_chrome_driver()
                if chrome_driver_path and os.path.exists(chrome_driver_path):
                    logger.info(f"Using Chrome driver from Chrome for Testing: {chrome_driver_path}")
          
            driver = None
            if chrome_driver_path and os.path.exists(chrome_driver_path):
                try:
                    driver = webdriver.Chrome(service=Service(chrome_driver_path), options=options)
                except SessionNotCreatedException as e:
                    if "This version of ChromeDriver only supports Chrome version" in str(e):
                        logger.warning(
                            "ChromeDriver version mismatch (installed Chrome may be behind latest). "
                            "Retrying with WebDriver Manager to match your Chrome version."
                        )
                        driver = None
                    else:
                        raise
            if driver is None and current_arch not in ['aarch64', 'arm64']:
                # Fallback: WebDriver Manager detects installed Chrome and downloads matching driver
                logger.warning(
                    "Using WebDriver Manager to install ChromeDriver matching your installed Chrome version."
                )
                driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            elif driver is None and current_arch in ['aarch64', 'arm64']:
                driver = webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)
            # Suppress 'webdriver' detection
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                Object.defineProperty(navigator, 'webdriver', {
                  get: () => undefined
                })
                """
            })
            logger.info("Initialized Selenium WebDriver successfully.")
            # Navigate to an initial page to confirm browser works
            driver.get("https://debridmediamanager.com")
            logger.info("Navigated to Debrid Media Manager page.")
        except Exception as e:
            logger.error(f"Failed to initialize Selenium WebDriver: {e}")
            logger.warning("Browser automation will be disabled. The application will continue without browser functionality.")
            driver = None  # Ensure driver is None on failure
            return None  # Return None instead of raising the exception
        # If initialization succeeded, continue with setup
        if driver:
            try:
                # Inject Real-Debrid access token and other credentials into local storage
                driver.execute_script(f"""
                    localStorage.setItem('rd:accessToken', '{RD_ACCESS_TOKEN}');
                    localStorage.setItem('rd:clientId', '{RD_CLIENT_ID}');
                    localStorage.setItem('rd:clientSecret', '{RD_CLIENT_SECRET}');
                    localStorage.setItem('rd:refreshToken', '{RD_REFRESH_TOKEN}');
                """)
                logger.info("Set Real-Debrid credentials in local storage.")
                # Refresh the page to apply the local storage values
                driver.refresh()
                login(driver)
                logger.info("Refreshed the page to apply local storage values.")
                driver.refresh()
                # Handle potential premium expiration modal
                try:
                    modal_h2 = WebDriverWait(driver, 2).until(
                        EC.presence_of_element_located((By.XPATH, "//h2[contains(text(), 'Premium Expiring Soon')]"))
                    )
                    logger.info("Premium Expiring Soon modal detected.")
                    # Extract the message to get days
                    p_element = driver.find_element(By.XPATH, "//p[contains(text(), 'Your Real-Debrid premium subscription will expire in')]")
                    message = p_element.text.strip()
                    import re
                    days_match = re.search(r'expire in (\d+) days', message)
                    days = int(days_match.group(1)) if days_match else "UNKNOWN"
                    # Log distinct message in big caps
                    logger.warning(f"YOUR REAL-DEBRID PREMIUM WILL EXPIRE IN {days} DAYS!!!")
                    # Click Cancel to dismiss
                    cancel_button = driver.find_element(By.XPATH, "//button[text()='Cancel']")
                    cancel_button.click()
                    logger.info("Dismissed the premium expiration modal by clicking Cancel.")
                    time.sleep(1) # Wait briefly for modal to disappear
                except TimeoutException:
                    logger.info("No premium expiration modal found. Proceeding.")
              
                # Navigate to the new settings page
                try:
                    logger.info("Navigating to the new settings page.")
                    driver.get("https://debridmediamanager.com/settings")
                    WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.ID, "dmm-movie-max-size"))
                    )
                    logger.info("Settings page loaded successfully.")
                    logger.info("Locating maximum movie size select element in 'Settings'.")
                    max_movie_select_elem = WebDriverWait(driver, 3).until(
                        EC.visibility_of_element_located((By.ID, "dmm-movie-max-size"))
                    )
                    # Initialize Select class with the <select> WebElement
                    select_obj = Select(max_movie_select_elem)
                    
                    # Get all available options to validate the value
                    available_options = [option.get_attribute('value') for option in select_obj.options]
                    logger.info(f"Available movie size options: {available_options}")
                    
                    # Validate and select the appropriate movie size
                    movie_size_value = str(int(MAX_MOVIE_SIZE)) if MAX_MOVIE_SIZE is not None else "0"
                    if movie_size_value in available_options:
                        select_obj.select_by_value(movie_size_value)
                        logger.info("Biggest Movie Size Selected as {} GB.".format(MAX_MOVIE_SIZE))
                    else:
                        # Fallback to "Biggest available" (value="0") if the specified value is not available
                        logger.warning(f"Movie size value '{movie_size_value}' not available. Available options: {available_options}. Using 'Biggest available' (0) as fallback.")
                        select_obj.select_by_value("0")
                        logger.info("Biggest Movie Size Selected as 'Biggest available' (0) as fallback.")
                    # MAX EPISODE SIZE: Locate the maximum series size select element
                    logger.info("Locating maximum series size select element in 'Settings'.")
                    max_episode_select_elem = WebDriverWait(driver, 3).until(
                        EC.visibility_of_element_located((By.ID, "dmm-episode-max-size"))
                    )
                    # Initialize Select class with the <select> WebElement
                    select_obj = Select(max_episode_select_elem)
                    
                    # Get all available options to validate the value
                    available_options = [option.get_attribute('value') for option in select_obj.options]
                    logger.info(f"Available episode size options: {available_options}")
                    
                    # Validate and select the appropriate episode size
                    # Handle both integer and float values properly
                    if MAX_EPISODE_SIZE is not None:
                        if MAX_EPISODE_SIZE == int(MAX_EPISODE_SIZE):
                            # Integer value (e.g., 1, 3, 5)
                            episode_size_value = str(int(MAX_EPISODE_SIZE))
                        else:
                            # Float value (e.g., 0.1, 0.3, 0.5)
                            episode_size_value = str(MAX_EPISODE_SIZE)
                    else:
                        episode_size_value = "0"
                    
                    if episode_size_value in available_options:
                        select_obj.select_by_value(episode_size_value)
                        logger.info("Biggest Episode Size Selected as {} GB.".format(MAX_EPISODE_SIZE))
                    else:
                        # Fallback to "Biggest available" (value="0") if the specified value is not available
                        logger.warning(f"Episode size value '{episode_size_value}' not available. Available options: {available_options}. Using 'Biggest available' (0) as fallback.")
                        select_obj.select_by_value("0")
                        logger.info("Biggest Episode Size Selected as 'Biggest available' (0) as fallback.")
                    # Locate the "Default torrents filter" input box and insert the regex
                    logger.info("Attempting to insert regex into 'Default torrents filter' box.")
                    default_filter_input = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.ID, "dmm-default-torrents-filter"))
                    )
                    if TORRENT_FILTER_REGEX is not None:
                        default_filter_input.clear() # Clear any existing filter
                        # Use a simpler filter for DMM UI to ensure results are returned
                        # The complex regex will be applied in Python code
                        simple_ui_filter = "1080p 720p"
                        default_filter_input.send_keys(simple_ui_filter)
                        logger.info(f"Inserted simple filter into DMM UI: {simple_ui_filter} (Full regex will be applied in Python)")
                    else:
                        logger.info("TORRENT_FILTER_REGEX is not set. Skipping insertion into 'Default torrents filter' box.")
                    # Assume settings are auto-saved; no explicit save button
                    logger.info("Settings updated successfully.")
                except (TimeoutException, NoSuchElementException, ElementClickInterceptedException) as ex:
                    logger.error(f"Error while interacting with the settings: {ex}")
                    logger.warning("Continuing without applying custom settings (TORRENT_FILTER_REGEX, MAX_MOVIE_SIZE, MAX_EPISODE_SIZE)")
                except Exception as ex:
                    logger.error(f"Unexpected error while configuring settings: {ex}")
                    logger.warning("Continuing without applying custom settings due to unexpected error")
                # Navigate to the library section
                logger.info("Navigating to the library section.")
                driver.get("https://debridmediamanager.com/library")
                # Wait for 2 seconds on the library page before further processing
                try:
                    # Ensure the library page has loaded correctly (e.g., wait for a specific element on the library page)
                    library_element = WebDriverWait(driver, 2).until(
                        EC.presence_of_element_located((By.XPATH, "//div[@id='library-content']")) # Adjust the XPath as necessary
                    )
                    logger.info("Library section loaded successfully.")
                except TimeoutException:
                    logger.info("Library loading.")
                # Wait for at least 7 seconds on the library page
                logger.info("Waiting for 7 seconds on the library page.")
                time.sleep(7)
                logger.info("Completed waiting on the library page.")
             
                # Extract library stats from the page
                try:
                    logger.info("Extracting library statistics from the page.")
                    library_stats_element = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.XPATH, "//h1[contains(@class, 'text-xl') and contains(@class, 'font-bold') and contains(@class, 'text-white') and contains(text(), 'Library')]"))
                    )
                    library_stats_text = library_stats_element.text.strip()
                    logger.info(f"Found library stats text: {library_stats_text}")
                 
                    # Parse the text to extract torrent count and size
                    # Example: "Library, 3132 torrents, 76.5 TB"
                    import re
                    from datetime import datetime
                 
                    # Extract torrent count
                    torrent_match = re.search(r'(\d+)\s+torrents', library_stats_text)
                    torrents_count = int(torrent_match.group(1)) if torrent_match else 0
                 
                    # Extract TB size
                    size_match = re.search(r'([\d.]+)\s*TB', library_stats_text)
                    total_size_tb = float(size_match.group(1)) if size_match else 0.0
                 
                    # Update global library stats
                    global library_stats
                    library_stats = {
                        "torrents_count": torrents_count,
                        "total_size_tb": total_size_tb,
                        "last_updated": datetime.now().isoformat()
                    }
                 
                    logger.info(f"Successfully extracted library stats: {torrents_count} torrents, {total_size_tb} TB")
                 
                except TimeoutException:
                    logger.warning("Could not find library stats element on the page within timeout.")
                except Exception as e:
                    logger.error(f"Error extracting library stats: {e}")
             
                logger.info("Browser initialization completed successfully.")
            except Exception as e:
                logger.error(f"Error during browser setup: {e}")
                if driver:
                    driver.quit()
                    driver = None
    else:
        logger.info("Browser already initialized.")
 
    return driver # Return the driver instance for direct use
async def shutdown_browser():
    """Shut down the browser and clean up resources."""
    global driver
    if driver:
        driver.quit()
        logger.warning("Selenium WebDriver closed.")
        driver = None

def login(driver):
    """Handle login to Debrid Media Manager."""
    logger.info("Initiating login process.")

    try:
        # Check if the "Login with Real Debrid" button exists and is clickable
        login_button = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Login with Real Debrid')]"))
        )
        if login_button:
            login_button.click()
            logger.info("Clicked on 'Login with Real Debrid' button.")
        else:
            logger.info("'Login with Real Debrid' button was not found. Skipping this step.")

    except TimeoutException:
        # Handle case where the button was not found before the timeout
        logger.warning("'Login with Real Debrid' button not found or already bypassed. Proceeding...")
    
    except NoSuchElementException:
        # Handle case where the element is not in the DOM
        logger.warning("'Login with Real Debrid' button not present in the DOM. Proceeding...")

    except Exception as ex:
        # Log any other unexpected exception
        logger.error(f"An unexpected error occurred during login: {ex}")

def click_show_more_results(driver, logger, max_attempts=3, wait_between=3, initial_timeout=5, subsequent_timeout=5):
    """
    Attempts to click the 'Show More Results' button multiple times with waits in between.
    
    Args:
        driver: The WebDriver instance
        logger: Logger instance for logging events
        max_attempts: Number of times to try clicking the button (default: 2)
        wait_between: Seconds to wait between clicks (default: 3)
        initial_timeout: Initial timeout in seconds for first click (default: 5)
        subsequent_timeout: Timeout in seconds for subsequent clicks (default: 5)
    """
    for attempt in range(max_attempts):
        try:
            # Adjust timeout based on whether it's the first attempt
            timeout = initial_timeout if attempt == 0 else subsequent_timeout
            
            # Locate and click the button
            show_more_button = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'haptic') and contains(text(), 'Show More Results')]"))
            )
            show_more_button.click()
            logger.info(f"Clicked 'Show More Results' button ({attempt + 1}{'st' if attempt == 0 else 'nd/th'} time).")
            
            # Wait between clicks if not the last attempt
            if attempt < max_attempts - 1:
                time.sleep(wait_between)
                
            time.sleep(2)    
        except TimeoutException:
            logger.info(f"No 'Show More Results' button found for {attempt + 1}{'st' if attempt == 0 else 'nd/th'} click after {timeout} seconds. Proceeding anyway.")
            break  # Exit the loop if we can't find the button
        except Exception as e:
            logger.warning(f"Error clicking 'Show More Results' button on attempt {attempt + 1}: {e}. Proceeding anyway.")
            break  # Exit on other errors too

def prioritize_buttons_in_box(result_box):
    """
    Prioritize buttons within a result box. Clicks the 'Instant RD' or 'DL with RD' button
    if available. Handles stale element references by retrying the operation once.

    Args:
        result_box (WebElement): The result box element.

    Returns:
        bool: True if a button was successfully clicked and handled, False otherwise.
    """
    global driver
    
    try:
        # Wait for the button container to be present (div with class 'space-x-1 space-y-1')
        try:
            WebDriverWait(driver, 2).until(
                lambda d: result_box.find_element(By.XPATH, ".//div[contains(@class, 'space-x-1')]//button")
            )
        except TimeoutException:
            logger.debug("Button container not found immediately, proceeding anyway")
        
        # Wait a moment for buttons to be fully rendered
        time.sleep(0.3)
        
        # First, try to find 'Instant RD' button
        instant_rd_button = None
        
        # Strategy 1: Find by class (green button) and verify text
        try:
            # Find all buttons with green background class
            green_buttons = result_box.find_elements(By.XPATH, ".//button[contains(@class, 'bg-green-900/30')]")
            for btn in green_buttons:
                try:
                    button_text = btn.text.strip()
                    if "Instant RD" in button_text or "Instant" in button_text:
                        instant_rd_button = btn
                        logger.info(f"Located 'Instant RD' button with text: '{button_text}'")
                        break
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Error finding green buttons: {e}")
        
        # Strategy 2: Search all buttons by text content (more reliable for nested text)
        if instant_rd_button is None:
            try:
                all_buttons = result_box.find_elements(By.XPATH, ".//button")
                logger.debug(f"Found {len(all_buttons)} total buttons in result_box")
                for button in all_buttons:
                    try:
                        button_text = button.text.strip()
                        # Check for "Instant RD" or just "Instant" (in case RD is missing)
                        if "Instant RD" in button_text or ("Instant" in button_text and "RD" in button_text):
                            instant_rd_button = button
                            logger.info(f"Located 'Instant RD' button by text search. Full text: '{button_text}'")
                            break
                    except (StaleElementReferenceException, Exception) as e:
                        logger.debug(f"Error reading button text: {e}")
                        continue
            except Exception as e:
                logger.debug(f"Error searching all buttons for 'Instant RD': {e}")
        
        # If we found Instant RD button, try to click it
        if instant_rd_button is not None:
            try:
                if attempt_button_click_with_state_check(instant_rd_button, result_box):
                    return True
            except Exception as e:
                logger.warning(f"Error clicking 'Instant RD' button: {e}")

    except StaleElementReferenceException:
        logger.warning("Stale element reference encountered for 'Instant RD' button. Retrying...")
        try:
            green_buttons = result_box.find_elements(By.XPATH, ".//button[contains(@class, 'bg-green-900/30')]")
            for btn in green_buttons:
                try:
                    button_text = btn.text.strip()
                    if "Instant RD" in button_text and attempt_button_click_with_state_check(btn, result_box):
                        return True
                except:
                    continue
        except Exception as e:
            logger.debug(f"Retry failed for 'Instant RD' button: {e}")

    # If 'Instant RD' button is not found, try to locate the 'DL with RD' button
    try:
        dl_with_rd_button = None
        
        # Method 1: Find blue button by class
        try:
            blue_buttons = result_box.find_elements(By.XPATH, ".//button[contains(@class, 'bg-blue-900/30')]")
            for btn in blue_buttons:
                try:
                    button_text = btn.text.strip()
                    if "DL with RD" in button_text or ("DL" in button_text and "RD" in button_text and "with" in button_text):
                        dl_with_rd_button = btn
                        logger.info(f"Located 'DL with RD' button (blue) with text: '{button_text}'")
                        break
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Error finding blue buttons: {e}")
        
        # Method 2: Search all buttons by text content
        if dl_with_rd_button is None:
            try:
                all_buttons = result_box.find_elements(By.XPATH, ".//button")
                for button in all_buttons:
                    try:
                        button_text = button.text.strip()
                        # Look for "DL with RD" or variations
                        if "DL with RD" in button_text or ("DL" in button_text and "with RD" in button_text):
                            dl_with_rd_button = button
                            logger.info(f"Located 'DL with RD' button by text search. Full text: '{button_text}'")
                            break
                    except (StaleElementReferenceException, Exception):
                        continue
            except Exception as e:
                logger.debug(f"Error searching for 'DL with RD' button by text: {e}")
        
        if dl_with_rd_button is not None:
            # Attempt to click the button and wait for a state change
            if attempt_button_click_with_state_check(dl_with_rd_button, result_box):
                return True

    except StaleElementReferenceException:
        logger.warning("Stale element reference encountered for 'DL with RD' button. Retrying...")
        try:
            blue_buttons = result_box.find_elements(By.XPATH, ".//button[contains(@class, 'bg-blue-900/30')]")
            for btn in blue_buttons:
                try:
                    button_text = btn.text.strip()
                    if "DL with RD" in button_text and attempt_button_click_with_state_check(btn, result_box):
                        return True
                except:
                    continue
        except Exception as e:
            logger.debug(f"Retry failed for 'DL with RD' button: {e}")

    except Exception as e:
        logger.debug(f"Error searching for 'DL with RD' button: {e}")

    # If we get here, neither button was found - log available buttons for debugging
    try:
        all_buttons = result_box.find_elements(By.XPATH, ".//button")
        button_info = []
        for btn in all_buttons:
            try:
                btn_text = btn.text.strip()
                btn_class = btn.get_attribute("class")
                # Only show first 50 chars of text and 80 chars of class
                button_info.append(f"Text: '{btn_text[:50]}', Class: '{btn_class[:80]}'")
            except Exception:
                button_info.append("(could not read button)")
        logger.warning(f"Neither 'Instant RD' nor 'DL with RD' button found in this box. Available buttons ({len(all_buttons)}): {button_info}")
    except Exception as e:
        logger.warning(f"Error getting button info: {e}")

    return False

def attempt_button_click_with_state_check(button, result_box):
    """
    Attempts to click a button and waits for its state to change.
    Waits for overlay to disappear before clicking so the click is not intercepted.

    Args:
        button (WebElement): The button element to click.
        result_box (WebElement): The parent result box (used for context).

    Returns:
        bool: True if the button's state changes, False otherwise.
    """
    global driver
    overlay_xpath = "//div[contains(@class, 'fixed inset-0') and contains(@class, 'bg-black')]"
    try:
        # Wait for overlay to disappear so click is not intercepted
        try:
            WebDriverWait(driver, 10).until(
                EC.invisibility_of_element_located((By.XPATH, overlay_xpath))
            )
        except TimeoutException:
            pass
        # Get the initial state of the button
        initial_state = button.get_attribute("class")  # Or another attribute relevant to the state
        logger.info(f"Initial button state: {initial_state}")

        # Click the button
        button.click()
        logger.info("Clicked the button.")

        # Wait for a short period (max 2 seconds) to check for changes in the state (use driver, not result_box)
        WebDriverWait(driver, 2).until(
            lambda d: button.get_attribute("class") != initial_state
        )
        logger.info("Button state changed successfully after clicking.")
        return True  # Button was successfully clicked and handled

    except TimeoutException:
        logger.warning("No state change detected after clicking the button within 2 seconds.")

    except StaleElementReferenceException:
        logger.error("Stale element reference encountered while waiting for button state change.")
        # Click may have succeeded and DOM updated; treat as possible success
        return True

    return False

def relocate_red_buttons(driver, target_index):
    """
    Re-locate red buttons after stale element reference
    Returns the button at target_index if found, None otherwise
    """
    try:
        # Wait a bit for the page to stabilize
        time.sleep(1)
        
        # Re-find all availability buttons (red or green)
        # We look for buttons containing "RD" or "INSTANT"
        all_avail = driver.find_elements(By.TAG_NAME, "button")
        avail_buttons_elements = []
        for button in all_avail:
            try:
                bt = button.text.strip().upper()
                if "REPORT" not in bt and ("RD" in bt or "INSTANT" in bt):
                    avail_buttons_elements.append(button)
            except StaleElementReferenceException:
                continue
            except Exception as e:
                logger.warning(f"Error accessing button during re-location: {e}")
                continue
        
        logger.info(f"Re-located {len(avail_buttons_elements)} availability buttons, looking for index {target_index}")
        
        if target_index <= len(avail_buttons_elements):
            return avail_buttons_elements[target_index-1]
        return None
    except Exception as e:
        logger.warning(f"Error re-locating red buttons: {e}")
        return None

def check_red_buttons(driver, movie_title, normalized_seasons, confirmed_seasons, is_tv_show, episode_id=None, processed_torrents=None, complete_season_pack_only=False):
    """
    Check for red buttons (RD 100%) on the page and verify if they match the expected title
   
    Args:
        driver: Selenium WebDriver instance
        movie_title: Expected title to match
        normalized_seasons: List of seasons in normalized format
        confirmed_seasons: Set of already confirmed seasons
        is_tv_show: Whether we're checking a TV show
        episode_id: Optional episode ID for TV shows
        processed_torrents: Set of already processed torrent titles to avoid duplicates
        complete_season_pack_only: If True, only accept complete season packs, not individual episodes
       
    Returns:
        Tuple[bool, set]: (confirmation flag, updated confirmed seasons set)
    """
    from seerr.utils import clean_title, extract_year, extract_season
    import re
   
    confirmation_flag = False
    if processed_torrents is None:
        processed_torrents = set()
    
    try:
        # Find ALL buttons on the page for maximum robustness and diagnostic logging
        all_elements = driver.find_elements(By.TAG_NAME, "button")
        logger.info(f"Total <button> elements found on page: {len(all_elements)}")
        
        # Filter buttons that indicate availability
        valid_buttons_elements = []
        filtered_button_samples = []
        
        for button in all_elements:
            try:
                # Include hidden text and icons
                button_text = button.text.strip()
                button_class = button.get_attribute("class") or ""
                
                # Check for "RD" or "Instant" in text (case-insensitive) OR specific classes/icons
                # DMM uses bg-red-900/30, bg-green-900/30, etc.
                # Also look for Real-Debrid icons (img with src containing real-debrid)
                is_availability = any(x in button_text.upper() for x in ["RD", "INSTANT", "LIBRARY", "DEBRID"]) or \
                                 len(button.find_elements(By.XPATH, ".//img[contains(@src, 'real-debrid')]")) > 0
                is_report = "REPORT" in button_text.upper()
                
                # Diagnostic logging for anything that looks like an RD button
                if is_availability:
                    logger.debug(f"Detected potential availability button: text='{button_text}', class='{button_class}'")
                
                if is_availability and not is_report:
                    # We want "RD (100%)", "Instant RD", or buttons with RD icons
                    valid_buttons_elements.append(button)
                else:
                    if len(filtered_button_samples) < 10 and (is_availability or "CAST" in button_text.upper()):
                        filtered_button_samples.append(f"'{button_text}' (class: {button_class})")
            except StaleElementReferenceException:
                continue
            except Exception as e:
                logger.warning(f"Error accessing button during filtering: {e}")
                continue
        
        logger.info(f"Found {len(valid_buttons_elements)} availability button(s) after filtering. Verifying titles.")
        
        if len(valid_buttons_elements) == 0:
            logger.warning("No availability buttons found. Detailed diagnostics:")
            # Log first 5 buttons found just to see what's on the page
            for i, b in enumerate(all_elements[:10]):
                try:
                    logger.info(f"Diagnostic button {i}: text='{b.text}', class='{b.get_attribute('class')}'")
                except:
                    pass
        
        # Log samples of filtered buttons for debugging, especially when searching for episodes
        if episode_id and len(valid_buttons_elements) == 0 and filtered_button_samples:
            logger.info(f"All {len(all_elements)} red/green buttons were filtered out. Sample button texts: {filtered_button_samples[:10]}")
            logger.info(f"This likely means the buttons don't contain 'RD' or 'INSTANT' text. Episode being searched: {episode_id}")
        
        # Add a small delay to let the page stabilize after "Show More Results" clicks
        time.sleep(1)
        
        for i, availability_button_element in enumerate(valid_buttons_elements, start=1):
            try:
                # Re-locate the button to avoid stale element issues
                try:
                    button_text = availability_button_element.text.strip()
                except StaleElementReferenceException:
                    logger.info(f"Availability button {i} became stale, re-locating...")
                    # For now, we reuse relocate_red_buttons but it might need updating if it specifically looks for red
                    availability_button_element = relocate_red_buttons(driver, i)
                    if availability_button_element is None:
                        logger.warning(f"Could not re-locate availability button {i}. Skipping.")
                        continue
                    button_text = availability_button_element.text.strip()
                
                if "Report" in button_text:
                    logger.debug(f"Availability button {i} contains 'Report' - skipping")
                    continue
               
                # Double-check that this is actually an RD or Instant button (case-insensitive)
                bt_upper = button_text.upper()
                if "RD" not in bt_upper and "INSTANT" not in bt_upper:
                    logger.info(f"Button {i} does not look like an availability button - text: '{button_text}'. Skipping.")
                    continue
               
                logger.info(f"Checking availability button {i} with text: '{button_text}'...")
                try:
                    # Try to find the title element, with retry on stale reference
                    try:
                        logger.info(f"Attempting to find title element for availability button {i}...")
                        # Make XPath more robust: find ancestor that contains an h2, then find that h2
                        try:
                            availability_button_title_element = availability_button_element.find_element(By.XPATH, ".//ancestor::div[.//h2][1]//h2")
                        except NoSuchElementException:
                            # Fallback to the old specific one if the robust one fails for some reason
                            availability_button_title_element = availability_button_element.find_element(By.XPATH, ".//ancestor::div[contains(@class, 'border')]//h2")
                        
                        availability_button_title_text = availability_button_title_element.text.strip()
                        logger.info(f"Successfully found title for availability button {i}: '{availability_button_title_text}'")
                    except StaleElementReferenceException:
                        logger.info(f"Title element for availability button {i} became stale, re-locating...")
                        availability_button_element = relocate_red_buttons(driver, i)
                        if availability_button_element is None:
                            logger.warning(f"Could not re-locate availability button {i} for title extraction. Skipping.")
                            continue
                        # Use robust XPath here too
                        try:
                            availability_button_title_element = availability_button_element.find_element(By.XPATH, ".//ancestor::div[.//h2][1]//h2")
                        except NoSuchElementException:
                            availability_button_title_element = availability_button_element.find_element(By.XPATH, ".//ancestor::div[contains(@class, 'border')]//h2")
                        availability_button_title_text = availability_button_title_element.text.strip()
                    # Use original title first, clean it for comparison
                    availability_button_title_cleaned = clean_title(availability_button_title_text.split('(')[0].strip(), target_lang='en')
                    movie_title_cleaned = clean_title(movie_title.split('(')[0].strip(), target_lang='en')
                    # Extract year for comparison
                    availability_button_year = extract_year(availability_button_title_text, ignore_resolution=True)
                    expected_year = extract_year(movie_title)
                    logger.info(f"Availability button {i} title: {availability_button_title_cleaned}, Expected movie title: {movie_title_cleaned}")
                    
                    # Check if we've already processed this torrent
                    if availability_button_title_text in processed_torrents:
                        logger.info(f"Skipping availability button {i} - already processed torrent: {availability_button_title_text}")
                        continue
                    
                    # Fuzzy matching with a slightly lower threshold for robustness
                    title_match_ratio = fuzz.partial_ratio(availability_button_title_cleaned.lower(), movie_title_cleaned.lower())
                    title_match_threshold = 65  # Lowered from 69 to allow more flexibility
                    
                    # If initial match fails, try matching with original title (handles cases where extraction failed)
                    if title_match_ratio < title_match_threshold:
                        # Try matching original torrent title directly (fuzz.partial_ratio can find matches in longer strings)
                        original_match_ratio = fuzz.partial_ratio(
                            availability_button_title_text.lower(), 
                            movie_title.split('(')[0].strip().lower()
                        )
                        if original_match_ratio > title_match_ratio:
                            title_match_ratio = original_match_ratio
                            logger.info(f"Trying original title match - ratio improved to {title_match_ratio}%")
                    
                    title_matched = title_match_ratio >= title_match_threshold
                    # Year comparison (skip for TV shows or if missing)
                    year_matched = True
                    if not is_tv_show and expected_year:
                        if availability_button_year is None:
                            year_matched = False  # Card has no year; don't accept for movie with known year
                        else:
                            year_matched = abs(availability_button_year - expected_year) <= 1
                    # Episode and season matching (for TV shows)
                    season_matched = False
                    episode_matched = True
                    if is_tv_show and normalized_seasons:
                        # Use improved season matching that handles ranges like S01-04
                        from seerr.utils import match_single_season
                        for requested_season in normalized_seasons:
                            if match_single_season(availability_button_title_text, requested_season):
                                season_matched = True
                                logger.info(f"Season match found: {requested_season} matches torrent '{availability_button_title_text}'")
                                break
                        
                        if episode_id:
                            episode_matched = episode_id.lower() in availability_button_title_text.lower()
                            # Log episode matching details
                            if episode_id:
                                logger.info(f"Checking episode match for episode_id='{episode_id}' in title='{availability_button_title_text}': match={episode_matched}")
                            # If we're searching for a specific episode and it matches, we can auto-match the season
                            # since the filter already ensures season match (avoiding redundant checks)
                            if episode_matched and not season_matched:
                                # First, try to extract season from episode_id if it contains it (e.g., "S08E01")
                                if episode_id.startswith('S') and 'E' in episode_id:
                                    try:
                                        season_from_episode = int(episode_id[1:episode_id.index('E')])
                                        # Check if the title contains the same season
                                        if f"S{season_from_episode:02d}" in availability_button_title_text or f"Season {season_from_episode}" in availability_button_title_text:
                                            season_matched = True
                                            logger.info(f"Auto-matched season from episode_id: {episode_id}")
                                    except (ValueError, IndexError):
                                        pass
                                # If we have an episode match but no season match, auto-match the season
                                # The filter already narrowed results to the correct season, so if episode matches, season must too
                                if not season_matched:
                                    season_matched = True
                                    logger.info(f"Auto-matched season based on episode filter and episode match: episode_id={episode_id}")
                    
                    # Log matching details when searching for episodes
                    if episode_id:
                        logger.info(f"Availability button {i} matching details - Title: '{availability_button_title_text}', title_ratio: {title_match_ratio:.1f}%, title_match: {title_matched}, season_match: {season_matched}, episode_match: {episode_matched}")
                    
                    # --- NEW: Python-side Regex and Size filtering ---
                    if title_matched and year_matched and (not is_tv_show or (season_matched and episode_matched)):
                        # 0. System Junk Blacklist Check (Mandatory)
                        is_junk = False
                        for junk_pattern in SYSTEM_JUNK_BLACKLIST:
                            if re.search(junk_pattern, availability_button_title_text, re.IGNORECASE):
                                logger.info(f"Torrent '{availability_button_title_text}' rejected by MANDATORY system blacklist: {junk_pattern}")
                                is_junk = True
                                break
                        if is_junk:
                            continue

                        # 1. Regex Filter Check (Python-side / User defined)
                        if TORRENT_FILTER_REGEX:
                            try:
                                match = re.search(TORRENT_FILTER_REGEX, availability_button_title_text)
                                if not match:
                                    logger.info(f"Torrent '{availability_button_title_text}' rejected by User-side TORRENT_FILTER_REGEX: {TORRENT_FILTER_REGEX}")
                                    continue
                                else:
                                    logger.info(f"Torrent '{availability_button_title_text}' matched regex filter. Proceeding.")
                            except Exception as e:
                                logger.error(f"Invalid TORRENT_FILTER_REGEX: {e}")
                                # In case of regex error, we skip to be safe
                                continue
                        
                        # 2. Size Filter Check
                        try:
                            # Extract size from the result box text
                            # The box_element usually contains title, resolution, size, etc.
                            try:
                                box_element = availability_button_element.find_element(By.XPATH, ".//ancestor::div[.//h2][1]")
                            except NoSuchElementException:
                                box_element = availability_button_element.find_element(By.XPATH, ".//ancestor::div[contains(@class, 'border')]")
                            
                            box_text = box_element.text.strip()
                            
                            # Use our new parse_size utility
                            from seerr.utils import parse_size
                            torrent_size_gb = parse_size(box_text)
                            
                            if torrent_size_gb > 0:
                                max_allowed_gb = MAX_MOVIE_SIZE if not is_tv_show else MAX_EPISODE_SIZE
                                # If max_allowed_gb is 0, it means 'Biggest available' (unlimited)
                                if max_allowed_gb and max_allowed_gb > 0:
                                    if torrent_size_gb > max_allowed_gb:
                                        logger.info(f"Torrent '{availability_button_title_text}' rejected due to size: {torrent_size_gb:.2f} GB > {max_allowed_gb} GB")
                                        continue
                                    else:
                                        logger.info(f"Torrent '{availability_button_title_text}' size accepted: {torrent_size_gb:.2f} GB <= {max_allowed_gb} GB")
                            else:
                                logger.warning(f"Could not extract size for torrent: '{availability_button_title_text}' - continuing anyway")
                        except Exception as e:
                            logger.warning(f"Error during Python-side size filtering: {e}")
                        
                        # If we reached here, all Python-side filters passed
                        logger.info(f"Found a match on availability button {i} - {availability_button_title_cleaned} with RD/Instant RD. Clicking to add to Real-Debrid.")
                        
                        try:
                            # 1. Primary Click: The RD status button itself
                            logger.info(f"Attempting primary click on availability button for '{availability_button_title_text}'")
                            driver.execute_script("arguments[0].click();", availability_button_element)
                            time.sleep(2)
                            
                            # 2. Secondary Click: The Torrent Title (often opens a detail view with a more reliable Add button)
                            try:
                                logger.info(f"Clicking title '{availability_button_title_text}' to ensure detail view is open.")
                                driver.execute_script("arguments[0].click();", availability_button_title_element)
                                time.sleep(2)
                            except Exception as title_click_e:
                                logger.debug(f"Title click failed (might already be open): {title_click_e}")

                            # 3. Third Click: Look for explicit "Add" or "Real-Debrid" buttons in the newly opened/focused view
                            try:
                                logger.info("Searching for explicit 'Add to Library' or 'Real-Debrid' buttons...")
                                tertiary_selectors = [
                                    "//button[contains(., 'Add to Library')]",
                                    "//button[contains(., 'Real-Debrid')]",
                                    "//button[.//img[contains(@src, 'real-debrid')]]",
                                    "//a[contains(., 'Add to Library')]",
                                    "//a[contains(., 'Real-Debrid')]",
                                    "//a[.//img[contains(@src, 'real-debrid')]]"
                                ]
                                for sel in tertiary_selectors:
                                    btns = driver.find_elements(By.XPATH, sel)
                                    for b in btns:
                                        if b.is_displayed():
                                            logger.info(f"Found explicit addition button: '{b.text or 'icon button'}'. Clicking it.")
                                            driver.execute_script("arguments[0].click();", b)
                                            time.sleep(2)
                            except Exception as tert_e:
                                logger.debug(f"Tertiary button check failed: {tert_e}")

                            # 4. Fourth Click: Check for potential confirmation modals
                            try:
                                confirm_selectors = [
                                    "//button[contains(text(), 'Confirm')]",
                                    "//button[contains(text(), 'OK')]",
                                    "//button[contains(text(), 'Yes')]"
                                ]
                                for selector in confirm_selectors:
                                    confirms = driver.find_elements(By.XPATH, selector)
                                    for cb in confirms:
                                        if cb.is_displayed():
                                            logger.info(f"Found confirmation button: '{cb.text}'. Clicking it.")
                                            driver.execute_script("arguments[0].click();", cb)
                                            time.sleep(1)
                            except Exception as modal_e:
                                logger.debug(f"No confirmation modal found: {modal_e}")

                            logger.success(f"Successfully processed availability button for '{availability_button_title_text}'")
                        except Exception as e:
                            logger.error(f"Failed to complete media addition: {e}")
                        
                        confirmation_flag = True
                        # Add this torrent to processed set to avoid duplicate processing
                        processed_torrents.add(availability_button_title_text)
                        if is_tv_show and season_matched and not episode_id:
                            # Add the matched season to confirmed seasons
                            for requested_season in normalized_seasons:
                                if match_single_season(availability_button_title_text, requested_season):
                                    confirmed_seasons.add(requested_season)
                                    break
                        return confirmation_flag, confirmed_seasons  # Early exit on match
                    else:
                        logger.warning(f"No match for availability button {i}: Title - {availability_button_title_cleaned}, Year - {availability_button_year}, Episode - {episode_id}. Moving to next button.")
                except NoSuchElementException as e:
                    logger.warning(f"Could not find title associated with availability button {i}: {e}")
                    continue
            except StaleElementReferenceException as e:
                logger.warning(f"Stale element reference encountered for availability button {i}: {e}. Skipping this button.")
                continue
    except NoSuchElementException:
        logger.info("No buttons with 'RD (100%)' or 'Instant RD' detected. Proceeding with optional fallback.")
    return confirmation_flag, confirmed_seasons

def check_torrent_in_dmm_library(driver, search_phrase, library_wait_sec=8):
    """
    Check whether a torrent appears in DMM library by searching for the given phrase (case-insensitive).
    For TV use a phrase like "star trek starfleet academy S02E05" (normalized title + episode id).
    For movie use normalized title only, e.g. "perriers bounty".
    Navigates to library, optionally uses search input, then looks for the phrase in library content. Restores original URL.

    Returns:
        True if the phrase is found in the library, False otherwise or on error.
    """
    if driver is None:
        return False
    phrase = (search_phrase or "").strip() if isinstance(search_phrase, str) else str(search_phrase).strip()
    if not phrase:
        return False
    original_url = driver.current_url
    try:
        driver.get("https://debridmediamanager.com/library")
        try:
            WebDriverWait(driver, library_wait_sec).until(
                EC.presence_of_element_located((By.XPATH, "//div[@id='library-content']"))
            )
        except TimeoutException:
            logger.warning("Library page did not load in time during library check.")
            return False
        time.sleep(2)
        # Optional: if library has a search/filter input, use it to narrow results
        try:
            search_input = driver.find_element(By.CSS_SELECTOR, "input#query, input[placeholder*='earch' i], input[type='search']")
            search_input.clear()
            search_input.send_keys(phrase)
            time.sleep(2)
        except NoSuchElementException:
            pass
        # Look for the search phrase in library (case-insensitive)
        try:
            library_content = driver.find_element(By.ID, "library-content")
            library_text = library_content.text or ""
        except NoSuchElementException:
            library_text = driver.find_element(By.TAG_NAME, "body").text or ""
        found = phrase.lower() in library_text.lower()
        return found
    except Exception as e:
        logger.warning(f"Library check failed: {e}")
        return False
    finally:
        try:
            driver.get(original_url)
            time.sleep(1)
        except Exception as e:
            logger.warning(f"Failed to restore URL after library check: {e}")


def refresh_library_stats():
    """
    Refresh library statistics from the current page
    """
    global driver, library_stats
    
    if driver is None:
        logger.warning("Browser not initialized. Cannot refresh library stats.")
        return False
    
    # Check if it's safe to refresh library stats (queues not processing)
    try:
        from seerr.background_tasks import is_safe_to_refresh_library_stats
        if not is_safe_to_refresh_library_stats(min_idle_seconds=30):
            logger.info("Library refresh skipped - queues are active or recently active")
            return False
    except ImportError:
        # If background_tasks module is not available, proceed with caution
        logger.warning("Could not import background_tasks module. Proceeding with library refresh.")
    
    try:
        # Navigate to library page if we're not already there
        current_url = driver.current_url
        if "library" not in current_url:
            logger.info("Navigating to library page to refresh stats.")
            driver.get("https://debridmediamanager.com/library")
            time.sleep(7)  # Wait for page to load
        
        logger.info("Refreshing library statistics.")
        library_stats_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//h1[contains(@class, 'text-xl') and contains(@class, 'font-bold') and contains(@class, 'text-white') and contains(text(), 'Library')]"))
        )
        library_stats_text = library_stats_element.text.strip()
        logger.info(f"Found library stats text: {library_stats_text}")
        
        # Parse the text to extract torrent count and size
        import re
        from datetime import datetime
        
        # Extract torrent count
        torrent_match = re.search(r'(\d+)\s+torrents', library_stats_text)
        torrents_count = int(torrent_match.group(1)) if torrent_match else 0
        
        # Extract TB size
        size_match = re.search(r'([\d.]+)\s*TB', library_stats_text)
        total_size_tb = float(size_match.group(1)) if size_match else 0.0
        
        # Update global library stats
        library_stats = {
            "torrents_count": torrents_count,
            "total_size_tb": total_size_tb,
            "last_updated": datetime.now().isoformat()
        }
        
        # Save to database if enabled
        if USE_DATABASE:
            try:
                db = get_db()
                # Create new library stats entry
                new_stats = LibraryStats(
                    torrents_count=torrents_count,
                    total_size_tb=total_size_tb,
                    last_updated=datetime.now()
                )
                db.add(new_stats)
                db.commit()
                log_info("Library Stats", f"Saved to database: {torrents_count} torrents, {total_size_tb} TB")
            except Exception as e:
                log_error("Database Error", f"Failed to save library stats to database: {e}")
            finally:
                if 'db' in locals():
                    db.close()
        
        logger.info(f"Successfully refreshed library stats: {torrents_count} torrents, {total_size_tb} TB")
        return True
        
    except TimeoutException:
        logger.warning("Could not find library stats element on the page within timeout.")
        return False
    except Exception as e:
        logger.error(f"Error refreshing library stats: {e}")
        return False 
