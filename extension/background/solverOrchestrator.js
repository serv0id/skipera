import { getUserId, getCourseMaterials, getCompletedItems, getVideoMetadata, watchVideo, readSupplement, completeWidget, completeLti, delay, fetchCoursera, getCsrfToken } from './courseraApi.js';
import { triggerQuizSolver } from './quizSolver.js';
import { callLLMProvider } from './llmProviders.js';

let isRunning = false;

export async function runFullCourse(courseSlug, settings, tabId) {
  if (isRunning) return { status: "Already running" };
  isRunning = true;
  
  const updateProgress = (msg) => {
    if (tabId) {
      chrome.tabs.sendMessage(tabId, { action: "UPDATE_PROGRESS", message: msg }).catch(() => {});
    }
    console.log(msg);
  };
  
  try {
    const userId = await getUserId();
    if (!userId) throw new Error("Could not fetch User ID. Are you logged in?");
    
    updateProgress(`Starting run for course: ${courseSlug}`);
    const initialMaterials = await getCourseMaterials(courseSlug);
    const courseId = initialMaterials.elements[0].id;
    
    // We will loop continuously until we find no more uncompleted items
    let loopCount = 0;
    const skippedItems = new Set();
    
    while (isRunning && loopCount < 100) {
      loopCount++;
      const completedIds = await getCompletedItems(userId, courseId);
      const materials = await getCourseMaterials(courseSlug);
      
      const uncompleted = [];
      const items = materials.linked["onDemandCourseMaterialItems.v2"] || [];
      
      for (const item of items) {
        if (!completedIds.has(item.id) && !skippedItems.has(item.id)) {
          uncompleted.push(item);
        }
      }
      
      updateProgress(`Found ${uncompleted.length} uncompleted items.`);
      if (uncompleted.length === 0) {
        updateProgress("Course Complete!");
        break;
      }
      
      // Process the first available unlocked item
      let processedAny = false;
      let allLocked = uncompleted.length > 0;
      
      for (const item of uncompleted) {
        if (item.isLocked) continue;
        allLocked = false;
        
        updateProgress(`Processing item: ${item.name} (${item.contentSummary.typeName})`);
        
        try {
          if (item.contentSummary.typeName === "lecture") {
            const meta = await getVideoMetadata(courseId, item.id);
            await watchVideo(userId, courseSlug, courseId, item, meta);
            processedAny = true;
            break;
          } else if (item.contentSummary.typeName === "supplement") {
            await readSupplement(userId, courseId, item.id);
            processedAny = true;
            break;
          } else if (["plugin", "notebook"].includes(item.contentSummary.typeName)) {
            updateProgress(`Skipping unsupported assignment: ${item.name} (${item.contentSummary.typeName})`);
            skippedItems.add(item.id);
            processedAny = true;
            break;
          } else if (["exam", "quiz", "assignment", "closedAssessment", "phasedPeer", "gradedPeer", "programming", "gradedProgramming", "staffGraded", "ungradedAssignment"].includes(item.contentSummary.typeName)) {
            updateProgress(`Triggering quiz solver for ${item.name}`);
            await triggerQuizSolver(courseId, item.id, settings, tabId);
            processedAny = true;
            break;
          } else if (item.contentSummary.typeName === "widget" || item.contentSummary.typeName === "gradedWidget" || item.contentSummary.typeName === "ungradedWidget") {
            await completeWidget(userId, courseId, item.id);
            processedAny = true;
            break;
          } else if (item.contentSummary.typeName === "lti" || item.contentSummary.typeName === "gradedLti" || item.contentSummary.typeName === "ungradedLti") {
            await completeLti(userId, courseId, item.id);
            processedAny = true;
            break;
          } else if (item.contentSummary.typeName === "discussionPrompt") {
            await solveDiscussion(courseId, item.id, settings, tabId);
            processedAny = true;
            break;
          }
        } catch (e) {
          updateProgress(`Failed to process item ${item.name}: ${e.message}`);
        }
      }
      
      if (!processedAny) {
        if (allLocked) {
          updateProgress("Remaining items are locked. Waiting 5s for Coursera to unlock them...");
          await delay(5000);
          continue;
        } else {
          updateProgress("No unlocked items could be processed. Stopping.");
          break;
        }
      }
      
      await delay(2000);
    }
  } catch (err) {
    console.error(err);
    isRunning = false;
    throw err;
  }
  
  isRunning = false;
  return { status: "Finished" };
}

