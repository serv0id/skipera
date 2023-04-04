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
            self.watch_module(video["id"])

    def watch_module(self, item_id):
        r = self.session.post(self.base_url + f"opencourse.v1/user/{self.user_id}/course/{self.course}/item/{item_id}/lecture/videoEvents/ended?autoEnroll=false",
            data='{"contentRequestBody":{}}', headers={
                "x-crsf3-token": "1681448905.ModvqewqnjdnpSs4",
                "x-csrf2-cookie": "csrf2_token_jj1kc9gp",
                "x-csrf2-token": "CfRRROCd2dDv1JB6NIRbOt2u",
                "x-csrftoken": "iuLzOHq0YfOxe23GujMzVSes"
            })
        print(r.request.url)
        logger.info(r.content)

@logger.catch
def main():
    skipera = Skipera(sys.argv[1])
    skipera.get_modules()
    skipera.get_items()
if __name__ == '__main__':
    main()