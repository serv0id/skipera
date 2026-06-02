import uuid
from html import escape
from html.parser import HTMLParser

import requests
from loguru import logger

from .. import config
from ..llm.connector import GeminiConnector, PerplexityConnector, DeepSeekConnector
from ..session_utils import get_csrf_headers

import datetime

SYSTEM_PROMPT = (
    "Write a concise Coursera assignment reply for the provided prompt. "
    "Answer every question directly, use a natural first-person tone, and keep it concrete. "
    "Never return fill-in-the-blank templates, bracketed placeholders. "
    "If the prompt asks for personal details that were not provided, omit those details or answer in a "
    "neutral way instead of inventing facts. "
    "Return only the assignment reply text. Do not include XML, HTML, markdown headings, or preamble."
)

DRAFT_FIELDS = (
    "submission,context,creatorId,attachedAssignmentId,createdAt,"
    "upgradeSubmissionToLatestAssignment,blocksSubmit,validationErrors,"
    "onDemandPeerReviewSchemas.v1(reviewSchema),"
    "onDemandPeerSubmissionSchemas.v1(submissionSchema)"
)
DRAFT_INCLUDES = "reviewSchemas,submissionSchemas"

SUBMISSION_FIELDS = (
    "submission,gradingType,gradingEvents,context,creatorId,"
    "attachedAssignmentId,createdAt,upgradeSubmissionToLatestAssignment,"
    "blocksSubmit,validationErrors,upvotes,isUpvotedByRequester,"
    "isDeleted,isLatestDeletedSubmissionDeletedByAdmin,isAnonymous,"
    "onDemandPeerReviewSchemas.v1(reviewSchema),"
    "onDemandPeerSubmissionSchemas.v1(submissionSchema),"
    "onDemandSocialProfiles.v1(userId,externalUserId,fullName,photoUrl,"
    "courseRole,isAnonymous)"
)
SUBMISSION_INCLUDES = "submissionSchemas,reviewSchemas,profiles"


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


