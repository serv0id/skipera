import requests
import config
import loguru

class Skipera(object):
    def __init__(self):

response = requests.get(
    'https://www.coursera.org/api/onDemandCourseMaterials.v2/?q=slug&slug=introduction-psychology&includes=modules&showLockedItems=true',
    cookies=config.COOKIES,
    headers=config.HEADERS,
)
print(response.content)