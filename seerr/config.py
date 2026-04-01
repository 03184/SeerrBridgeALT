"""
Configuration module for SeerrBridge
Loads configuration from .env file
"""
import os
import sys
import json
import time
from typing import Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv
from loguru import logger

# Configure loguru
logger.remove()  # Remove default handler

# Add file logger only if directory exists and is writable
log_file = "logs/seerrbridge.log"
if os.path.exists(os.path.dirname(log_file)):
    try:
        # Try to create/open the log file to check permissions
        open(log_file, 'a').close()
        logger.add(log_file, rotation="500 MB", encoding='utf-8')  # Use utf-8 encoding for log file
    except (PermissionError, OSError):
        # If we can't write to the file, skip file logging (database logging will be used instead)
        pass

logger.add(sys.stdout, colorize=True)  # Ensure stdout can handle Unicode
logger.level("WARNING", color="<cyan>")

# Initialize variables
RD_ACCESS_TOKEN = None
RD_REFRESH_TOKEN = None
RD_CLIENT_ID = None
RD_CLIENT_SECRET = None
OVERSEERR_BASE = None
OVERSEERR_API_BASE_URL = None
OVERSEERR_API_KEY = None
TRAKT_API_KEY = None
HEADLESS_MODE = True
ENABLE_AUTOMATIC_BACKGROUND_TASK = False
ENABLE_SHOW_SUBSCRIPTION_TASK = False
TORRENT_FILTER_REGEX = None
MAX_MOVIE_SIZE = None
MAX_EPISODE_SIZE = None
REFRESH_INTERVAL_MINUTES = 60.0
DISCREPANCY_REPO_FILE = "logs/episode_discrepancies.json"
SYSTEM_JUNK_BLACKLIST = [
    r'[a-z0-9]+\.[a-z]{2,5}',           # Broad URL detector (site.gs, site.pro, etc.)
    r'Tam|Tel|Hin|Kan|Mal|Multi|Dual|Рус|Ukr', # Non-English/Multi tags
    r'HDRip|CAM|HDCAM|TS|TC|SCR|DVDScr',       # Low quality sources
    r'【.*?】|\[esp\]'                          # Specific junk tags
]

# Database configuration
DB_HOST = None
DB_PORT = None
DB_NAME = None
DB_USER = None
DB_PASSWORD = None
USE_DATABASE = True

# Add a global variable to track start time
START_TIME = datetime.now()

def validate_size_values(movie_size, episode_size):
    """Validate movie and episode size values against available options"""
    # Valid movie size values based on DMM settings page
    valid_movie_sizes = [0, 1, 3, 5, 15, 30, 60]
    # Valid episode size values based on DMM settings page  
    valid_episode_sizes = [0, 0.1, 0.3, 0.5, 0.8, 1, 3, 5]
    
    # Convert to appropriate types and validate
    try:
        if movie_size is not None:
            movie_size = float(movie_size)
            if movie_size not in valid_movie_sizes:
                logger.warning(f"Invalid movie size '{movie_size}'. Valid options: {valid_movie_sizes}. Using default (0).")
                movie_size = 0
    except (ValueError, TypeError):
        logger.warning(f"Invalid movie size format '{movie_size}'. Using default (0).")
        movie_size = 0
    
    try:
        if episode_size is not None:
            episode_size = float(episode_size)
            if episode_size not in valid_episode_sizes:
                logger.warning(f"Invalid episode size '{episode_size}'. Valid options: {valid_episode_sizes}. Using default (0).")
                episode_size = 0
    except (ValueError, TypeError):
        logger.warning(f"Invalid episode size format '{episode_size}'. Using default (0).")
        episode_size = 0
    
    return movie_size, episode_size

def load_config_from_env():
    """Load configuration from .env file"""
    global OVERSEERR_BASE, OVERSEERR_API_BASE_URL, HEADLESS_MODE, TORRENT_FILTER_REGEX, MAX_MOVIE_SIZE, MAX_EPISODE_SIZE
    
    try:
        # Load configuration from environment variables
        OVERSEERR_BASE = os.getenv('OVERSEERR_BASE', '')
        OVERSEERR_API_BASE_URL = OVERSEERR_BASE if OVERSEERR_BASE else None
        HEADLESS_MODE = os.getenv('HEADLESS_MODE', 'true').lower() == 'true'
        
        # exclusionary default regex that blocks URLs, multi-audio/non-English, and low quality
        # (?!.*[a-z0-9]+\.[a-z]{2,}) filters common URL patterns
        # (?!.*(Tamil|Telugu|Hindi|Kannada|Malayalam|RUS|FR|GER|ITA|SPA|Dual|Multi|Audio)) filters non-English/multi
        # (?!.*(HDRip|CAM|HDCAM|TS)) filters low quality
        # (?=.*(1080p|720p|WEB)) requires HD/WEB
        DEFAULT_REGEX = r'^(?!.*[a-z0-9]+\.[a-z]{2,})(?!.*[【】\u0400-\u04FF\[esp\]])(?!.*(Tamil|Telugu|Hindi|Kannada|Malayalam|RUS|FR|GER|ITA|SPA|Dual|Multi|Audio))(?!.*(HDRip|CAM|HDCAM|TS|2160p|4K|4k|UHD|uhd|480p|360p|SD|sd))(?=.*(1080p|720p)).*'
        TORRENT_FILTER_REGEX = os.getenv('TORRENT_FILTER_REGEX', DEFAULT_REGEX)
        
        if TORRENT_FILTER_REGEX:
            TORRENT_FILTER_REGEX = TORRENT_FILTER_REGEX.strip("'\"")
        
        logger.info("Configuration loaded from .env file successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to load configuration from .env: {e}")
        return False

