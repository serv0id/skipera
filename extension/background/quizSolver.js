// quizSolver.js
import { fetchCoursera, delay, getModuleContext } from './courseraApi.js';
import { GET_STATE_QUERY, INITIATE_ATTEMPT_QUERY, SAVE_RESPONSES_QUERY, SUBMIT_DRAFT_QUERY, ASSIGNMENT_FEEDBACK_QUERY } from './queries.js';
import { callLLMProvider } from './llmProviders.js';
import { getAgentForType, getReflectionPrompt, stripHtmlTags } from './agents.js';

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
     console.error(`[Skipera Solver] GraphQL ${opname} -> ${res.status}:`, text); // full body, untruncated
     throw new Error(`GraphQL API returned ${res.status}: ${text.substring(0, 100)}...`);
  }
  const contentType = res.headers.get("content-type");
  if (!contentType || !contentType.includes("application/json")) {
     const text = await res.text();
     console.error(`[Skipera Solver] GraphQL ${opname} unexpected content-type ${contentType}:`, text);
     throw new Error(`Expected JSON but got ${contentType}: ${text.substring(0, 100)}...`);
  }
  const data = await res.json();
  if (data.errors) throw new Error(`GraphQL Error: ${JSON.stringify(data.errors)}`);
  return data;
}

const TEXT_ANSWER_TYPES = new Set(["TEXT_REFLECT", "NUMERIC", "PLAIN_TEXT", "TEXT_EXACT_MATCH", "REGEX", "FILE_UPLOAD", "URL", "CODE_EXPRESSION", "MATH", "RICH_TEXT", "WIDGET"]);

async function callLLM(unsolvedQuestions, settings, systemPrompt, moduleContext = "") {
  const userPrompt = moduleContext 
    ? `Module Context (Use this to answer questions if relevant):\n${moduleContext}\n\nQuestions:\n${JSON.stringify(unsolvedQuestions, null, 2)}`
    : JSON.stringify(unsolvedQuestions, null, 2);
  const keys = (settings?.apiKey || "").split(",").map(k => k.trim()).filter(k => k);
  const provider = settings?.provider || "nvidia";
  
  return await callLLMProvider(provider, keys, settings?.modelName, systemPrompt, userPrompt);
}

import { updateDashboard } from './dashboardStore.js';

