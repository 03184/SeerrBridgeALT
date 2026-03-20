"""
Task Configuration Manager for SeerrBridge
Handles reading and updating task configuration from the database
"""
import json
import os
from typing import Any, Dict, Optional, Union
from datetime import datetime
from sqlalchemy.orm import Session
from seerr.database import get_db, SystemConfig
from seerr.db_logger import log_info, log_error, log_debug

# Config keys that can be set from .env. On startup, any value set in .env is pushed to DB (one-way: .env → DB).
CONFIG_KEY_TO_ENV = {
    'background_tasks_enabled': 'BACKGROUND_TASKS_ENABLED',
    'scheduler_enabled': 'SCHEDULER_ENABLED',
    'enable_automatic_background_task': 'ENABLE_AUTOMATIC_BACKGROUND_TASK',
    'enable_show_subscription_task': 'ENABLE_SHOW_SUBSCRIPTION_TASK',
    'refresh_interval_minutes': 'REFRESH_INTERVAL_MINUTES',
    'headless_mode': 'HEADLESS_MODE',
    'torrent_filter_regex': 'TORRENT_FILTER_REGEX',
    'max_movie_size': 'MAX_MOVIE_SIZE',
    'max_episode_size': 'MAX_EPISODE_SIZE',
    'token_refresh_interval_minutes': 'TOKEN_REFRESH_INTERVAL_MINUTES',
    'movie_processing_check_interval_minutes': 'MOVIE_PROCESSING_CHECK_INTERVAL_MINUTES',
    'subscription_check_interval_minutes': 'SUBSCRIPTION_CHECK_INTERVAL_MINUTES',
    'movie_queue_maxsize': 'MOVIE_QUEUE_MAXSIZE',
    'tv_queue_maxsize': 'TV_QUEUE_MAXSIZE',
    'enable_failed_item_retry': 'ENABLE_FAILED_ITEM_RETRY',
    'failed_item_retry_interval_minutes': 'FAILED_ITEM_RETRY_INTERVAL_MINUTES',
    'failed_item_retry_delay_hours': 'FAILED_ITEM_RETRY_DELAY_HOURS',
    'failed_item_retry_backoff_multiplier': 'FAILED_ITEM_RETRY_BACKOFF_MULTIPLIER',
    'failed_item_max_retry_delay_hours': 'FAILED_ITEM_MAX_RETRY_DELAY_HOURS',
}


