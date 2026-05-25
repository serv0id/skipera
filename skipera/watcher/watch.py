# https://github.com/serv0id/skipera
import requests
from loguru import logger
from .. import config
from ..session_utils import get_csrf_headers, random_delay


class Watcher(object):
    def __init__(self, session: requests.Session, item: dict, metadata: dict, user_id: str, slug: str, course_id: str):
        self.metadata = metadata
        self.session = session
        self.item = item
        self.slug = slug
        self.user_id = user_id
        self.course_id = course_id

    def watch_item(self) -> bool:
        if self.metadata["can_skip"]:
            logger.debug("Skippable video!")
            self.end_item()
        else:
            self.start_item()
            self.update_progress()
            self.end_item()
        return True

    def start_item(self):
        """
        Start watching a video item.
        """
        res = self.session.post(url=f'{config.BASE_URL}opencourse.v1/user/{self.user_id}/course/{self.slug}/'
                                f'item/{self.item["id"]}/lecture/videoEvents/play?autoEnroll=false',
                                headers=get_csrf_headers(self.session),
                                data='{"contentRequestBody":{}}')

        if res.status_code != 200:
            logger.error(f"Couldn't start video {self.item['name']}!")

    def end_item(self):
        """
        End watching a video item.
        Can be called directly for a skippable video.
        """
        res = self.session.post(url=f'{config.BASE_URL}opencourse.v1/user/{self.user_id}/course/{self.slug}/'
                                f'item/{self.item["id"]}/lecture/videoEvents/ended?autoEnroll=false',
                                headers=get_csrf_headers(self.session),
                                data='{"contentRequestBody":{}}')

        if res.status_code != 200:
            logger.error(f"Couldn't end watching {self.item['name']}")

    def update_progress(self):
        """
        Updates the watchtime progress of a video.
        """
        res = self.session.put(url=f'{config.BASE_URL}onDemandVideoProgresses.v1/{self.user_id}~{self.course_id}~'
                               f'{self.metadata["tracking_id"]}',
                               headers=get_csrf_headers(self.session),
                               json={
                                   "videoProgressId": f'{self.user_id}~{self.course_id}~{self.metadata["tracking_id"]}',
                                   "viewedUpTo": self.item["timeCommitment"] + 2000
        })

        if res.status_code != 204:
            logger.error(f"Couldn't update progress for {self.item['name']}")
        else:
            random_delay(1.0, 3.0)