class AssignmentPromptSolver(object):
    def __init__(self, session: requests.Session, user_id: str, course_id: str, item_id: str):
        self.session: requests.Session = session
        self.user_id: str = user_id
        self.course_id: str = course_id
        self.item_id: str = item_id

    PERMISSIONS_FIELDS = (
        "deleteSubmission,listSubmissions,reviewPeers,viewReviewSchema,anonymousPeerReview,"
        "onDemandPeerSubmissionProgresses.v1(latestSubmissionSummary,latestDraftSummary,"
        "latestAttemptSummary),onDemandPeerReceivedReviewProgresses.v1(evaluationIfReady,"
        "earliestCompletionTime,reviewCount,defaultReceivedReviewRequiredCount),"
        "onDemandPeerDisplayablePhaseSchedules.v1(currentPhase,phaseEnds,phaseStarts)"
    )
    PERMISSIONS_INCLUDES = "receivedReviewsProgress,submissionProgress,phaseSchedule"

    @property
    def _draft_url(self) -> str:
        return (config.BASE_URL + "onDemandPeerSubmissionDrafts.v1/"
                + f"{self.user_id}~{self.course_id}~{self.item_id}")

    @property
    def _submission_url(self) -> str:
        return config.BASE_URL + "onDemandPeerSubmissions.v1/"

    @property
    def _permissions_url(self) -> str:
        return (config.BASE_URL + "onDemandPeerAssignmentPermissions.v1/"
                + f"{self.user_id}~{self.course_id}~{self.item_id}")
        
    def check_status(self) -> str:
        """
        Check the current status of the peer assignment.

        Returns one of: 'GRADED', 'SUBMITTED', 'DRAFT', 'NOT_STARTED', 'ERROR'
        """
        res = self.session.get(
            self._permissions_url,
            params={
                "fields": self.PERMISSIONS_FIELDS,
                "includes": self.PERMISSIONS_INCLUDES,
            },
        )

        if res.status_code != 200:
            logger.debug(f"Permissions GET {res.status_code}: {res.text[:300]}")
            return "ERROR"

        data = res.json()
        elements = data.get("elements") or []
        if not elements:
            return "NOT_STARTED"

        progresses = data.get("linked", {}).get(
            "onDemandPeerSubmissionProgresses.v1") or []
        progress = progresses[0] if progresses else {}

        submission_summary = progress.get("latestSubmissionSummary", {})
        draft_summary = progress.get("latestDraftSummary", {})
        received_reviews = data.get("linked", {}).get(
            "onDemandPeerReceivedReviewProgresses.v1") or []

        # Check for a completed evaluation (graded state)
        for review in received_reviews:
            evaluation = review.get("evaluationIfReady", {}).get("evaluation")
            if evaluation:
                score = evaluation.get("score", 0)
                max_score = evaluation.get("maxScore", 1)
                passing = evaluation.get("passingFraction", 0)
                required = review.get("defaultReceivedReviewRequiredCount", 0)
                count = review.get("reviewCount", 0)
                logger.info(
                    f"Assignment GRADED: {score}/{max_score} "
                    f"(passing: {passing:.0%}, reviews: {count}/{required})"
                )
                return "GRADED"

        # Already submitted — log review progress if available
        if submission_summary:
            if received_reviews:
                r = received_reviews[0]
                count = r.get("reviewCount", 0)
                required = r.get("defaultReceivedReviewRequiredCount", 0)
                logger.info(
                    f"Assignment already SUBMITTED "
                    f"(reviews: {count}/{required}, awaiting evaluation)"
                )
            else:
                logger.info("Assignment already SUBMITTED (awaiting peer reviews).")
            return "SUBMITTED"

        # Draft exists but not submitted
        if draft_summary:
            logger.info("Assignment has a DRAFT in progress.")
            return "DRAFT"

        return "NOT_STARTED"

    def solve(self) -> bool:
        # ── status check ──
        status = self.check_status()
        if status in ("GRADED", "SUBMITTED"):
            logger.success(f"Assignment status is {status} — nothing to do.")
            return True
        if status == "ERROR":
            logger.error("Could not determine assignment status.")
            return False

        prompt = self.get_prompt()
        if prompt is None:
            logger.error("Could not retrieve assignment prompt.")
            return False

        connector = self.get_connector()
        answers = {}
        for part in prompt["parts"]:
            llm_prompt = self.format_llm_prompt(prompt, part)
            answer = connector.get_response(llm_prompt, system_prompt=SYSTEM_PROMPT)
            answers[part["id"]] = answer
            logger.info(f"Generated answer for part: {part['prompt'][:80]}...")

        if self._save_and_submit(prompt, answers):
            logger.success("Assignment submitted.")
            return True
        else:
            logger.error("Could not submit assignment.")
            return False

    def get_connector(self) -> PerplexityConnector | GeminiConnector | DeepSeekConnector:
        if config.PERPLEXITY_API_KEY:
            return PerplexityConnector()
        if config.GEMINI_API_KEY:
            return GeminiConnector()
        if config.DEEPSEEK_API_KEY:
            return DeepSeekConnector()
        raise RuntimeError("No API Key specified.")

    # ── prompt extraction ────────────────────────────────────────────

    def get_prompt(self) -> dict | None:
        res = self.session.get(
            config.BASE_URL + "onDemandPeerAssignmentInstructions.v1",
            params={
                "q": "latest",
                "userId": self.user_id,
                "courseId": self.course_id,
                "itemId": self.item_id,
                "includes": "gradingMetadata,reviewSchemas,submissionSchemas",
                "fields": "instructions,onDemandPeerAssignmentGradingMetadata.v1(requiredAuthoredReviewCount"
                          ",isMentorGraded,assignmentDetails),onDemandPeerReviewSchemas.v1(reviewSchema),"
                          "onDemandPeerSubmissionSchemas.v1(submissionSchema)"
            }
        )

        if res.status_code != 200:
            logger.debug(res.text)
            return None

        data = res.json()
        elements = data.get("elements") or []
        if not elements:
            logger.debug(data)
            return None

        element = elements[0]
        instructions = element.get("instructions", {})

        intro = instructions.get("introduction", {})
        main_prompt = self.cml_to_text(
            intro.get("definition", {}).get("value", "")
        )

        review_criteria = ""
        for section in instructions.get("sections", []):
            if section.get("typeId") == "reviewCriteria":
                review_criteria = self.cml_to_text(
                    section.get("content", {}).get("definition", {}).get("value", "")
                )
                break

        assignment_id = element.get("id", "unknown").split("~")[-1]
        logger.info(f"Retrieved prompt for assignment {assignment_id}.")

        schemas = data.get("linked", {}).get(
            "onDemandPeerSubmissionSchemas.v1") or []
        if not schemas:
            logger.warning("No submission schemas found.")
            return None

        submission_schema = schemas[0].get("submissionSchema", {})
        raw_parts = submission_schema.get("parts", [])
        if not raw_parts:
            logger.warning("No submission parts found in schema.")
            return None

        parts = []
        for part in raw_parts:
            part_prompt = self.cml_to_text(
                part.get("prompt", {}).get("definition", {}).get("value", "")
            )
            part_type = part.get("details", {}).get("typeName", "plainText")
            parts.append({
                "id": part["id"],
                "prompt": part_prompt,
                "type": part_type,
            })

        return {
            "assignment_id": assignment_id,
            "main_prompt": main_prompt,
            "review_criteria": review_criteria,
            "parts": parts,
        }

    # ── draft fetching ──────────────────────────────────────────────

    def _get_draft(self) -> dict | None:
        """GET onDemandPeerSubmissionDrafts.v1/{userId}~{courseId}~{itemId}"""
        res = self.session.get(
            self._draft_url,
            params={"fields": DRAFT_FIELDS, "includes": DRAFT_INCLUDES},
        )
        if res.status_code != 200:
            logger.debug(f"Draft GET {res.status_code}: {res.text[:300]}")
            return None
        data = res.json()
        elements = data.get("elements") or []
        return elements[0] if elements else None

    # ── save & submit ────────────────────────────────────────────────

    def _save_and_submit(self, prompt: dict, answers: dict[str, str]) -> bool:
        """Save draft via PUT, then finalize submission via POST."""

        # ── build part responses ──
        draft_parts = {}
        for part in prompt["parts"]:
            part_id = part["id"]
            part_type = part["type"]
            answer_text = answers.get(part_id, "")

            if part_type == "richText":
                draft_parts[part_id] = {
                    "typeName": "richText",
                    "definition": {
                        "richText":{
                            "typeName":"cml",
                            "definition":{
                                "dtdId":"peerSubmission/1",
                                "value": self.to_cml(answer_text)
                            },
                            "renderableHtmlWithMetadata":{
                                "metadata":{
                                    "hasMath":False,
                                    "isPlainText":True,
                                    "hasAssetBlock":False,
                                    "hasCodeBlock":False
                                },
                                "renderableHtml": self.to_renderable_html(answer_text)
                            }
                        },

                    }
                }
            else:
                draft_parts[part_id] = {
                    "typeName": "plainText",
                    "definition": {
                        "plainText": answer_text,
                    }
                }

        # ── save draft ──
        body = {
            "submission": {
                "title": "Project",
                "parts": draft_parts,
            },
            "attachedAssignmentId": prompt["assignment_id"],
        }

        res = self.session.put(
            self._draft_url,
            params={"fields": DRAFT_FIELDS, "includes": DRAFT_INCLUDES},
            headers=get_csrf_headers(self.session),
            json=body,
        )

        if res.status_code >= 400:
            logger.debug(f"Draft PUT failed ({res.status_code}): {res.text[:500]}")
            return False
        logger.info("Draft saved.")
        
        # ── get draft state (provides createdAt) ──
        draft = self._get_draft()

        draft_created_at = None
        if draft:
            draft_created_at = draft.get("createdAt")
            
        # ── finalize submission ──
        verifiable_id = self._generate_verifiable_id()

        res = self.session.post(
            self._submission_url,
            params={"fields": SUBMISSION_FIELDS, "includes": SUBMISSION_INCLUDES},
            headers=get_csrf_headers(self.session),
            json={
                "courseId": self.course_id,
                "itemId": self.item_id,
                "draftCreatedAt": draft_created_at,
                "verifiableId": verifiable_id,
                "gradingType": "AI",
            },
        )

        if res.status_code >= 400:
            logger.warning(
                f"Submission POST returned {res.status_code} "
                f"(draft was saved): {res.text[:300]}"
            )
            return True  # draft at least saved

        logger.info("Assignment submitted successfully.")
        return True

    def _generate_verifiable_id(self) -> str:
        """Generate a verifiableId in the format <uuid-v4>~<user-id>."""
        return f"{uuid.uuid4()}~{self.user_id}"
    
    def _get_current_timestamp(self) -> int:
        now = datetime.datetime.now()
        return int(now.timestamp()*1000)

    # ── helpers ──────────────────────────────────────────────────────

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

    @staticmethod
    def to_renderable_html(answer: str) -> str:
        lines = [line.strip() for line in answer.splitlines() if line.strip()]
        if not lines:
            lines = [answer.strip()]
        return "<div class=\"cmlToHtml-content-container\" style=\"white-space: pre-wrap\">".join(f"<p>{escape(line)}</p>" for line in lines) + "</div>"

    @staticmethod
    def format_llm_prompt(prompt: dict, part: dict) -> str:
        parts = [
            f"Assignment prompt:\n{prompt['main_prompt']}",
        ]
        if prompt.get("review_criteria"):
            parts.append(f"Review criteria:\n{prompt['review_criteria']}")
        parts.append(
            f"Now answer this specific part:\n{part['prompt']}\n\n"
            "Write the reply I should submit."
        )
        return "\n\n".join(parts)