export async function triggerQuizSolver(courseId, itemId, settings, tabId, courseSlug = "default", runContext = null, materials = null) {
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
  
  let targetGrade = (typeof settings?.targetGrade === "number" && settings.targetGrade > 0) ? settings.targetGrade : 0.8;
  let maxAttempts = 2; // give up and let the orchestrator skip this item after 2 failed attempts
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
    } else {
      // Catch-all, not just `allowed === null`: any other value (undefined, an
      // unrecognized enum) means there's no draft to resume either, and falling
      // through to `inProgressAttempt.id` below crashes with "Cannot read
      // properties of null" instead of the real "no attempts left" story.
      if (submissionState.outcome?.isPassed) return;
      throw new Error(`No more attempts remaining (allowedAction: ${JSON.stringify(allowed)}).`);
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
      "Submission_CheckboxReflectQuestion": "CHECKBOX_REFLECT",
      "Submission_TextReflectQuestion": "TEXT_REFLECT",
      "Submission_NumericQuestion": "NUMERIC",
      "Submission_PlainTextQuestion": "PLAIN_TEXT",
      "Submission_TextExactMatchQuestion": "TEXT_EXACT_MATCH",
      "Submission_RegexQuestion": "REGEX",
      "Submission_FileUploadQuestion": "FILE_UPLOAD",
      "Submission_UrlQuestion": "URL",
      "Submission_CodeExpressionQuestion": "CODE_EXPRESSION",
      "Submission_MathQuestion": "MATH",
      "Submission_RichTextQuestion": "RICH_TEXT",
      "Submission_WidgetQuestion": "WIDGET",
      "Submission_MultipleFillableBlanksQuestion": "MULTIPLE_FILLABLE_BLANKS"
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
      const options = schemaOptions.map((opt, idx) => {
        const val = opt.display.cmlValue;
        const existing = qd.Options.find(o => o.value === val);
        return {
          original_id: opt.optionId,
          option_id: `opt_${idx + 1}`,
          value: stripHtmlTags(val),
          correct: existing ? existing.correct : null
        };
      });
      qd.Options = options;
      qd.Type = qTypeStr;
      qd.Question = stripHtmlTags(prompt);

      if (TEXT_ANSWER_TYPES.has(qTypeStr)) {
        if (qd.correct_answer) {
          const agent = getAgentForType(qTypeStr);
          answerResponses.push(agent.formatPayload(partId, qTypeStr, null, qd.correct_answer));
        } else {
          unsolvedQuestions[partId] = { Question: qd.Question, Options: [], Type: qTypeStr };
          if (qd.wrong_attempts) unsolvedQuestions[partId].previous_attempts = qd.wrong_attempts;
        }
      } else if (qTypeStr === "MULTIPLE_CHOICE") {
        const knownCorrect = options.find(o => o.correct === true);
        if (knownCorrect) {
          const agent = getAgentForType(qTypeStr);
          answerResponses.push(agent.formatPayload(partId, qTypeStr, [knownCorrect.option_id]));
          continue;
        }
        const filtered = options.filter(o => o.correct !== false);
        if (filtered.length === 1) {
          const agent = getAgentForType(qTypeStr);
          answerResponses.push(agent.formatPayload(partId, qTypeStr, [filtered[0].option_id]));
          continue;
        }
        unsolvedQuestions[partId] = { Question: qd.Question, Options: filtered, Type: qTypeStr };
      } else if (qTypeStr === "CHECKBOX" || qTypeStr === "CHECKBOX_REFLECT") {
        const allResolved = options.every(o => o.correct !== null);
        if (allResolved) {
          const correctIds = options.filter(o => o.correct === true).map(o => o.option_id);
          const agent = getAgentForType(qTypeStr);
          answerResponses.push(agent.formatPayload(partId, qTypeStr, correctIds));
          continue;
        }
        const filtered = options.filter(o => o.correct !== false);
        unsolvedQuestions[partId] = { Question: qd.Question, Options: filtered, Type: qTypeStr };
      }
    }

    let moduleContext = "";
    if (Object.keys(unsolvedQuestions).length > 0) {
      updateProgress("Calling LLM for unsolved questions...");

      moduleContext = materials ? await getModuleContext(courseId, itemId, materials) : "";

      let domainGroups = {};
      for (const [qid, q] of Object.entries(unsolvedQuestions)) {
        const agent = getAgentForType(q.Type);
        const domain = agent.domain;
        if (!domainGroups[domain]) {
          domainGroups[domain] = { agent: agent, questions: {} };
        }
        domainGroups[domain].questions[qid] = q;
      }

function resolveQuestionId(ansQId, domainQuestions, responseIndex) {
  if (!domainQuestions || typeof domainQuestions !== "object") return null;
  const questionKeys = Object.keys(domainQuestions);
  if (questionKeys.length === 0) return null;

  // 1. Direct key match
  if (ansQId && domainQuestions[ansQId]) {
    return ansQId;
  }

  // 2. Case-insensitive & trimmed match
  if (ansQId) {
    const cleanId = String(ansQId).trim().toLowerCase();
    const caseMatch = questionKeys.find(k => k.trim().toLowerCase() === cleanId);
    if (caseMatch) return caseMatch;

    // 3. Match against "q1", "q2", "question_1", "part_1", numbers
    const numMatch = cleanId.match(/\d+/);
    if (numMatch) {
      const idx = parseInt(numMatch[0], 10);
      if (idx >= 1 && idx <= questionKeys.length) {
        return questionKeys[idx - 1];
      }
      if (idx >= 0 && idx < questionKeys.length) {
        return questionKeys[idx];
      }
    }
  }

  // 4. Fallback by position in responses array if valid
  if (typeof responseIndex === "number" && responseIndex >= 0 && responseIndex < questionKeys.length) {
    return questionKeys[responseIndex];
  }

  // 5. If only 1 question in this domain group, default to it
  if (questionKeys.length === 1) {
    return questionKeys[0];
  }

  return null;
}

      const domainPromises = Object.entries(domainGroups).map(async ([domain, groupData]) => {
        const domainQuestions = groupData.questions;
        const reflection = getReflectionPrompt(domainQuestions);
        const domainResponses = [];
        const covered = new Set();

        // Turn an LLM result's responses[] into formatted payloads, tracking coverage.
        const ingest = (llmResult, questionSubset) => {
          for (let i = 0; i < (llmResult?.responses?.length || 0); i++) {
            const ans = llmResult.responses[i];
            const matchedQId = resolveQuestionId(ans.question_id, questionSubset, i);
            if (!matchedQId || !questionSubset[matchedQId] || covered.has(matchedQId)) {
              console.warn(`[Skipera Solver] Unresolvable/dup question id '${ans.question_id}' in domain ${domain}`);
              continue;
            }
            const ansType = questionSubset[matchedQId].Type;
            const agent = getAgentForType(ansType);
            const { chosen, answer } = agent.postProcess(ansType, ans.chosen, ans.answer, questionSubset, matchedQId);
            domainResponses.push(agent.formatPayload(matchedQId, ansType, chosen, answer));
            covered.add(matchedQId);
          }
        };

        // Swallow the throw: an unparseable response must not skip the re-ask below
        // (it used to escape this whole function, so every question in the batch got
        // blanked and "after retry" in the warning was a lie).
        const tryCall = async (questions) => {
          try {
            return await callLLM(questions, settings, groupData.agent.buildPrompt(questions, reflection), moduleContext);
          } catch (e) {
            console.error(`[Skipera Solver] LLM call failed for domain ${domain}:`, e?.message || e);
            return null;
          }
        };

        ingest(await tryCall(domainQuestions), domainQuestions);

        // Re-ask ONCE for anything the model skipped / truncated / mis-labelled.
        const missingIds = Object.keys(domainQuestions).filter(id => !covered.has(id));
        if (missingIds.length > 0) {
          console.warn(`[Skipera Solver] Domain ${domain}: ${missingIds.length}/${Object.keys(domainQuestions).length} unanswered, re-asking.`);
          const subset = {};
          for (const id of missingIds) subset[id] = domainQuestions[id];
          ingest(await tryCall(subset), subset);
        }
        return domainResponses;
      });

      const allDomainResults = await Promise.allSettled(domainPromises);
      for (const r of allDomainResults) {
        if (r.status === "fulfilled") answerResponses.push(...r.value);
        else console.error(`[Skipera Solver] Domain solve rejected:`, r.reason?.message || r.reason);
      }
    } else {
      updateProgress("All questions answered via local cache.");
    }

    // Ensure all draft elements are answered, fallback to blank response if omitted by LLM
    const answeredIds = new Set(answerResponses.map(r => r.questionId));
    for (const part of parts) {
      if (part.__typename === "Submission_TextBlock" || !part.partId) continue;
      const partId = part.partId;
      const qTypeStr = QTYPE_MAP[part.__typename];
      if (qTypeStr && !answeredIds.has(partId)) {
        updateProgress(`WARN: no answer for a ${qTypeStr} question after retry — submitting blank`, "error");
        const agent = getAgentForType(qTypeStr);
        // Coursera's SaveResponses rejects both a missing field AND a literal empty
        // string/undefined choice with a 400 that aborts the WHOLE mutation (every
        // question in the item, not just this one) — so the "blank" fallback must
        // still be a valid, non-empty payload. MC/CHECKBOX need a real option id
        // (using [] leaves chosen[0] === undefined, which JSON.stringify drops).
        // null (not []) when there's no option to fall back to: MULTIPLE_CHOICE's
        // `chosen ? chosen[0] : null` treats [] as truthy, so chosen[0] would be
        // undefined -> JSON.stringify drops the key -> same 400 this is fixing.
        const fallbackOptions = questionsData[partId]?.Options || [];
        const fallbackChosen = fallbackOptions.length ? [fallbackOptions[0].original_id] : null;
        try {
          answerResponses.push(agent.formatPayload(partId, qTypeStr, fallbackChosen, "N/A"));
        } catch (e) {
          console.error(`Could not format blank payload for ${partId}:`, e);
        }
      }
    }

    // Per-question diagnostic log: which type, how much context, what we chose.
    // Pair with the CORRECT/WRONG line in the feedback loop to see where accuracy breaks.
    for (const r of answerResponses) {
      const qd = questionsData[r.questionId] || {};
      console.log(`[Q] attempt=${attemptsMade + 1} id=${r.questionId} type=${r.questionType} ctxChars=${moduleContext.length} prompt="${(qd.Question || "").replace(/\s+/g, " ").slice(0, 140)}" -> ${JSON.stringify(r.questionResponse).slice(0, 200)}`);
    }

    // 3. Save Responses
    console.log("[Skipera Solver] Saving answer responses payload:", JSON.stringify(answerResponses, null, 2));
    await fetchGraphQL("Submission_SaveResponses", SAVE_RESPONSES_QUERY, {
      input: { courseId, itemId, attemptId, questionResponses: answerResponses }
    });

    // 4. Submit Draft
    await fetchGraphQL("Submission_SubmitLatestDraft", SUBMIT_DRAFT_QUERY, {
      input: { courseId, itemId, submissionId: draftId }
    });

    // Coursera namespaces part ids by gradability: `autoGradableResponseId~...` vs
    // `submissionResponseId~...`. With none of the former, a human grades this, so
    // there is no score to wait for — polling just reads 0% ("awaiting grading"),
    // fails the target-grade check, and burns attempts re-submitting the same essay
    // while feeding ungraded feedback into wrong_attempts.
    if (!parts.some(p => String(p.partId || "").startsWith("autoGradableResponseId"))) {
      updateProgress("Submitted for manual grading — no auto-graded questions, so no score to wait for.", "complete");
      return;
    }

    // 5. Wait & Get Feedback. Coursera's grader lags the submit; a fixed 5s wait
    // read an ungraded response ("2-3%") and poisoned questionsData with all-WRONG
    // feedback. Poll until per-question feedback (parts) shows up. Ramp the delays:
    // auto-graded MCQ is usually ready in 2-4s, so check fast first (~28s ceiling).
    const POLL_DELAYS = [2000, 2000, 3000, 4000, 5000, 6000, 6000];
    let feedbackData = null;
    for (const d of POLL_DELAYS) {
      await delay(d);
      const fbRes = await fetchGraphQL("AssignmentFeedback", ASSIGNMENT_FEEDBACK_QUERY, { courseId, itemId });
      feedbackData = fbRes?.data?.SubmissionState?.queryState?.feedback || feedbackData;
      if (feedbackData?.parts?.length > 0) break; // per-question feedback present -> graded
    }
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
        console.log(`[Q] attempt=${attemptsMade + 1} id=${partId} ${isCorrect ? "CORRECT" : "WRONG"} type=${qd.Type} ctxChars=${moduleContext.length}`);
        
        if (!isCorrect && submitted) {
          qd.wrong_attempts = qd.wrong_attempts || [];
          let chosen = null;
          if (qd.Type === "CHECKBOX" || qd.Type === "CHECKBOX_REFLECT") {
            chosen = submitted.questionResponse.checkboxResponse?.chosen || [];
          } else if (qd.Type === "MULTIPLE_CHOICE") {
            const mChosen = submitted.questionResponse.multipleChoiceResponse?.chosen;
            chosen = mChosen ? [mChosen] : [];
          } else {
            const resKeys = Object.keys(submitted.questionResponse);
            if (resKeys.length > 0) {
               const valKeys = Object.keys(submitted.questionResponse[resKeys[0]]);
               if (valKeys.length > 0) chosen = submitted.questionResponse[resKeys[0]][valKeys[0]];
            }
          }
          
          let mappedChosen = chosen;
          if (Array.isArray(chosen) && ["MULTIPLE_CHOICE", "CHECKBOX", "CHECKBOX_REFLECT"].includes(qd.Type)) {
            mappedChosen = [];
            for (let c of chosen) {
              const wrongOpt = qd.Options.find(o => o.option_id === c || o.original_id === c);
              if (wrongOpt) {
                mappedChosen.push(wrongOpt.option_id);
                // For multiple choice, mark the single chosen option as definitely wrong
                if (qd.Type === "MULTIPLE_CHOICE" && chosen.length === 1) {
                  wrongOpt.correct = false;
                }
              } else {
                mappedChosen.push(c);
              }
            }
          }
          if (mappedChosen) qd.wrong_attempts.push(mappedChosen);
        } else if (isCorrect && submitted) {
          // If the question is correct, cache the correct answer in case we need to retry the whole quiz
          if (qd.Type === "CHECKBOX") {
             const chosen = submitted.questionResponse.checkboxResponse?.chosen || [];
             for (const opt of qd.Options) opt.correct = chosen.includes(opt.option_id) || chosen.includes(opt.original_id);
          } else if (qd.Type === "MULTIPLE_CHOICE") {
             const mChosen = submitted.questionResponse.multipleChoiceResponse?.chosen;
             for (const opt of qd.Options) opt.correct = (opt.option_id === mChosen || opt.original_id === mChosen);
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
