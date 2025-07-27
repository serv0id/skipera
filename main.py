# https://github.com/serv0id/skipera

import requests
import sys
import config
from loguru import logger


class Skipera(object):
    def __init__(self, course):
        self.user_id = None
        self.course_id = None
        self.base_url = config.BASE_URL
        self.session = requests.Session()
        self.session.headers.update(config.HEADERS)
        self.session.cookies.update(config.COOKIES)
        self.course = course
        if not self.get_userid():
            self.login()  # implementation pending

    def login(self):
        logger.debug("Trying to log in using credentials")
        r = self.session.post(self.base_url + "login/v3", json={
            "code": "",
            "email": config.EMAIL,
            "password": config.PASSWORD,
            "webrequest": True,
        })

        logger.info(r.content)

    def get_userid(self):
        r = self.session.get(self.base_url + "adminUserPermissions.v1?q=my").json()
        try:
            self.user_id = r["elements"][0]["id"]
            logger.info("User ID: " + self.user_id)
        except KeyError:
            if r.get("errorCode"):
                logger.error("Error Encountered: " + r["errorCode"])
            return False
        return True

    # hierarchy - Modules > Lessons > Items
    def get_modules(self):
        r = self.session.get(self.base_url
                             + f"onDemandCourseMaterials.v2/?q=slug&slug={self.course}&includes=modules").json()
        self.course_id = r["elements"][0]["id"]
        logger.debug("Course ID: " + self.course_id)
        logger.debug("Number of Modules: " + str(len(r["linked"]["onDemandCourseMaterialModules.v1"])))
        for x in r["linked"]["onDemandCourseMaterialModules.v1"]:
            logger.info(x["name"] + " -- " + x["id"])

    def get_items(self):
        r = self.session.get(self.base_url + "onDemandCourseMaterials.v2/", params={
            "q": "slug",
            "slug": self.course,
            "includes": "passableItemGroups,passableItemGroupChoices,items,tracks,gradePolicy,gradingParameters",
            "fields": "onDemandCourseMaterialItems.v2(name,slug,timeCommitment,trackId)",
            "showLockedItems": "true"
        }).json()
        for video in r["linked"]["onDemandCourseMaterialItems.v2"]:
            logger.info("Watching " + video["name"])
            self.watch_item(video["id"])

    def watch_item(self, item_id):
        r = self.session.post(
            self.base_url + f"opencourse.v1/user/{self.user_id}/course/{self.course}/item/{item_id}/lecture"
                            f"/videoEvents/ended?autoEnroll=false",
            json={"contentRequestBody": {}}).json()
        if r.get("contentResponseBody") is None:
            logger.info("Not a watch item! Reading..")
            self.read_item(item_id)

    def read_item(self, item_id):
        r = self.session.post(self.base_url + "onDemandSupplementCompletions.v1", json={
            "courseId": self.course_id,
            "itemId": item_id,
            "userId": int(self.user_id)
        })
        if "Completed" not in r.text:
            logger.debug("Item is a quiz/assignment!")
            if "StaffGradedContent" in r.text:
                logger.debug("Attempting to solve graded assessment..")
                print(item_id)


@logger.catch
def main():
    if len(sys.argv) < 2:
        logger.error("Course slug not specified!")
        return

    skipera = Skipera(sys.argv[1])
    skipera.get_modules()
    skipera.get_items()


if __name__ == '__main__':
    main()
