import requests, sys
import config
from loguru import logger

class Skipera(object):
    def __init__(self, course):
        self.base_url = config.BASE_URL
        self.session = requests.Session()
        self.session.headers.update(config.HEADERS)
        self.session.cookies.update(config.COOKIES)
        self.course = course
    
    def get_modules(self):
        r = self.session.get(self.base_url
         + f"onDemandCourseMaterials.v2/?q=slug&slug={self.course}&includes=modules").json()
        logger.info(r)

@logger.catch
def main():
    skipera = Skipera("introduction-psychology")
    skipera.get_modules()
if __name__ == '__main__':
    main()