def load_config(override=False):
    """Load configuration from .env file"""
    global RD_ACCESS_TOKEN, RD_REFRESH_TOKEN, RD_CLIENT_ID, RD_CLIENT_SECRET
    global OVERSEERR_BASE, OVERSEERR_API_BASE_URL, OVERSEERR_API_KEY, TRAKT_API_KEY
    global HEADLESS_MODE, ENABLE_AUTOMATIC_BACKGROUND_TASK, ENABLE_SHOW_SUBSCRIPTION_TASK
    global TORRENT_FILTER_REGEX, MAX_MOVIE_SIZE, MAX_EPISODE_SIZE, REFRESH_INTERVAL_MINUTES
    global DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, USE_DATABASE
    
    # Determine .env file path - use shared data directory in containers
    if os.path.exists('/app/data'):
        env_path = '/app/data/.env'
    else:
        env_path = '.env'
    
    # Load environment variables from .env file
    load_dotenv(dotenv_path=env_path, override=override, interpolate=False)
    
    # Load all configuration from environment variables
    RD_ACCESS_TOKEN = os.getenv('RD_ACCESS_TOKEN', '').strip("'\" ")
    RD_REFRESH_TOKEN = os.getenv('RD_REFRESH_TOKEN', '').strip("'\" ")
    RD_CLIENT_ID = os.getenv('RD_CLIENT_ID', '').strip("'\" ")
    RD_CLIENT_SECRET = os.getenv('RD_CLIENT_SECRET', '').strip("'\" ")
    OVERSEERR_BASE = os.getenv('OVERSEERR_BASE', '').strip("'\" ")
    OVERSEERR_API_BASE_URL = OVERSEERR_BASE if OVERSEERR_BASE else None
    OVERSEERR_API_KEY = os.getenv('OVERSEERR_API_KEY', '').strip("'\" ")
    TRAKT_API_KEY = os.getenv('TRAKT_API_KEY', '').strip("'\" ")
    HEADLESS_MODE = os.getenv("HEADLESS_MODE", "true").lower() == "true"
    ENABLE_AUTOMATIC_BACKGROUND_TASK = os.getenv("ENABLE_AUTOMATIC_BACKGROUND_TASK", "false").lower() == "true"
    ENABLE_SHOW_SUBSCRIPTION_TASK = os.getenv("ENABLE_SHOW_SUBSCRIPTION_TASK", "false").lower() == "true"
    TORRENT_FILTER_REGEX = os.getenv("TORRENT_FILTER_REGEX")
    
    # Clean quotes if they exist from .env loading
    if TORRENT_FILTER_REGEX:
        TORRENT_FILTER_REGEX = TORRENT_FILTER_REGEX.strip("'\"")
        
        import re as _re
        
        # Fix double-escaped backslashes (from dashboard config save)
        TWO_BACKSLASHES = chr(92) + chr(92)
        ONE_BACKSLASH = chr(92)
        if TWO_BACKSLASHES in TORRENT_FILTER_REGEX:
            TORRENT_FILTER_REGEX = TORRENT_FILTER_REGEX.replace(TWO_BACKSLASHES, ONE_BACKSLASH)
            logger.info("Fixed double-escaped backslashes in TORRENT_FILTER_REGEX")
        
        # Fix the broken character class pattern from the default/old regex.
        # The old pattern [【】\u0400-\u04FF\[esp\]] is broken in .env because:
        #   - \u0400 becomes literal chars \,u,0,4,0,0 (not Unicode Ѐ)
        #   - \[esp\] inside [...] matches individual chars including 'p'
        #   - 'p' matches '1080p' in EVERY title, rejecting everything
        # Replace with a safe alternation-based pattern.
        broken_patterns = [
            chr(92) + 'u0400-' + chr(92) + 'u04FF',  # literal \u0400-\u04FF
            chr(92) + '[esp' + chr(92) + ']',          # literal \[esp\]
        ]
        has_broken = any(bp in TORRENT_FILTER_REGEX for bp in broken_patterns)
        if has_broken:
            logger.warning("Detected broken Unicode/character-class pattern in regex. Rebuilding...")
            # Replace the entire broken character class with a working alternation
            # Find and replace [【】\u0400-\u04FF\[esp\]] or similar
            # Use a simple approach: just rebuild the regex from known-good components
            TORRENT_FILTER_REGEX = (
                r'^(?!.*(【|】|\[esp\]))'                                                  # Block CJK brackets and [esp] tags
                r'(?=.*(1080p|720p))'                                                       # Require HD resolution
                r'(?!.*(DUAL|MULTI|Multi\sAudio|Dual\sAudio|FRENCH|FR|GERMAN|GER'
                r'|ITALIAN|ITA|SPANISH|SPA|RUSSIAN|RUS|HINDI|TAMIL|TELUGU'
                r'|KANNADA|MALAYALAM|2160p|4K|4k|UHD|uhd|480p|360p|SD|sd'
                r'|remux|CAM|TS|HDRip))'                                                    # Block non-English, low quality, 4K
                r'(?=.*(MeGusta|Elite|NeoNoir|rarbg|PSA|YTS))'                              # Require approved release groups
                r'.*'
            )
            logger.info("Rebuilt regex with working pattern")
        
        # Validate the regex compiles and passes sanity checks
        try:
            compiled = _re.compile(TORRENT_FILTER_REGEX, _re.IGNORECASE)
            # Sanity tests
            test_pass = bool(compiled.search("Movie.2025.1080p.BluRay.x264-RARBG"))
            test_block_dual = not compiled.search("Movie.2025.1080p.DUAL.BluRay-RARBG")
            test_block_nogroup = not compiled.search("Movie.2025.1080p.BluRay-Nogroup")
            logger.info(f"TORRENT_FILTER_REGEX sanity: good_title={test_pass}, block_dual={test_block_dual}, block_nogroup={test_block_nogroup}")
            if not test_pass:
                logger.error("CRITICAL: Regex rejects known-good titles! Falling back to permissive regex.")
                # Fallback: only block multi-language, require HD, require release group
                TORRENT_FILTER_REGEX = (
                    r'^(?=.*(1080p|720p))'
                    r'(?!.*(DUAL|MULTI|FRENCH|FR|GERMAN|GER|ITALIAN|ITA|SPANISH|SPA|RUSSIAN|RUS))'
                    r'(?=.*(MeGusta|Elite|NeoNoir|rarbg|PSA|YTS))'
                    r'.*'
                )
                logger.info("Using fallback regex")
            logger.info(f"  Final regex: {TORRENT_FILTER_REGEX[:120]}...")
        except _re.error as e:
            logger.error(f"TORRENT_FILTER_REGEX is invalid and will be IGNORED: {e}")
            TORRENT_FILTER_REGEX = None
    
    
    # Load and validate size values
    raw_movie_size = os.getenv("MAX_MOVIE_SIZE")
    raw_episode_size = os.getenv("MAX_EPISODE_SIZE")
    MAX_MOVIE_SIZE, MAX_EPISODE_SIZE = validate_size_values(raw_movie_size, raw_episode_size)
    
    # Database configuration
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_NAME = os.getenv("DB_NAME", "seerrbridge")
    DB_USER = os.getenv("DB_USER", "seerrbridge")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "seerrbridge")
    USE_DATABASE = os.getenv("USE_DATABASE", "true").lower() == "true"
    
    # Load refresh interval from environment variable
    try:
        REFRESH_INTERVAL_MINUTES = float(os.getenv("REFRESH_INTERVAL_MINUTES", "60"))
        min_interval = 1.0  # Minimum interval in minutes
        if REFRESH_INTERVAL_MINUTES < min_interval:
            logger.warning(f"REFRESH_INTERVAL_MINUTES ({REFRESH_INTERVAL_MINUTES}) is too small. Setting to minimum interval of {min_interval} minutes.")
            REFRESH_INTERVAL_MINUTES = min_interval
    except (TypeError, ValueError):
        logger.warning(f"REFRESH_INTERVAL_MINUTES environment variable is not a valid number. Using default of 60 minutes.")
        REFRESH_INTERVAL_MINUTES = 60.0
    
    logger.info("Configuration loaded from .env file")
    
    # Validate required configuration
    if not OVERSEERR_API_BASE_URL:
        logger.error("OVERSEERR_API_BASE_URL environment variable is not set.")
        return False
    
    if not OVERSEERR_API_KEY:
        logger.error("OVERSEERR_API_KEY environment variable is not set.")
        return False
    
    if not TRAKT_API_KEY:
        logger.error("TRAKT_API_KEY environment variable is not set.")
        return False
    
    return True

# Initialize configuration - use override=True so .env file wins over Docker/env vars at startup
load_config(override=True)

def update_env_file():
    """Update the .env file with the new access token."""
    try:
        # Determine .env file path - use shared data directory in containers
        if os.path.exists('/app/data'):
            env_path = '/app/data/.env'
        else:
            env_path = '.env'
        
        with open(env_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
        
        with open(env_path, 'w', encoding='utf-8') as file:
            for line in lines:
                if line.startswith('RD_ACCESS_TOKEN'):
                    file.write(f'RD_ACCESS_TOKEN={RD_ACCESS_TOKEN}\n')
                else:
                    file.write(line)
        return True
    except Exception as e:
        logger.error(f"Error updating .env file: {e}")
        return False 