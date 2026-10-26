import json
import sys
import os
from pathlib import Path

# Load .env if present (simple parser to avoid extra dependencies)
env_path = Path.cwd() / ".env"
if env_path.is_file():
    for line in env_path.read_text().splitlines():
        if line.strip() and not line.strip().startswith("#"):
            key, _, value = line.partition("=")
            os.environ[key.strip()] = value.strip()

from loguru import logger

CONFIG_DIR = Path.home() / ".skipera"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "cookies": {},
    "perplexity_api_key": "",
    "gemini_api_key": "",
    "groq_api_key": "",
    "perplexity_model": "sonar-pro",
    "gemini_model": "gemini-3.1-flash-lite",
    "groq_model": "openai/gpt-oss-120b"
}


def fetch_browser_cookies() -> dict:
    try:
        import browser_cookie3
    except ImportError:
        logger.error(
            "browser-cookie3 not installed. Run: pip install browser-cookie3")
        return {}

    browsers = [
        ("Chrome", browser_cookie3.chrome),
        ("Firefox", browser_cookie3.firefox),
        ("Edge", browser_cookie3.edge),
    ]

    needs_admin = False
    for name, browser_fn in browsers:
        try:
            cj = browser_fn(domain_name=".coursera.org")
            cookies = {}
            for c in cj:
                if c.name in cookies and cookies[c.name] and not c.value:
                    continue
                if c.name in cookies and cookies[c.name] and not c.domain.startswith('.'):
                    continue
                cookies[c.name] = c.value
            if cookies.get("CAUTH"):
                logger.success(f"Fetched Coursera cookies from {name}")
                return cookies
        except Exception as e:
            logger.warning(f"Failed fetching from {name}: {e}")
            if "requires admin" in str(e).lower():
                needs_admin = True
            continue

    if needs_admin and sys.platform == "win32":
        logger.info("Attempting to fetch cookies with elevated privileges (you may see a UAC prompt)...")
        import tempfile
        import subprocess
        import os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
            tmp_name = tmp.name
        
        script_path = tmp_name + ".py"
        with open(script_path, "w") as f:
            f.write("import sys, json, browser_cookie3\n")
            f.write("cookies = {}\n")
            f.write("for n, fn in [('Chrome', browser_cookie3.chrome), ('Firefox', browser_cookie3.firefox), ('Edge', browser_cookie3.edge)]:\n")
            f.write("    try:\n")
            f.write("        cj = fn(domain_name='.coursera.org')\n")
            f.write("        c = {}\n")
            f.write("        for x in cj:\n")
            f.write("            if x.name in c and c[x.name] and not x.value: continue\n")
            f.write("            if x.name in c and c[x.name] and not x.domain.startswith('.'): continue\n")
            f.write("            c[x.name] = x.value\n")
            f.write("        if c.get('CAUTH'):\n")
            f.write("            cookies = c\n")
            f.write("            break\n")
            f.write("    except Exception:\n")
            f.write("        pass\n")
            f.write("with open(sys.argv[1], 'w') as f:\n")
            f.write("    json.dump(cookies, f)\n")
            
        exec_path = sys.executable.replace('\\', '/')
        script_path_f = script_path.replace('\\', '/')
        tmp_name_f = tmp_name.replace('\\', '/')
        
        cmd = f'powershell -Command "Start-Process -FilePath \'{exec_path}\' -ArgumentList \'{script_path_f} {tmp_name_f}\' -Verb RunAs -Wait"'
        subprocess.run(cmd, shell=True)
        
        if os.path.exists(tmp_name):
            try:
                with open(tmp_name, "r") as f:
                    elevated_cookies = json.load(f)
                if "CAUTH" in elevated_cookies:
                    logger.success("Fetched Coursera cookies using elevated privileges!")
                    return elevated_cookies
            except Exception:
                pass
            finally:
                try: os.remove(tmp_name)
                except: pass
                try: os.remove(script_path)
                except: pass

    logger.warning(
        "Could not find Coursera cookies in any browser. Make sure you're logged into Coursera.")
    return {}


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2))

    config = json.loads(CONFIG_FILE.read_text())

    if not config.get("cookies") or not config.get("cookies", {}).get("CAUTH"):
        logger.info(
            "No valid CAUTH cookie in config -- attempting to fetch from browser...")
        cookies = fetch_browser_cookies()
        if cookies and cookies.get("CAUTH"):
            config["cookies"] = cookies
            CONFIG_FILE.write_text(json.dumps(config, indent=2))
            logger.info(f"Cookies saved to {CONFIG_FILE}")
        else:
            logger.error(
                f"No cookies found. Log into Coursera in your browser and retry, or manually edit {CONFIG_FILE}")
            sys.exit(1)

    return config


_config = load_config()

# URLs (constant, not user-configurable)
BASE_URL = "https://www.coursera.org/api/"
GRAPHQL_URL = "https://www.coursera.org/graphql-gateway"
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# User-configurable
COOKIES = _config["cookies"]
PERPLEXITY_API_KEY = _config.get("perplexity_api_key", "")
GEMINI_API_KEY = _config.get("gemini_api_key", "")
GROQ_API_KEY = _config.get("groq_api_key", "")

# Load additional Groq API keys from .env (comma-separated)
GROQ_API_KEYS = []
env_keys = os.getenv("GROQ_API_KEYS")
if env_keys:
    GROQ_API_KEYS = [k.strip() for k in env_keys.split(",") if k.strip()]
# Ensure primary key is included
if GROQ_API_KEY and GROQ_API_KEY not in GROQ_API_KEYS:
    GROQ_API_KEYS.insert(0, GROQ_API_KEY)
elif not GROQ_API_KEY and GROQ_API_KEYS:
    GROQ_API_KEY = GROQ_API_KEYS[0]
PERPLEXITY_MODEL = _config.get("perplexity_model", "sonar-pro")
GEMINI_MODEL = _config.get("gemini_model", "gemini-3.1-flash-lite")
GROQ_MODEL = _config.get("groq_model", "openai/gpt-oss-120b")
if GROQ_MODEL in ("llama-3.1-8b-instant", "llama-3.3-70b-versatile"):
    GROQ_MODEL = "openai/gpt-oss-120b" # auto-upgrade for deprecated models

HEADERS = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
    'x-coursera-application': 'ondemand',
    'x-coursera-version': '3bfd497de04ae0fef167b747fd85a6fbc8fb55df',
    'x-requested-with': 'XMLHttpRequest',
}
