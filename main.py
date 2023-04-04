import requests, sys
import config
from loguru import logger
import click

class Skipera(object):
    def __init__(self, course):
        self.base_url = config.BASE_URL
        self.session = requests.Session()
        self.session.headers.update(config.HEADERS)
        self.session.cookies.update(config.COOKIES)
        self.course = course
        self.get_userid()

    def get_userid(self):
        r = self.session.get(self.base_url + "adminUserPermissions.v1?q=my").json()
        self.user_id = r["elements"][0]["id"]
        logger.info("User ID: " + self.user_id)


    def get_modules(self):
        r = self.session.get(self.base_url
         + f"onDemandCourseMaterials.v2/?q=slug&slug={self.course}&includes=modules").json()
        self.course_id = r["elements"][0]["id"]
        logger.debug("Course ID: " + self.course_id)
        logger.debug("Number of Modules: " + str(len(r["linked"]["onDemandCourseMaterialModules.v1"])))
        for x in r["linked"]["onDemandCourseMaterialModules.v1"]:
            logger.info(x["name"] + " -- " + x["id"])

    def watch_module(self, lesson_id):
        r = self.session.post(self.base_url + f"opencourse.v1/user/{self.user_id}/course/{self.course}/item/0Wmh7/lecture/videoEvents/ended?autoEnroll=false")

@logger.catch
def main():
    skipera = Skipera(sys.argv[1])
    skipera.get_modules()
if __name__ == '__main__':
    main()