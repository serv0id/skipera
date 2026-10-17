import click
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
from .config import fetch_browser_cookies, CONFIG_FILE, DEFAULT_CONFIG, BASE_URL, HEADERS, COOKIES
import json
from loguru import logger
from .assessment.solver import GradedSolver
from .discussion.solver import DiscussionPromptSolver
from .coach.solver import CoachSolver
from .watcher.watch import Watcher
from .session_utils import get_csrf_headers, random_delay


class Skipera(object):
    def __init__(self, course: str, llm: bool):
        self.user_id = None
        self.course_id = None
        self.base_url = BASE_URL
        self.session = httpx.Client(timeout=60.0, follow_redirects=True, verify=False)
        self.session.headers.update(HEADERS)
        self.session.cookies.update(COOKIES)
        self.course = course
        self.llm = llm
        self.failed_items = set()
        if not self.get_userid():
            self.refresh_cookies()
            if not self.get_userid():
                logger.error(
                    "Cookies are invalid. Log into Coursera in your browser, close it, and retry.")
                raise SystemExit
        
        if self.llm:
            from .llm.connector import test_llm_setup
            test_llm_setup()


    def refresh_cookies(self):
        logger.warning("Session expired — re-fetching cookies from browser...")
        cookies = fetch_browser_cookies()
        if not cookies:
            return
        self.session.cookies.clear()
        self.session.cookies.update(cookies)
        cfg = json.loads(CONFIG_FILE.read_text()
                         ) if CONFIG_FILE.exists() else DEFAULT_CONFIG.copy()
        cfg["cookies"] = cookies
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

    def get_userid(self) -> bool:
        r = self.session.get(
            self.base_url + "adminUserPermissions.v1?q=my").json()
        try:
            self.user_id = r["elements"][0]["id"]
            logger.info("User ID: " + self.user_id)
        except KeyError:
            if r.get("errorCode"):
                logger.error("Error Encountered: " + r["errorCode"])
            return False
        return True

    def get_course(self) -> None:
        r = self.get_course_materials()
        self.course_id = r["elements"][0]["id"]
        all_items = r["linked"]["onDemandCourseMaterialItems.v2"]

        self.graded_assignment_groups = {}
        for param in r.get("linked", {}).get("onDemandGradingParameters.v1", []):
            self.graded_assignment_groups.update(param.get("gradedAssignmentGroups", {}))

        logger.info("Course ID: " + self.course_id)
        logger.info("Number of Modules: " +
                    str(len(r["linked"]["onDemandCourseMaterialModules.v1"])))
        logger.info("Total items: " + str(len(all_items)))

        self.process_items(all_items)

    def get_course_materials(self) -> dict:
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
        })

        if r.status_code != 200:
            logger.error("Please check if you are enrolled in the course!")
            raise SystemExit

        return r.json()

    def process_items(self, all_items: list[dict]) -> None:
        total = len(all_items)

        while True:
            completed = self.get_completed_items()

            try:
                fresh_data = self.get_course_materials()
                current_items = fresh_data["linked"]["onDemandCourseMaterialItems.v2"]
            except SystemExit:
                current_items = all_items

            pending_items = [item for item in current_items if item["id"] not in completed]
            if not pending_items:
                logger.info(f"Finished: {total}/{total} completed.")
                break

            unlocked_items = [
                item for item in pending_items 
                if not item.get("isLocked", False) and item["id"] not in self.failed_items
            ]
            if not unlocked_items:
                logger.info(
                    f"Finished: {total - len(pending_items)}/{total} completed, {len(pending_items)} still locked/pending."
                )
                break

            concurrent_items = []
            sequential_items = []
            for item in unlocked_items:
                if item["contentSummary"]["typeName"] not in {"discussionPrompt", "ungradedAssignment", "staffGraded", "phasedPeer"}:
                    concurrent_items.append(item)
                else:
                    sequential_items.append(item)

            if concurrent_items:
                with ThreadPoolExecutor(max_workers=min(6, len(concurrent_items))) as executor:
                    futures = {
                        executor.submit(self.process_item, item): item 
                        for item in concurrent_items
                    }
                    for future in as_completed(futures):
                        item = futures[future]
                        try:
                            success = future.result()
                            if not success:
                                self.failed_items.add(item["id"])
                        except Exception as e:
                            logger.exception(f"Error in processing item: {e}")
                            self.failed_items.add(item["id"])
                continue

            if sequential_items:
                item = sequential_items[0]
                try:
                    success = self.process_item(item)
                    if not success:
                        self.failed_items.add(item["id"])
                except Exception as e:
                    logger.exception(f"Error in processing item: {e}")
                    self.failed_items.add(item["id"])
                continue

    def process_item(self, item: dict) -> bool:
        item_type = item["contentSummary"]["typeName"]
        module_id = item.get('moduleId', 'unknown')
        item_id = item['id']
        logger.info(
            f"[module:{module_id}] [item:{item_id}] Processing {item['name']}")

        success = False
        if item_type == "lecture":
            success = self.watch_item(item, self.get_video_metadata(item_id))
        elif item_type == "supplement":
            success = self.read_item(item_id)
        elif item_type in {"ungradedAssignment", "staffGraded"} and self.llm:
            success = GradedSolver(
                self.session, self.course_id, item_id, slug=self.course).solve()
        elif item_type == "discussionPrompt" and self.llm:
            success = DiscussionPromptSolver(
                self.session, self.user_id, self.course_id, item_id).solve()
        elif item_type == "coach":
            success = CoachSolver(
                self.session, self.user_id, self.course_id, item_id).solve()
        elif item_type == "ungradedWidget":
            success = self.ungraded_widget_item(item_id)
        elif item_type == "ungradedLti":
            success = self.ungraded_lti_item(item_id)
        else:
            logger.warning(
                f"[module:{module_id}] [item:{item_id}] Unknown/skipped item type: {item_type} - skipping.")

        return success

    def get_completed_items(self) -> set[str]:
        r = self.session.get(
            self.base_url +
            f"onDemandCoursesProgress.v1/{self.user_id}~{self.course_id}",
            params={"fields": "gradedAssignmentGroupProgress"}
        )

        if r.status_code != 200:
            logger.debug("Could not fetch course progress.")
            logger.debug(r.text)
            return set()

        data = r.json()
        elements = data.get("elements") or []
        if not elements:
            logger.debug("Course progress response has no elements.")
            return set()

        items = elements[0].get("items", {})
        completed = {
            item_id
            for item_id, progress in items.items()
            if progress.get("progressState") == "Completed"
        }

        group_progress = elements[0].get("gradedAssignmentGroupProgress", {})
        for group_id, grp_prog in group_progress.items():
            grp_info = getattr(self, "graded_assignment_groups", {}).get(group_id, {})
            grp_items = grp_info.get("itemIds", [])
            num_required = grp_info.get("gradingType", {}).get("definition", {}).get("numberOfSelectedItems", 0)
            if grp_prog.get("state") == "Completed" or (num_required > 0 and len([i for i in grp_items if i in completed]) >= num_required):
                for alt_id in grp_items:
                    completed.add(alt_id)

        return completed

    def get_video_metadata(self, item_id: str) -> dict:
        r = self.session.get(self.base_url + f"onDemandLectureVideos.v1/{self.course_id}~{item_id}", params={
            "includes": "video",
            "fields": "disableSkippingForward,startMs,endMs"
        }).json()

        return {"can_skip": not r["elements"][0]["disableSkippingForward"],
                "tracking_id": r["linked"]["onDemandVideos.v1"][0]["id"]}

    def watch_item(self, item: dict, metadata: dict) -> bool:
        watcher = Watcher(self.session, item, metadata,
                          self.user_id, self.course, self.course_id)
        return watcher.watch_item()

    def read_item(self, item_id) -> bool:
        r = self.session.post(self.base_url + "onDemandSupplementCompletions.v1",
                              headers=get_csrf_headers(self.session),
                              json={
                                  "courseId": self.course_id,
                                  "itemId": item_id,
                                  "userId": int(self.user_id)
                              })
        return "Completed" in r.text

    def ungraded_widget_item(self, item_id) -> bool:
        r = self.session.get(
            self.base_url + f"onDemandWidgetSessions.v1/{self.user_id}~{self.course_id}~{item_id}",
            params={"fields": "session,sessionId"}
        )
        if r.status_code != 200:
            logger.error(f"Failed to get session for widget {item_id}: {r.status_code}")
            return False

        try:
            session_id = r.json()["elements"][0]["sessionId"]
        except (KeyError, IndexError):
            logger.error(f"Could not parse sessionId for widget {item_id}")
            return False

        res = self.session.put(
            self.base_url + f"onDemandWidgetProgress.v1/{self.user_id}~{self.course_id}~{item_id}",
            headers=get_csrf_headers(self.session),
            json={
                "sessionId": session_id,
                "progressState": "Completed"
            }
        )
        return 200 <= res.status_code < 300

    def ungraded_lti_item(self, item_id) -> bool:
        r = self.session.post(
            self.base_url + "rest/v1/lti/ungradedLaunches",
            headers=get_csrf_headers(self.session),
            json={
                "courseId": self.course_id,
                "itemId": item_id,
                "learnerId": int(self.user_id),
                "markItemCompleted": True
            }
        )
        return 200 <= r.status_code < 300


