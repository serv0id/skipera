import json
import sys
from pathlib import Path

from loguru import logger

CONFIG_DIR = Path.home() / ".skipera"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "cookies": {},
    "perplexity_api_key": "",
    "gemini_api_key": "",
    "perplexity_model": "sonar-pro",
    "gemini_model": "gemini-3-flash-preview"
}


def fetch_browser_cookies() -> dict:
    try:
        import browser_cookie3
    except ImportError:
        logger.error("browser-cookie3 not installed. Run: pip install browser-cookie3")
        return {}

    browsers = [
        ("Chrome", browser_cookie3.chrome),
        ("Firefox", browser_cookie3.firefox),
        ("Edge", browser_cookie3.edge),
    ]

    for name, browser_fn in browsers:
        try:
            cj = browser_fn(domain_name=".coursera.org")
            cookies = {c.name: c.value for c in cj}
            if "CAUTH" in cookies:
                logger.success(f"Fetched Coursera cookies from {name}")
                return cookies
        except Exception:
            continue

    logger.warning("Could not find Coursera cookies in any browser. Make sure you're logged into Coursera.")
    return {}


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2))

    config = json.loads(CONFIG_FILE.read_text())

    if not config.get("cookies"):
        logger.info("No cookies in config — attempting to fetch from browser...")
        cookies = fetch_browser_cookies()
        if cookies:
            config["cookies"] = cookies
            CONFIG_FILE.write_text(json.dumps(config, indent=2))
            logger.info(f"Cookies saved to {CONFIG_FILE}")
        else:
            logger.error(f"No cookies found. Log into Coursera in your browser and retry, or manually edit {CONFIG_FILE}")
            sys.exit(1)

    return config


_config = load_config()

# URLs (constant, not user-configurable)
BASE_URL = "https://www.coursera.org/api/"
GRAPHQL_URL = "https://www.coursera.org/graphql-gateway"
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

# User-configurable
COOKIES = _config["cookies"]
PERPLEXITY_API_KEY = _config.get("perplexity_api_key", "")
GEMINI_API_KEY = _config.get("gemini_api_key", "")
PERPLEXITY_MODEL = _config.get("perplexity_model", "sonar-pro")
GEMINI_MODEL = _config.get("gemini_model", "gemini-3-flash-preview")

SYSTEM_PROMPT = (
    "Answer the provided many questions."
    "Be precise and concise. The questions are in a dict format "
    "with the key representing the question id and the value a "
    "JSON dict containing several things. "
    "Questions may have single-choice or multiple-choice answers, "
    "which would be specified by the user in the JSON data. "
    "The question/option values might have HTML data but ignore that."
)

HEADERS = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
    'x-coursera-application': 'ondemand',
    'x-coursera-version': '3bfd497de04ae0fef167b747fd85a6fbc8fb55df',
    'x-requested-with': 'XMLHttpRequest',
}