async function solveDiscussion(courseId, itemId, settings, tabId) {
  const updateProgress = (msg) => {
    if (tabId) {
      chrome.tabs.sendMessage(tabId, { action: "UPDATE_PROGRESS", message: msg }).catch(() => {});
    }
    console.log(msg);
  };
  
  try {
    updateProgress("Fetching discussion prompt...");
    const userId = await getUserId();
    const url = `onDemandDiscussionPrompts.v1/${userId}~${courseId}~${itemId}?fields=onDemandDiscussionPromptQuestions.v1(content),promptType,question&includes=question`;
    
    const res = await fetchCoursera(url);
    if (!res.ok) throw new Error(`Failed to fetch discussion prompt: ${res.status}`);
    const data = await res.json();
    
    if (!data.elements || data.elements.length === 0) {
      throw new Error("Could not fetch discussion prompt details.");
    }
    
    const element = data.elements[0];
    const questions = (data.linked && data.linked["onDemandDiscussionPromptQuestions.v1"]) ? data.linked["onDemandDiscussionPromptQuestions.v1"] : [];
    if (questions.length === 0) {
      throw new Error("No discussion questions found.");
    }
    
    const question = questions[0];
    const title = question.content?.question || "";
    const detailsHtml = question.content?.details?.definition?.value || "";
    // strip HTML
    const details = detailsHtml.replace(/<[^>]*>?/gm, '');
    
    let forumQuestionId = element.promptType?.definition?.courseItemForumQuestionId || question.id;
    if (!forumQuestionId) throw new Error("Could not determine courseForumQuestionId");
    
    let finalForumQuestionId = "";
    const parts = forumQuestionId.split("~");
    if (parts.length === 4 && parts[1] === courseId) {
      finalForumQuestionId = `${parts[1]}~${parts[3]}`;
    } else if (parts.length === 3 && parts[0] === courseId) {
      finalForumQuestionId = `${parts[0]}~${parts[2]}`;
    } else if (parts.length === 2 && parts[0] === courseId) {
      finalForumQuestionId = forumQuestionId;
    } else {
      finalForumQuestionId = forumQuestionId; // fallback
    }
    
    updateProgress("Asking LLM for a discussion reply...");
    
    const systemPrompt = `Write a concise Coursera discussion reply for the provided prompt. Answer every question directly, use a natural first-person tone, and keep it concrete. Never return fill-in-the-blank templates, bracketed placeholders. Return only the discussion reply text.`;
    
    const userPrompt = `Discussion title:\n${title}\n\nDiscussion prompt:\n${details}\n\nWrite the reply I should post. Return it inside the "answer" field of the JSON response schema.`;

    const keys = settings.apiKey.split(",").map(k => k.trim());
    const llmResult = await callLLMProvider(settings.provider, keys, settings.modelName, systemPrompt, userPrompt);
    
    let answerText = "";
    if (llmResult && llmResult.responses && llmResult.responses.length > 0) {
       answerText = llmResult.responses[0].answer;
    }
    
    if (!answerText) {
      throw new Error("LLM returned empty answer for discussion prompt");
    }
    
    updateProgress("Submitting discussion answer...");
    
    // To submit, we need to POST to onDemandCourseForumAnswers.v1
    const submitUrl = `onDemandCourseForumAnswers.v1/?fields=content,forumQuestionId&includes=profiles`;
    
    // Convert to CML format
    const lines = answerText.split("\n").filter(line => line.trim().length > 0);
    const cmlValue = "<co-content>" + lines.map(line => `<text>${line}</text>`).join("") + "</co-content>";
    
    const postBody = {
      content: {
        typeName: "cml",
        definition: {
          dtdId: "discussion/1",
          value: cmlValue
        }
      },
      courseForumQuestionId: finalForumQuestionId
    };
    
    const submitRes = await fetchCoursera(submitUrl, {
      method: "POST",
      body: JSON.stringify(postBody)
    });
    
    if (submitRes.ok) {
       updateProgress("Discussion prompt answered successfully!");
    } else {
       const errText = await submitRes.text();
       throw new Error(`Failed to submit discussion answer: ${submitRes.status} ${errText}`);
    }
    
  } catch (err) {
    updateProgress(`ERROR in discussion: ${err.message}`);
    throw err;
  }
}
