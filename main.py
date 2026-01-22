import click
import requests
import config
from loguru import logger
from assessment.solver import GradedSolver
from watcher.watch import Watcher


class Skipera(object):
    def __init__(self, course: str, llm: bool):
        self.user_id = None
        self.course_id = None
        self.base_url = config.BASE_URL
        self.session = requests.Session()
        self.session.headers.update(config.HEADERS)
        self.session.cookies.update(config.COOKIES)
        self.course = course
        self.llm = llm
        if not self.get_userid():
            self.login()

    def login(self):
        raise NotImplementedError()  # implementation pending

    def get_userid(self) -> bool:
        r = self.session.get(self.base_url + "adminUserPermissions.v1?q=my").json()
        try:
            self.user_id = r["elements"][0]["id"]
            logger.info("User ID: " + self.user_id)
        except KeyError:
            if r.get("errorCode"):
                logger.error("Error Encountered: " + r["errorCode"])
            return False
        return True

    def get_course(self) -> None:
        r = self.session.get(self.base_url + f"onDemandCourseMaterials.v2/", params={
            "q": "slug",
            "slug": self.course,
            "includes": "modules,lessons,passableItemGroups,passableItemGroupChoices,passableLessonElements,items,"
                        "tracks,gradePolicy,gradingParameters,embeddedContentMapping",
            "fields": "moduleIds,onDemandCourseMaterialModules.v1(name,slug,description,timeCommitment,lessonIds,"
                      "optional,learningObjectives),onDemandCourseMaterialLessons.v1(name,slug,timeCommitment,"
                      "elementIds,optional,trackId),onDemandCourseMaterialPassableItemGroups.v1(requiredPassedCount,"
                      "passableItemGroupChoiceIds,trackId),onDemandCourseMaterialPassableItemGroupChoices.v1(name,"
                      "description,itemIds),onDemandCourseMaterialPassableLessonElements.v1(gradingWeight,"
                      "isRequiredForPassing),onDemandCourseMaterialItems.v2(name,originalName,slug,timeCommitment,"
                      "contentSummary,isLocked,lockableByItem,itemLockedReasonCode,trackId,lockedStatus,itemLockSummary,"
                      "customDisplayTypenameOverride),onDemandCourseMaterialTracks.v1(passablesCount),"
                      "onDemandGradingParameters.v1(gradedAssignmentGroups),"
                      "contentAtomRelations.v1(embeddedContentSourceCourseId,subContainerId)",
            "showLockedItems": True
        }).json()

        self.course_id = r["elements"][0]["id"]

        logger.info("Course ID: " + self.course_id)
        logger.info("Number of Modules: " + str(len(r["linked"]["onDemandCourseMaterialModules.v1"])))
        logger.debug("Processing items..")

        for item in r["linked"]["onDemandCourseMaterialItems.v2"]:
            if item["contentSummary"]["typeName"] == "lecture":
                logger.info(item["name"])
                self.watch_item(item, self.get_video_metadata(item["id"]))
            elif item["contentSummary"]["typeName"] == "supplement":
                self.read_item(item["id"])
            elif item["contentSummary"]["typeName"] == "ungradedAssignment":
                logger.info("Skipping ungraded assignment!")
            elif item["contentSummary"]["typeName"] == "staffGraded" and self.llm:
                logger.info("Attempting to solve graded assessment..")
                solver = GradedSolver(self.session, self.course_id, item["id"])
                solver.solve()

    def get_video_metadata(self, item_id: str) -> dict:
        r = self.session.get(self.base_url + f"onDemandLectureVideos.v1/{self.course_id}~{item_id}", params={
            "includes": "video",
            "fields": "disableSkippingForward,startMs,endMs"
        }).json()

        return {"can_skip": not r["elements"][0]["disableSkippingForward"],
                "tracking_id": r["linked"]["onDemandVideos.v1"][0]["id"]}

    def watch_item(self, item: dict, metadata: dict) -> None:
        watcher = Watcher(self.session, item, metadata, self.user_id, self.course, self.course_id)
        watcher.watch_item()

    def read_item(self, item_id) -> None:
        r = self.session.post(self.base_url + "onDemandSupplementCompletions.v1", json={
            "courseId": self.course_id,
            "itemId": item_id,
            "userId": int(self.user_id)
        })
        if "Completed" not in r.text:
            logger.debug("Couldn't read item!")


@logger.catch
@click.command()
@click.option('--slug', required=True, help="The course slug from the URL")
@click.option('--llm', is_flag=True, help="Whether to use an LLM to solve graded assignments.")
def main(slug: str, llm: bool) -> None:
    skipera = Skipera(slug, llm)
    skipera.get_course()


if __name__ == '__main__':
    main()
