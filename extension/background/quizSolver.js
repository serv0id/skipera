// quizSolver.js
import { fetchCoursera, delay } from './courseraApi.js';
import { GET_STATE_QUERY, INITIATE_ATTEMPT_QUERY, SAVE_RESPONSES_QUERY, SUBMIT_DRAFT_QUERY, ASSIGNMENT_FEEDBACK_QUERY } from './queries.js';
import { callLLMProvider } from './llmProviders.js';

async function fetchGraphQL(opname, query, variables) {
  const res = await fetchCoursera("https://www.coursera.org/graphql-gateway", {
    method: "POST",
    headers: {
      "x-coursera-version": "123",
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      operationName: opname,
      variables: variables,
      query: query
    })
  });
  if (!res.ok) {
     const text = await res.text();
     throw new Error(`GraphQL API returned ${res.status}: ${text.substring(0, 100)}...`);
  }
  const contentType = res.headers.get("content-type");
  if (!contentType || !contentType.includes("application/json")) {
     const text = await res.text();
     throw new Error(`Expected JSON but got ${contentType}: ${text.substring(0, 100)}...`);
  }
  const data = await res.json();
  if (data.errors) throw new Error(`GraphQL Error: ${JSON.stringify(data.errors)}`);
  return data;
}

async function callLLM(unsolvedQuestions, settings) {
  const systemPrompt = `Answer the provided questions. Be precise and concise.
The questions are in a dict format where each key represents the question id, and the value is a JSON dict containing:
- 'Question': the question text (which might have HTML tags, ignore them).
- 'Options': a list of options (for MULTIPLE_CHOICE and CHECKBOX types) with option_id and value.
- 'Type': one of 'MULTIPLE_CHOICE', 'CHECKBOX', 'TEXT_REFLECT', 'NUMERIC', 'PLAIN_TEXT', 'TEXT_EXACT_MATCH', 'REGEX', 'FILE_UPLOAD', or 'URL'.
- 'previous_attempts': (optional) past attempt results.

CRITICAL: Always provide a step-by-step logical deduction in the 'reasoning' field before providing your final answer.

Rules for each question type:
1. MULTIPLE_CHOICE: Select exactly one option_id and place it in the 'chosen' list.
2. CHECKBOX: Select one or more option_ids and place them in the 'chosen' list.
3. TEXT_REFLECT, NUMERIC, PLAIN_TEXT, TEXT_EXACT_MATCH, REGEX, FILE_UPLOAD, URL: Answer in the 'answer' field.

IMPORTANT for CHECKBOX:
If a question has 'previous_attempts', each entry records a prior submission of chosen option_ids.
Use partial scores to logically deduce the status of options.`;

  const userPrompt = JSON.stringify(unsolvedQuestions, null, 2);
  const keys = settings.apiKey.split(",").map(k => k.trim()).filter(k => k);
  const provider = settings.provider || "nvidia";
  
  return await callLLMProvider(provider, keys, settings.modelName, systemPrompt, userPrompt);
}

const TYPE_LOOKUP = {
  "MULTIPLE_CHOICE": ["multipleChoiceResponse", "chosen"],
  "CHECKBOX": ["checkboxResponse", "chosen"],
  "TEXT_REFLECT": ["textReflectResponse", "answer"],
  "NUMERIC": ["numericResponse", "answer"],
  "PLAIN_TEXT": ["plainTextResponse", "plainText"],
  "TEXT_EXACT_MATCH": ["textExactMatchResponse", "answer"],
  "REGEX": ["regexResponse", "answer"],
  "FILE_UPLOAD": ["fileUploadResponse", "fileUrl"],
  "URL": ["urlResponse", "url"],
};
const TEXT_ANSWER_TYPES = new Set(["TEXT_REFLECT", "NUMERIC", "PLAIN_TEXT", "TEXT_EXACT_MATCH", "REGEX", "FILE_UPLOAD", "URL"]);

