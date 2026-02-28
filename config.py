BASE_URL = "https://www.coursera.org/api/"
GRAPHQL_URL = "https://www.coursera.org/graphql-gateway"

# AI-Specific
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_MODEL = "sonar-pro"  # adjust this according to your preference
GEMINI_MODEL = "gemini-3-flash-preview"

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

COOKIES = {}

# Credentials
PERPLEXITY_API_KEY = ""
GEMINI_API_KEY = ""
