import httpx
from loguru import logger
from .. import config
from ..session_utils import get_csrf_headers, random_delay


class Watcher(object):
    def __init__(self, session: httpx.Client, item: dict, metadata: dict, user_id: str, slug: str, course_id: str):
        self.metadata = metadata
        self.session = session
        self.item = item
        self.slug = slug
        self.user_id = user_id
        self.course_id = course_id

    def watch_item(self) -> bool:
        if self.metadata.get("can_skip"):
            logger.debug("Skippable video!")
            return self.end_item()
        else:
            self.start_item()
            progress_ok = self.update_progress()
            end_ok = self.end_item()
            return progress_ok or end_ok

    def start_item(self) -> bool:
        """
        Start watching a video item.
        """
        res = self.session.post(url=f'{config.BASE_URL}opencourse.v1/user/{self.user_id}/course/{self.slug}/'
                                f'item/{self.item["id"]}/lecture/videoEvents/play?autoEnroll=false',
                                headers=get_csrf_headers(self.session),
                                data='{"contentRequestBody":{}}')

        if res.status_code != 200:
            logger.error(f"Couldn't start video {self.item['name']}: {res.status_code}")
            return False
        return True

    def end_item(self) -> bool:
        """
        End watching a video item.
        Can be called directly for a skippable video.
        """
        res = self.session.post(url=f'{config.BASE_URL}opencourse.v1/user/{self.user_id}/course/{self.slug}/'
                                f'item/{self.item["id"]}/lecture/videoEvents/ended?autoEnroll=false',
                                headers=get_csrf_headers(self.session),
                                data='{"contentRequestBody":{}}')

        if res.status_code != 200:
            logger.error(f"Couldn't end watching {self.item['name']}: {res.status_code}")
            return False
        return True

    def update_progress(self) -> bool:
        """
        Updates the watchtime progress of a video.
        """
        tracking_id = self.metadata.get("tracking_id")
        if not tracking_id:
            return False

        res = self.session.put(url=f'{config.BASE_URL}onDemandVideoProgresses.v1/{self.user_id}~{self.course_id}~'
                               f'{tracking_id}',
                               headers=get_csrf_headers(self.session),
                               json={
                                   "videoProgressId": f'{self.user_id}~{self.course_id}~{tracking_id}',
                                   "viewedUpTo": self.item["timeCommitment"] + 2000
        })

        if res.status_code != 204:
            logger.error(f"Couldn't update progress for {self.item['name']}: {res.status_code}")
            return False
        else:
            random_delay(1.0, 3.0)
            return True
