import time
import httpx
from loguru import logger
from .. import config
from ..session_utils import get_csrf_headers


class CoachSolver(object):
    def __init__(self, session: httpx.Client, user_id: str, course_id: str, item_id: str):
        self.session = session
        self.user_id = user_id
        self.course_id = course_id
        self.item_id = item_id

    def solve(self) -> bool:
        r = self.session.get(
            config.BASE_URL + "onDemandSessionMemberships.v1/",
            params={
                "q": "activeByUserAndCourse",
                "userId": self.user_id,
                "courseId": self.course_id,
                "includes": "sessions",
                "fields": "onDemandSessions.v1(branchId)"
            }
        )
        if r.status_code != 200:
            logger.error(f"Failed to fetch session memberships: {r.status_code}")
            return False

        try:
            data = r.json()
            sessions = data.get("linked", {}).get("onDemandSessions.v1", [])
            if not sessions:
                logger.error("No active session found for the course.")
                return False
            branch_id = sessions[0].get("branchId")
            if not branch_id:
                logger.error("No branchId found in the session.")
                return False
        except Exception as e:
            logger.exception(f"Error parsing session memberships: {e}")
            return False

        params = {
            'opname': 'UpdateCoachItemProgress',
        }
        json_data = [
            {
                'operationName': 'UpdateCoachItemProgress',
                'variables': {
                    'courseId': self.course_id,
                    'branchId': branch_id,
                    'itemId': self.item_id,
                    'progressState': 'COMPLETED',
                },
                'query': 'mutation UpdateCoachItemProgress($courseId: ID!, $branchId: ID!, $itemId: ID!, $progressState: CoachItem_ProgressState!) {\n  CoachItemProgress_UpdateCoachItemProgress(\n    input: {courseId: $courseId, branchId: $branchId, itemId: $itemId, progressState: $progressState}\n  ) {\n    _\n    __typename\n  }\n}\n',
            },
        ]

        for coach_attempt in range(2):
            res = self.session.post(
                config.GRAPHQL_URL,
                params=params,
                headers=get_csrf_headers(self.session),
                json=json_data
            )

            if res.status_code == 200:
                try:
                    res_data = res.json()
                    if res_data and isinstance(res_data, list):
                        result = res_data[0].get("data", {}).get("CoachItemProgress_UpdateCoachItemProgress", {})
                        if result.get("_") is True:
                            logger.success(f"Successfully completed coach item {self.item_id}")
                            return True
                    logger.error(f"Unexpected response from UpdateCoachItemProgress: {res.text}")
                except Exception as e:
                    logger.exception(f"Error parsing coach item progress update response: {e}")
            else:
                logger.warning(f"Coach item request attempt {coach_attempt + 1}/2 failed: {res.status_code}")

            if coach_attempt + 1 < 2:
                import time
                time.sleep(2.0)

        logger.error(f"Failed to complete coach item {self.item_id} after 2 attempts — skipping.")
        return False
