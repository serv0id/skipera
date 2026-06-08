from html import escape
from html.parser import HTMLParser

import httpx
from loguru import logger

from .. import config
from ..llm.connector import GeminiConnector, PerplexityConnector
from ..session_utils import get_csrf_headers, random_delay


SYSTEM_PROMPT = (
    "Write a concise Coursera discussion reply for the provided prompt. "
    "Answer every question directly, use a natural first-person tone, and keep it concrete. "
    "Never return fill-in-the-blank templates, bracketed placeholders. "
    "If the prompt asks for personal details that were not provided, omit those details or answer in a "
    "neutral way instead of inventing facts. "
    "Return only the discussion reply text. Do not include XML, HTML, markdown headings, or preamble."
)


class CMLTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_text = False
        self.parts = []
        self.current = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "text":
            self.in_text = True
            self.current = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "text" and self.in_text:
            text = "".join(self.current).strip()
            if text:
                self.parts.append(text)
            self.in_text = False

    def handle_data(self, data: str) -> None:
        if self.in_text:
            self.current.append(data)


class DiscussionPromptSolver(object):
    def __init__(self, session: httpx.Client, user_id: str, course_id: str, item_id: str):
        self.session: httpx.Client = session
        self.user_id: str = user_id
        self.course_id: str = course_id
        self.item_id: str = item_id

    def solve(self) -> bool:
        prompt = self.get_prompt()
        if prompt is None:
            logger.error("Could not retrieve discussion prompt.")
            return False

        connector = self.get_connector()
        answer = connector.get_response(self.format_llm_prompt(
            prompt), system_prompt=SYSTEM_PROMPT)

        if self.submit_answer(prompt["courseForumQuestionId"], self.to_cml(answer)):
            logger.success("Discussion prompt answered.")
            return True
        else:
            logger.error("Could not submit discussion answer.")
            return False

    def get_connector(self) -> PerplexityConnector | GeminiConnector:
        if config.PERPLEXITY_API_KEY:
            return PerplexityConnector()
        if config.GEMINI_API_KEY:
            return GeminiConnector()
        raise RuntimeError("No API Key specified.")

    def get_prompt(self) -> dict | None:
        res = self.session.get(
            config.BASE_URL +
            f"onDemandDiscussionPrompts.v1/{self.user_id}~{self.course_id}~{self.item_id}",
            params={
                "fields": "onDemandDiscussionPromptQuestions.v1(content,creatorId,createdAt,forumId,sessionId,"
                          "lastAnsweredBy,lastAnsweredAt,totalAnswerCount,topLevelAnswerCount,viewCount),"
                          "promptType,question",
                "includes": "question",
            }
        )

        if res.status_code != 200:
            logger.debug(res.text)
            return None

        data = res.json()
        elements = data.get("elements") or []
        questions = data.get("linked", {}).get(
            "onDemandDiscussionPromptQuestions.v1") or []
        if not elements or not questions:
            logger.debug(data)
            return None

        element = elements[0]
        question = questions[0]
        question_content = question.get("content", {})
        details = question_content.get("details", {}).get("definition", {})
        prompt_text = self.cml_to_text(details.get("value", ""))

        course_forum_question_id = self.to_course_forum_question_id(
            element.get("promptType", {}).get("definition", {}
                                              ).get("courseItemForumQuestionId", "")
        )
        if not course_forum_question_id:
            course_forum_question_id = self.to_course_forum_question_id(
                question.get("id", ""))

        if not course_forum_question_id:
            logger.warning(
                "Could not determine courseForumQuestionId for this discussion prompt.")
            logger.debug(data)
            return None

        return {
            "title": question_content.get("question", ""),
            "details": prompt_text,
            "courseForumQuestionId": course_forum_question_id,
        }

    def submit_answer(self, course_forum_question_id: str, value: str, max_retries: int = 3) -> bool:
        if max_retries <= 0:
            logger.error("Max retries reached.")
            return False

        res = self.session.post(
            config.BASE_URL + "onDemandCourseForumAnswers.v1/",
            headers=get_csrf_headers(self.session),
            params={
                "fields": "content,forumQuestionId,parentForumAnswerId,state,creatorId,createdAt,order,"
                          "upvoteCount,childAnswerCount,isFlagged,isUpvoted,courseItemForumQuestionId,"
                          "parentCourseItemForumAnswerId,onDemandSocialProfiles.v1(userId,externalUserId,"
                          "fullName,photoUrl,courseRole),onDemandCourseForumAnswers.v1(content,forumQuestionId,"
                          "parentForumAnswerId,state,creatorId,createdAt,order,upvoteCount,childAnswerCount,"
                          "isFlagged,isUpvoted,courseItemForumQuestionId,parentCourseItemForumAnswerId)",
                "includes": "profiles,children,userId",
            },
            json={
                "content": {
                    "typeName": "cml",
                    "definition": {
                        "dtdId": "discussion/1",
                        "value": value,
                    },
                },
                "courseForumQuestionId": course_forum_question_id,
            },
        )

        if 200 <= res.status_code < 300:
            return True

        if "FORUM_POST_RATE_LIMIT_REACHED_EXCEPTION" in res.text:
            logger.warning("Rate limit reached! Wait a bit...")
            random_delay(5.0, 10.0)
            return self.submit_answer(course_forum_question_id, value, max_retries - 1)

        logger.debug(res.text)
        return False

    @staticmethod
    def cml_to_text(value: str) -> str:
        parser = CMLTextParser()
        parser.feed(value)
        return "\n".join(parser.parts)

    @staticmethod
    def to_cml(answer: str) -> str:
        lines = [line.strip() for line in answer.splitlines() if line.strip()]
        if not lines:
            lines = [answer.strip()]
        return "<co-content>" + "".join(f"<text>{escape(line)}</text>" for line in lines) + "</co-content>"

    def to_course_forum_question_id(self, forum_question_id: str) -> str:
        parts = forum_question_id.split("~")
        if len(parts) == 4 and parts[1] == self.course_id:
            return f"{parts[1]}~{parts[3]}"
        if len(parts) == 3 and parts[0] == self.course_id:
            return f"{parts[0]}~{parts[2]}"
        if len(parts) == 2 and parts[0] == self.course_id:
            return forum_question_id
        return ""

    @staticmethod
    def format_llm_prompt(prompt: dict) -> str:
        return (
            f"Discussion title:\n{prompt['title']}\n\n"
            f"Discussion prompt:\n{prompt['details']}\n\n"
            "Write the reply I should post."
        )
