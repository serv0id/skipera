# https://github.com/serv0id/skipera
import time

import requests
from loguru import logger

import config


class Watcher(object):
    def __init__(self, session: requests.Session, item: dict, metadata: dict, user_id: str, slug: str, course_id: str):
        self.metadata = metadata
        self.session = session
        self.item = item
        self.slug = slug
        self.user_id = user_id
        self.course_id = course_id

        self.session.headers.update({
            "x-csrf3-token": "1763560945.17ISLo0AGTOEp8HU"  # TODO: randomise?
        })

    def watch_item(self) -> None:
        if self.metadata["can_skip"]:
            logger.debug("Skippable video!")
            self.end_item()
        else:
            self.start_item()
            self.update_progress()
            self.end_item()

    def start_item(self):
        """
        Start watching a video item.
        """
        res = self.session.post(url=f'{config.BASE_URL}opencourse.v1/user/{self.user_id}/course/{self.slug}/'
                                    f'item/{self.item["id"]}/lecture/videoEvents/play?autoEnroll=false',
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
                                data='{"contentRequestBody":{}}')

        print(res.text)

        if "Completed" not in res.text:
            logger.error(f"Couldn't end watching {self.item['name']}")

    def update_progress(self):
        """
        Updates the watchtime progress of a video.
        """
        res = self.session.put(url=f'{config.BASE_URL}onDemandVideoProgresses.v1/{self.user_id}~{self.course_id}~'
                                   f'{self.metadata["tracking_id"]}',
                               json={
                                   "videoProgressId": f'{self.user_id}~{self.course_id}~{self.metadata["tracking_id"]}',
                                   "viewedUpTo": self.item["timeCommitment"]
                               })

        if res.status_code != 204:
            logger.error(f"Couldn't update progress for {self.item["name"]}")
        else:
            time.sleep(3)