class TaskConfigManager:
    """Manages task configuration stored in the database"""
    
    def __init__(self):
        self._cache = {}
        self._cache_timestamp = None
        self._cache_ttl = 30  # Cache for 30 seconds
    
    def _is_cache_valid(self) -> bool:
        """Check if the cache is still valid"""
        if not self._cache_timestamp:
            return False
        return (datetime.utcnow() - self._cache_timestamp).total_seconds() < self._cache_ttl
    
    def _load_config_from_db(self) -> Dict[str, Any]:
        """Load all task configuration from database"""
        db = get_db()
        try:
            configs = db.query(SystemConfig).filter(
                SystemConfig.is_active == True
            ).all()
            
            config_dict = {}
            for config in configs:
                # Convert value based on type
                value = self._convert_config_value(config.config_value, config.config_type)
                config_dict[config.config_key] = value
            
            return config_dict
        except Exception as e:
            log_error("Config Error", f"Error loading configuration from database: {e}", 
                     module="task_config_manager", function="_load_config_from_db")
            return {}
        finally:
            db.close()
    
    def _convert_config_value(self, value: str, config_type: str) -> Any:
        """Convert string value to appropriate type"""
        if value is None:
            return None
        
        # Normalize type aliases: 'integer' -> 'int', 'boolean' -> 'bool'
        normalized_type = config_type.lower()
        if normalized_type == 'integer':
            normalized_type = 'int'
        elif normalized_type == 'boolean':
            normalized_type = 'bool'
            
        try:
            if normalized_type == 'bool':
                return value.lower() in ('true', '1', 'yes', 'on')
            elif normalized_type == 'int':
                # Handle float values that should be int
                if '.' in str(value):
                    return int(float(value))
                return int(value)
            elif normalized_type == 'float':
                return float(value)
            elif normalized_type == 'json':
                return json.loads(value)
            else:  # string
                return value
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            log_error("Config Error", f"Error converting config value '{value}' to type '{config_type}': {e}",
                     module="task_config_manager", function="_convert_config_value")
            return value
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key"""
        # Check cache first
        if self._is_cache_valid() and key in self._cache:
            return self._cache[key]
        
        # Load from database if cache is invalid
        if not self._is_cache_valid():
            self._cache = self._load_config_from_db()
            self._cache_timestamp = datetime.utcnow()
        
        return self._cache.get(key, default)
    
    def set_config(self, key: str, value: Any, config_type: str = 'string', description: str = None) -> bool:
        """Set a configuration value"""
        try:
            db = get_db()
            
            # Convert value to string for storage
            if config_type == 'json':
                str_value = json.dumps(value)
            else:
                str_value = str(value)
            
            # Check if config exists
            existing_config = db.query(SystemConfig).filter(
                SystemConfig.config_key == key
            ).first()
            
            if existing_config:
                # Update existing
                existing_config.config_value = str_value
                existing_config.config_type = config_type
                if description:
                    existing_config.description = description
                existing_config.updated_at = datetime.utcnow()
            else:
                # Create new
                new_config = SystemConfig(
                    config_key=key,
                    config_value=str_value,
                    config_type=config_type,
                    description=description or f"Configuration for {key}",
                    is_active=True
                )
                db.add(new_config)
            
            db.commit()
            
            # Update cache
            self._cache[key] = value
            if not self._cache_timestamp:
                self._cache_timestamp = datetime.utcnow()
            
            log_info("Config Update", f"Updated configuration: {key} = {value}", 
                    module="task_config_manager", function="set_config")
            return True
            
        except Exception as e:
            log_error("Config Error", f"Error setting configuration {key}: {e}", 
                     module="task_config_manager", function="set_config")
            return False
        finally:
            db.close()
    
    def get_all_task_configs(self) -> Dict[str, Any]:
        """Get all task-related configurations"""
        if not self._is_cache_valid():
            self._cache = self._load_config_from_db()
            self._cache_timestamp = datetime.utcnow()
        
        # Filter for task-related configs
        task_configs = {}
        task_keys = [
            'enable_automatic_background_task',
            'enable_show_subscription_task', 
            'refresh_interval_minutes',
            'movie_queue_maxsize',
            'tv_queue_maxsize',
            'token_refresh_interval_minutes',
            'movie_processing_check_interval_minutes',
            'library_refresh_interval_minutes',
            'subscription_check_interval_minutes',
            'background_tasks_enabled',
            'queue_processing_enabled',
            'scheduler_enabled',
            'overseerr_base',
            'headless_mode',
            'torrent_filter_regex',
            'max_movie_size',
            'max_episode_size'
        ]
        
        for key in task_keys:
            if key in self._cache:
                task_configs[key] = self._cache[key]
        
        return task_configs
    
    def invalidate_cache(self):
        """Invalidate the configuration cache"""
        self._cache = {}
        self._cache_timestamp = None
        log_debug("Config Cache", "Configuration cache invalidated", 
                 module="task_config_manager", function="invalidate_cache")


# Global instance
task_config = TaskConfigManager()


def sync_env_to_db() -> int:
    """
    One-way sync: .env → database. For each config key that has an env var set in .env,
    update system_config so the DB matches .env. Does not modify .env.
    Returns the number of keys updated.
    """
    from seerr.config import USE_DATABASE
    if not USE_DATABASE:
        return 0
    from seerr.config import load_config
    load_config(override=True)
    updated = 0
    for config_key, env_key in CONFIG_KEY_TO_ENV.items():
        value = os.getenv(env_key)
        if value is None or value == '':
            continue
        value = value.strip()
        if value.lower() in ('true', 'false'):
            config_type = 'bool'
            py_value = value.lower() == 'true'
        elif value.replace('.', '', 1).isdigit():
            config_type = 'float' if '.' in value else 'int'
            py_value = float(value) if '.' in value else int(value)
        else:
            config_type = 'string'
            py_value = value
        if task_config.set_config(config_key, py_value, config_type):
            updated += 1
    if updated:
        log_info("Config Sync", f"Synced {updated} setting(s) from .env to database", 
                 module="task_config_manager", function="sync_env_to_db")
    return updated