def list_enrolled_courses() -> None:
    from .config import fetch_browser_cookies, HEADERS
    import httpx
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    logger.info("Fetching enrolled courses...")
    cookies = fetch_browser_cookies()
    if not cookies:
        logger.error("Could not fetch cookies. Please log in to Coursera.")
        return
        
    client = httpx.Client(cookies=cookies, headers=HEADERS, follow_redirects=True, verify=False)
    url = "https://www.coursera.org/api/memberships.v1?includes=courseId,courses.v1&q=me&showHidden=true&filter=current"
    r = client.get(url)
    
    if r.status_code != 200:
        logger.error(f"Failed to fetch courses: {r.status_code}")
        return
        
    data = r.json()
    courses = data.get("linked", {}).get("courses.v1", [])
    elements = data.get("elements", [])
    user_id = elements[0].get("userId") if elements else None
    
    if not courses or not user_id:
        msg = "No enrolled courses found."
        logger.info(msg)
        with open("output.list", "w", encoding="utf-8") as f:
            f.write(msg + "\n")
        return
        
    def fetch_course_progress(c: dict) -> dict:
        course_id = c.get("id")
        slug = c.get("slug")
        name = c.get("name")
        
        # Get completed items
        prog_url = f"https://www.coursera.org/api/onDemandCoursesProgress.v1/{user_id}~{course_id}?fields=gradedAssignmentGroupProgress"
        pr = client.get(prog_url)
        completed = 0
        pelements = []
        completed_set = set()
        if pr.status_code == 200:
            pelements = pr.json().get("elements", [])
            if pelements:
                items = pelements[0].get("items", {})
                completed_set = {
                    item_id
                    for item_id, progress in items.items()
                    if progress.get("progressState") == "Completed"
                }
                
        # Get total items and grading parameters
        mat_url = f"https://www.coursera.org/api/onDemandCourseMaterials.v2/?q=slug&slug={slug}&includes=items,gradingParameters&fields=onDemandGradingParameters.v1(gradedAssignmentGroups)"
        mr = client.get(mat_url)
        total = "?"
        if mr.status_code == 200:
            mdata = mr.json()
            total = len(mdata.get("linked", {}).get("onDemandCourseMaterialItems.v2", []))
            if pelements and total != "?":
                group_progress = pelements[0].get("gradedAssignmentGroupProgress", {})
                grp_params = {}
                for param in mdata.get("linked", {}).get("onDemandGradingParameters.v1", []):
                    grp_params.update(param.get("gradedAssignmentGroups", {}))
                for group_id, grp_prog in group_progress.items():
                    grp_info = grp_params.get(group_id, {})
                    grp_items = grp_info.get("itemIds", [])
                    num_required = grp_info.get("gradingType", {}).get("definition", {}).get("numberOfSelectedItems", 0)
                    if grp_prog.get("state") == "Completed" or (num_required > 0 and len([i for i in grp_items if i in completed_set]) >= num_required):
                        for alt_id in grp_items:
                            completed_set.add(alt_id)
                modules = pelements[0].get("modules", {})
                if modules and all(score >= 100 for score in modules.values()):
                    completed = total
                else:
                    completed = len(completed_set)
        elif pelements:
            completed = len(completed_set)

        return {
            "name": name,
            "slug": slug,
            "completed": completed,
            "total": total
        }

    logger.info(f"Calculating progress for {len(courses)} courses (this may take a few seconds)...")
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_course_progress, c): c for c in courses}
        for future in as_completed(futures):
            results.append(future.result())
            
    output_lines = [
        "=" * 60,
        " ENROLLED COURSES ".center(60, "="),
        "=" * 60,
    ]
    
    for res in results:
        percentage = f"{(res['completed'] / int(res['total']) * 100):.1f}%" if str(res['total']).isdigit() and res['total'] > 0 else "N/A"
        output_lines.append(f"Title    : {res['name']}")
        output_lines.append(f"Slug     : {res['slug']}")
        output_lines.append(f"Progress : {res['completed']} / {res['total']} completed ({percentage})")
        output_lines.append(f"Command  : python -m skipera.main {res['slug']} --llm")
        output_lines.append(f"UV Cmd   : uv run skipera {res['slug']} --llm")
        output_lines.append("-" * 60)
    
    output_text = "\n".join(output_lines)
    print("\n" + output_text + "\n")

    with open("output.list", "w", encoding="utf-8") as f:
        f.write(output_text + "\n")
    logger.info("Saved enrolled courses to output.list")


@logger.catch
@click.command()
@click.argument('slug', required=False)
@click.option('--llm', is_flag=True, help="Whether to use an LLM to solve graded assignments.")
@click.option('--list', 'list_courses_flag', is_flag=True, help="List enrolled courses and their slugs.")
def main(slug: str | None, llm: bool, list_courses_flag: bool) -> None:
    if list_courses_flag:
        list_enrolled_courses()
        return
        
    if not slug:
        import sys
        logger.error("Missing argument 'SLUG'.")
        sys.exit(1)
        
    skipera = Skipera(slug, llm)
    skipera.get_course()

if __name__ == '__main__':
    main()