function formatResponse(partId, qType, chosen = null, answer = null) {
  if (qType === "MULTIPLE_CHOICE") {
    return {
      questionId: partId,
      questionType: qType,
      questionResponse: { multipleChoiceResponse: { chosen: chosen ? chosen[0] : null } }
    };
  } else if (qType === "CHECKBOX") {
    return {
      questionId: partId,
      questionType: qType,
      questionResponse: { checkboxResponse: { chosen: chosen || [] } }
    };
  } else if (qType === "FILE_UPLOAD") {
    const urlVal = (answer && answer.startsWith("http")) ? answer : "https://raw.githubusercontent.com/yamantaka-singh/skipera/main/README.md";
    return {
      questionId: partId,
      questionType: qType,
      questionResponse: { fileUploadResponse: { title: "submission.txt", caption: answer || "Assignment Submission", fileUrl: urlVal } }
    };
  } else if (qType === "URL") {
    const urlVal = (answer && answer.startsWith("http")) ? answer : "https://github.com";
    return {
      questionId: partId,
      questionType: qType,
      questionResponse: { urlResponse: { title: "Project Submission", caption: answer || "Submission URL", url: urlVal } }
    };
  } else {
    const [responseKey, valKey] = TYPE_LOOKUP[qType];
    return {
      questionId: partId,
      questionType: qType,
      questionResponse: { [responseKey]: { [valKey]: answer || null } }
    };
  }
}

import { updateDashboard } from './dashboardStore.js';

