export const dashboardStates = {};

export function getOrCreateState(slug = "default") {
  const safeSlug = slug || "default";
  if (!dashboardStates[safeSlug]) {
    dashboardStates[safeSlug] = {
      courseSlug: safeSlug,
      completionRate: 0,
      activeTask: { title: "Idle", timeElapsed: "00:00" },
      completedTasks: [],
      skippedTasks: [],
      errors: [],
      logs: [],
      startTime: Date.now()
    };
  }
  return dashboardStates[safeSlug];
}

// Load states from chrome.storage.local on initialization
chrome.storage.local.get(["dashboardStates"], (res) => {
  if (res.dashboardStates) {
    Object.assign(dashboardStates, res.dashboardStates);
  }
});

export function broadcastState(slug = "default") {
  const safeSlug = slug || "default";
  const state = getOrCreateState(safeSlug);
  const elapsed = Math.floor((Date.now() - (state.startTime || Date.now())) / 1000);
  const m = String(Math.floor(elapsed / 60)).padStart(2, '0');
  const s = String(elapsed % 60).padStart(2, '0');
  state.activeTask.timeElapsed = `${m}:${s}`;
  
  chrome.storage.local.set({ dashboardStates });
  chrome.runtime.sendMessage({ 
    action: "DASHBOARD_UPDATE", 
    slug: safeSlug, 
    state: state 
  }).catch(() => {});
}

export function updateDashboard(msg, type = "info", slug = "default") {
  const safeSlug = slug || "default";
  console.log(`[Dashboard:${safeSlug}] ${msg}`);
  const state = getOrCreateState(safeSlug);
  
  if (type === "active") {
    state.activeTask.title = msg;
    state.startTime = Date.now();
  } else if (type === "error") {
    state.errors.unshift({ time: Date.now(), msg });
  } else if (type === "skip") {
    state.skippedTasks.unshift({ time: Date.now(), msg });
  } else if (type === "complete") {
    state.completedTasks.unshift({ time: Date.now(), msg });
  } else if (type === "completionRate") {
    state.completionRate = msg; // msg is number
  }
  
  // Keep arrays bounded so storage stays lean
  if (state.errors.length > 50) state.errors.pop();
  if (state.skippedTasks.length > 50) state.skippedTasks.pop();
  if (state.completedTasks.length > 50) state.completedTasks.pop();
  
  if (type !== "completionRate") {
    state.logs.push({ time: Date.now(), msg: String(msg), type });
    if (state.logs.length > 100) state.logs.shift();
  }
  
  broadcastState(safeSlug);
}
