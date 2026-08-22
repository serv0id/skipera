// courseraApi.js
// Handles all Coursera API interactions for the background orchestrator.

const BASE_URL = "https://www.coursera.org/api/";

/**
 * Gets the CSRF token from the browser cookies for coursera.org.
 */
export async function getCsrfToken() {
  return new Promise((resolve) => {
    chrome.cookies.get({ url: "https://www.coursera.org", name: "csrf3-token" }, (cookie) => {
      resolve(cookie ? cookie.value : null);
    });
  });
}

/**
 * Helper to make authenticated requests to Coursera API.
 */
export async function fetchCoursera(endpoint, options = {}) {
  const token = await getCsrfToken();
  const headers = {
    ...options.headers,
    "X-CSRF3-Token": token,
  };
  
  // Only add Content-Type if we're sending a body and it's not already set
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const url = (endpoint.startsWith("http") || endpoint.startsWith("/")) 
    ? endpoint 
    : `${BASE_URL}${endpoint}`;

  const res = await fetch(url, {
    credentials: "include",
    ...options,
    headers
  });
  return res;
}

export async function getUserId() {
  const res = await fetchCoursera("adminUserPermissions.v1?q=my");
  if (!res.ok) return null;
  const data = await res.json();
  return data.elements?.[0]?.id || null;
}

export async function getCourseMaterials(courseSlug) {
  const params = new URLSearchParams({
    q: "slug",
    slug: courseSlug,
    includes: "modules,lessons,passableItemGroups,passableItemGroupChoices,passableLessonElements,items,tracks,gradePolicy,gradingParameters,embeddedContentMapping",
    fields: "moduleIds,onDemandCourseMaterialModules.v1(name,slug,description,timeCommitment,lessonIds,optional,learningObjectives),onDemandCourseMaterialLessons.v1(name,slug,timeCommitment,elementIds,optional,trackId),onDemandCourseMaterialPassableItemGroups.v1(requiredPassedCount,passableItemGroupChoiceIds,trackId),onDemandCourseMaterialPassableItemGroupChoices.v1(name,description,itemIds),onDemandCourseMaterialPassableLessonElements.v1(gradingWeight,isRequiredForPassing),onDemandCourseMaterialItems.v2(name,originalName,slug,timeCommitment,contentSummary,isLocked,lockableByItem,itemLockedReasonCode,trackId,lockedStatus,itemLockSummary,customDisplayTypenameOverride),onDemandCourseMaterialTracks.v1(passablesCount),onDemandGradingParameters.v1(gradedAssignmentGroups),contentAtomRelations.v1(embeddedContentSourceCourseId,subContainerId)",
    showLockedItems: "true"
  });

  const res = await fetchCoursera(`onDemandCourseMaterials.v2/?${params.toString()}`);
  if (!res.ok) throw new Error("Failed to fetch course materials");
  return await res.json();
}

export async function getCompletedItems(userId, courseId) {
  const res = await fetchCoursera(`onDemandCoursesProgress.v1/${userId}~${courseId}?fields=gradedAssignmentGroupProgress`);
  if (!res.ok) return new Set();
  
  const data = await res.json();
  const completed = new Set();
  
  const elements = data.elements || [];
  if (elements.length > 0) {
    const items = elements[0].items || {};
    for (const [itemId, progress] of Object.entries(items)) {
      if (progress.progressState === "Completed") {
        completed.add(itemId);
      }
    }
  }
  return completed;
}

// --- ITEM COMPLETION HANDLERS ---

export async function getVideoMetadata(courseId, itemId) {
  const params = new URLSearchParams({
    includes: "video",
    fields: "disableSkippingForward,startMs,endMs"
  });
  const res = await fetchCoursera(`onDemandLectureVideos.v1/${courseId}~${itemId}?${params.toString()}`);
  const data = await res.json();
  return {
    canSkip: !data.elements[0].disableSkippingForward,
    trackingId: data.linked["onDemandVideos.v1"][0].id
  };
}

export async function watchVideo(userId, courseSlug, courseId, item, metadata) {
  const startUrl = `opencourse.v1/user/${userId}/course/${courseSlug}/item/${item.id}/lecture/videoEvents/play?autoEnroll=false`;
  const endUrl = `opencourse.v1/user/${userId}/course/${courseSlug}/item/${item.id}/lecture/videoEvents/ended?autoEnroll=false`;
  
  if (!metadata.canSkip) {
    await fetchCoursera(startUrl, { method: "POST", body: '{"contentRequestBody":{}}' });
    
    // Update progress
    await fetchCoursera(`onDemandVideoProgresses.v1/${userId}~${courseId}~${metadata.trackingId}`, {
      method: "PUT",
      body: JSON.stringify({
        videoProgressId: `${userId}~${courseId}~${metadata.trackingId}`,
        viewedUpTo: item.timeCommitment + 2000
      })
    });
  }
  
  // End item (can skip calls this directly)
  await fetchCoursera(endUrl, { method: "POST", body: '{"contentRequestBody":{}}' });
  return true;
}

export async function readSupplement(userId, courseId, itemId) {
  const res = await fetchCoursera("onDemandSupplementCompletions.v1", {
    method: "POST",
    body: JSON.stringify({
      courseId,
      itemId,
      userId: parseInt(userId)
    })
  });
  const text = await res.text();
  return text.includes("Completed");
}

export async function completeWidget(userId, courseId, itemId) {
  const res = await fetchCoursera(`onDemandWidgetSessions.v1/${userId}~${courseId}~${itemId}?fields=session,sessionId`);
  if (!res.ok) return false;
  
  const data = await res.json();
  const sessionId = data.elements?.[0]?.sessionId;
  if (!sessionId) return false;

  const putRes = await fetchCoursera(`onDemandWidgetProgress.v1/${userId}~${courseId}~${itemId}`, {
    method: "PUT",
    body: JSON.stringify({
      sessionId,
      progressState: "Completed"
    })
  });
  return putRes.ok;
}

export async function completeLti(userId, courseId, itemId) {
  const res = await fetchCoursera("rest/v1/lti/ungradedLaunches", {
    method: "POST",
    body: JSON.stringify({
      courseId,
      itemId,
      learnerId: parseInt(userId),
      markItemCompleted: true
    })
  });
  return res.ok;
}

export async function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
