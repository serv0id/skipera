export const dashboardState = {
  completionRate: 0,
  activeTask: { title: "Idle", timeElapsed: "00:00" },
  completedTasks: [],
  skippedTasks: [],
  errors: [],
  logs: []
};

let startTime = Date.now();

export function broadcastState() {
  const elapsed = Math.floor((Date.now() - startTime) / 1000);
  const m = String(Math.floor(elapsed / 60)).padStart(2, '0');
  const s = String(elapsed % 60).padStart(2, '0');
  dashboardState.activeTask.timeElapsed = `${m}:${s}`;
  
  chrome.storage.local.set({ dashboardState });
  chrome.runtime.sendMessage({ action: "DASHBOARD_UPDATE", state: dashboardState }).catch(() => {});
}

export function updateDashboard(msg, type = "info") {
  console.log(`[Dashboard] ${msg}`);
  
  if (type === "active") {
    dashboardState.activeTask.title = msg;
    startTime = Date.now();
  } else if (type === "error") {
    dashboardState.errors.unshift({ time: Date.now(), msg });
  } else if (type === "skip") {
    dashboardState.skippedTasks.unshift({ time: Date.now(), msg });
  } else if (type === "complete") {
    dashboardState.completedTasks.unshift({ time: Date.now(), msg });
  } else if (type === "completionRate") {
    dashboardState.completionRate = msg; // msg is number
  }
  
  // Keep arrays bounded so we don't blow up storage
  if (dashboardState.errors.length > 50) dashboardState.errors.pop();
  if (dashboardState.skippedTasks.length > 50) dashboardState.skippedTasks.pop();
  if (dashboardState.completedTasks.length > 50) dashboardState.completedTasks.pop();
  
  if (type !== "completionRate") {
    dashboardState.logs.push({ time: Date.now(), msg: String(msg), type });
    if (dashboardState.logs.length > 100) dashboardState.logs.shift();
  }
  
  broadcastState();
}