export async function triggerQuizSolver(courseId, itemId, settings, tabId, courseSlug = "default", runContext = null) {
  const safeSlug = courseSlug || "default";
  const updateProgress = (msg, overrideType) => {
    let type = overrideType || "info";
    if (!overrideType) {
      if (msg.includes("ERROR") || msg.includes("Failed") || msg.includes("Error")) type = "error";
      else if (msg.includes("Complete") || msg.includes("successfully") || msg.includes("Passed")) type = "complete";
      else if (msg.includes("Starting") || msg.includes("Processing") || msg.includes("Triggering")) type = "active";
    }
    updateDashboard(msg, type, safeSlug);
  };
  
  updateProgress(`Starting quiz solver for courseId: ${courseId}, itemId: ${itemId}`);
  
  try {
  
  let targetGrade = 0.8;
  let maxAttempts = 3;
  let attemptsMade = 0;
  
  // Local cache for correctness
  let questionsData = {}; 

  while (attemptsMade < maxAttempts) {
    if (runContext?.isCancelled) {
      updateProgress("Quiz solver cancelled (tab closed).", "error");
      return;
    }
    // 1. Get State
    const stateRes = await fetchGraphQL("QueryState", GET_STATE_QUERY, { courseId, itemId });
    const submissionState = stateRes.data.SubmissionState.queryState;
    
    if (submissionState.outcome?.isPassed && submissionState.outcome.earnedGrade >= targetGrade) {
      updateProgress(`Already passed! Current grade: ${(submissionState.outcome.earnedGrade * 100).toFixed(1)}% (Target: ${(targetGrade * 100).toFixed(1)}%)`);
      return;
    } else if (submissionState.outcome?.isPassed) {
      updateProgress(`Passed, but grade ${(submissionState.outcome.earnedGrade * 100).toFixed(1)}% is below target ${(targetGrade * 100).toFixed(1)}%. Retrying...`);
    }
    
    const allowed = submissionState.allowedAction;
    if (allowed === "START_NEW_ATTEMPT") {
      await fetchGraphQL("Submission_StartAttempt", INITIATE_ATTEMPT_QUERY, { courseId, itemId });
      continue;
    } else if (allowed === "RESUME_DRAFT") {
      updateProgress("Resuming draft.");
    } else if (allowed === null) {
      if (submissionState.outcome?.isPassed) return;
      throw new Error("No more attempts remaining.");
    }

    // 2. Retrieve Questions
    const draft = submissionState.attempts.inProgressAttempt;
    const attemptId = draft.id;
    const draftId = draft.draft.id;
    const parts = draft.draft.parts;
    
    let answerResponses = [];
    let unsolvedQuestions = {};

    const QTYPE_MAP = {
      "Submission_MultipleChoiceQuestion": "MULTIPLE_CHOICE",
      "Submission_CheckboxQuestion": "CHECKBOX",
      "Submission_TextReflectQuestion": "TEXT_REFLECT",
      "Submission_NumericQuestion": "NUMERIC",
      "Submission_PlainTextQuestion": "PLAIN_TEXT",
      "Submission_TextExactMatchQuestion": "TEXT_EXACT_MATCH",
      "Submission_RegexQuestion": "REGEX",
      "Submission_FileUploadQuestion": "FILE_UPLOAD",
      "Submission_UrlQuestion": "URL"
    };
    
    for (const part of parts) {
      if (part.__typename === "Submission_TextBlock") {
        continue;
      }

      const qTypeStr = QTYPE_MAP[part.__typename];
      if (!qTypeStr) {
        throw new Error(`Unsupported question type encountered: ${part.__typename}`);
      }

      const partId = part.partId;
      if (!questionsData[partId]) questionsData[partId] = { Options: [] };
      const qd = questionsData[partId];
      
      const prompt = part.questionSchema.prompt?.cmlValue || "";
      const schemaOptions = part.questionSchema.options || [];
      const options = schemaOptions.map(opt => {
        const val = opt.display.cmlValue;
        const existing = qd.Options.find(o => o.value === val);
        return {
          option_id: opt.optionId,
          value: val,
          correct: existing ? existing.correct : null
        };
      });
      qd.Options = options;
      qd.Type = qTypeStr;
      qd.Question = prompt;

      if (TEXT_ANSWER_TYPES.has(qTypeStr)) {
        if (qd.correct_answer) {
          answerResponses.push(formatResponse(partId, qTypeStr, null, qd.correct_answer));
        } else {
          unsolvedQuestions[partId] = { Question: prompt, Options: [], Type: qTypeStr };
          if (qd.wrong_attempts) unsolvedQuestions[partId].previous_attempts = qd.wrong_attempts;
        }
      } else if (qTypeStr === "MULTIPLE_CHOICE") {
        const knownCorrect = options.find(o => o.correct === true);
        if (knownCorrect) {
          answerResponses.push(formatResponse(partId, qTypeStr, [knownCorrect.option_id]));
          continue;
        }
        const filtered = options.filter(o => o.correct !== false);
        if (filtered.length === 1) {
          answerResponses.push(formatResponse(partId, qTypeStr, [filtered[0].option_id]));
          continue;
        }
        unsolvedQuestions[partId] = { Question: prompt, Options: filtered, Type: qTypeStr };
      } else if (qTypeStr === "CHECKBOX") {
        const allResolved = options.every(o => o.correct !== null);
        if (allResolved) {
          const correctIds = options.filter(o => o.correct === true).map(o => o.option_id);
          answerResponses.push(formatResponse(partId, qTypeStr, correctIds));
          continue;
        }
        const filtered = options.filter(o => o.correct !== false);
        unsolvedQuestions[partId] = { Question: prompt, Options: filtered, Type: qTypeStr };
      }
    }

    if (Object.keys(unsolvedQuestions).length > 0) {
      updateProgress("Calling LLM for unsolved questions...");
      const llmResult = await callLLM(unsolvedQuestions, settings);
      
      if (!llmResult || !llmResult.responses || llmResult.responses.length === 0) {
        throw new Error("LLM returned an empty or invalid response format.");
      }
      
      for (const ans of llmResult.responses) {
        answerResponses.push(formatResponse(ans.question_id, unsolvedQuestions[ans.question_id].Type, ans.chosen, ans.answer));
      }
    } else {
      updateProgress("All questions answered via local cache.");
    }

    // 3. Save Responses
    await fetchGraphQL("Submission_SaveResponses", SAVE_RESPONSES_QUERY, {
      input: { courseId, itemId, attemptId, questionResponses: answerResponses }
    });

    // 4. Submit Draft
    await fetchGraphQL("Submission_SubmitLatestDraft", SUBMIT_DRAFT_QUERY, {
      input: { courseId, itemId, submissionId: draftId }
    });

    // 5. Wait & Get Feedback
    await delay(5000);
    const fbRes = await fetchGraphQL("AssignmentFeedback", ASSIGNMENT_FEEDBACK_QUERY, { courseId, itemId });
    
    const feedbackData = fbRes?.data?.SubmissionState?.queryState?.feedback;
    if (feedbackData) {
      const outcome = feedbackData.outcome || {};
      const latestScore = outcome.latestScore || 0;
      const maxScore = outcome.maxScore || 1;
      const earnedGrade = latestScore / maxScore;
      
      updateProgress(`Received feedback. Earned grade: ${(earnedGrade * 100).toFixed(1)}% | Target grade: ${(targetGrade * 100).toFixed(1)}%`);
      
      if (earnedGrade >= targetGrade) {
        updateProgress("Passed with target grade!");
        return;
      }
      
      if (feedbackData.parts) {
        for (const fPart of feedbackData.parts) {
        const partId = fPart.partId;
        const qd = questionsData[partId];
        if (!qd) continue;

        const isCorrect = fPart.feedback?.correctness === "CORRECT";
        const submitted = answerResponses.find(r => r.questionId === partId);
        
        if (!isCorrect && submitted) {
          qd.wrong_attempts = qd.wrong_attempts || [];
          let chosen = null;
          if (qd.Type === "CHECKBOX") {
            chosen = submitted.questionResponse.checkboxResponse?.chosen;
          } else if (qd.Type === "MULTIPLE_CHOICE") {
            const mChosen = submitted.questionResponse.multipleChoiceResponse?.chosen;
            chosen = mChosen ? [mChosen] : [];
            // For multiple choice, mark the single chosen option as definitely wrong
            if (chosen.length === 1) {
              const wrongOpt = qd.Options.find(o => o.option_id === chosen[0]);
              if (wrongOpt) wrongOpt.correct = false;
            }
          } else {
            const resKeys = Object.keys(submitted.questionResponse);
            if (resKeys.length > 0) {
               const valKeys = Object.keys(submitted.questionResponse[resKeys[0]]);
               if (valKeys.length > 0) chosen = submitted.questionResponse[resKeys[0]][valKeys[0]];
            }
          }
          if (chosen) qd.wrong_attempts.push(chosen);
        } else if (isCorrect && submitted) {
          // If the question is correct, cache the correct answer in case we need to retry the whole quiz
          if (qd.Type === "CHECKBOX") {
             const chosen = submitted.questionResponse.checkboxResponse?.chosen || [];
             for (const opt of qd.Options) opt.correct = chosen.includes(opt.option_id);
          } else if (qd.Type === "MULTIPLE_CHOICE") {
             const mChosen = submitted.questionResponse.multipleChoiceResponse?.chosen;
             for (const opt of qd.Options) opt.correct = (opt.option_id === mChosen);
          } else {
             const resKeys = Object.keys(submitted.questionResponse);
             if (resKeys.length > 0) {
               const valKeys = Object.keys(submitted.questionResponse[resKeys[0]]);
               if (valKeys.length > 0) qd.correct_answer = submitted.questionResponse[resKeys[0]][valKeys[0]];
             }
          }
        }
      }
    }
    }
    
    attemptsMade++;
  }
  
  // If we exit the loop without passing
  throw new Error(`Failed to pass after ${maxAttempts} attempts.`);
  
  } catch (err) {
    updateProgress(`ERROR: ${err.message}`);
    throw err;
  }
}
