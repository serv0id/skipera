// background.js
import { runFullCourse } from './solverOrchestrator.js';
import { triggerQuizSolver } from './quizSolver.js';
import { getCourseMaterials } from './courseraApi.js';

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "NVIDIA_API_CALL") {
    handleNvidiaCall(request.payload, request.apiKey, request.modelName)
      .then(data => sendResponse({ success: true, data }))
      .catch(error => sendResponse({ success: false, error: error.message }));
    return true; // Keep channel open for async response
  }
  
  if (request.action === "RUN_FULL_COURSE") {
    runFullCourse(request.slug, request.settings, sender.tab?.id)
      .then(data => sendResponse(data))
      .catch(error => sendResponse({ status: "Error", error: error.message }));
    return true; // Keep channel open
  }

  if (request.action === "RUN_SINGLE_QUIZ") {
    getCourseMaterials(request.slug)
      .then(materials => {
        const courseId = materials.elements[0].id;
        return triggerQuizSolver(courseId, request.itemId, request.settings, sender.tab?.id);
      })
      .then(() => sendResponse({ status: "Quiz solver finished." }))
      .catch(error => sendResponse({ status: "Error", error: error.message }));
    return true; // Keep channel open
  }
});

async function handleNvidiaCall(questions, apiKey, modelName) {
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

  const userPrompt = JSON.stringify(questions, null, 2);

  const response = await fetch("https://integrate.api.nvidia.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      "Accept": "application/json"
    },
    body: JSON.stringify({
      model: modelName,
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userPrompt }
      ],
      max_tokens: 2000,
      temperature: 0.1,
      response_format: {
        type: "json_schema",
        json_schema: {
          name: "quiz_responses",
          schema: {
            type: "object",
            properties: {
              responses: {
                type: "array",
                items: {
                  type: "object",
                  properties: {
                    question_id: { type: "string" },
                    reasoning: { type: "string" },
                    chosen: { type: "array", items: { type: "string" } },
                    answer: { type: "string" }
                  },
                  required: ["question_id", "reasoning"]
                }
              }
            },
            required: ["responses"]
          }
        }
      }
    })
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`API Error ${response.status}: ${errText}`);
  }

  const json = await response.json();
  return JSON.parse(json.choices[0].message.content);
}
