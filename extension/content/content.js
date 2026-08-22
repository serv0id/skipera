console.log("Skipera Content script loaded.");

let state = {
  apiKey: null,
  modelName: null,
  isSolving: false
};

// Listen for messages from the popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "PING") {
    sendResponse({ status: "OK", url: window.location.href });
  } else if (request.action === "START_SOLVER") {
    if (state.isSolving) {
      sendResponse({ status: "Solver already running" });
      return true;
    }
    
    // For single item, extract from URL
    // Examples: 
    // /learn/slug/exam/HASH/name
    // /learn/slug/assignment/HASH/name
    const urlParts = window.location.pathname.split('/');
    const learnIdx = urlParts.indexOf('learn');
    if (learnIdx === -1 || urlParts.length < learnIdx + 4) {
      sendResponse({ status: "Error: Not on a valid Coursera item page." });
      return true;
    }
    
    const slug = urlParts[learnIdx + 1];
    const itemType = urlParts[learnIdx + 2];
    const itemId = urlParts[learnIdx + 3];
    
    // valid itemTypes usually are exam, quiz, assignment, peer, programming, etc.
    // If it's "home", they are on the course homepage, not an item.
    if (itemType === "home") {
      sendResponse({ status: "Error: Please navigate to a specific quiz/assignment page first, or use 'Run Full Course'." });
      return true;
    }

    chrome.runtime.sendMessage({
      action: "RUN_SINGLE_QUIZ",
      slug: slug,
      itemId: itemId,
      settings: request.settings
    }, response => {
      sendResponse({ status: response?.status || "Background quiz solver started." });
    });
      
    return true; // Keep channel open for async
  } else if (request.action === "START_FULL_COURSE_SOLVER") {
    if (state.isSolving) {
      sendResponse({ status: "Solver already running" });
      return true;
    }
    
    // Extract course slug from URL
    const urlParts = window.location.pathname.split('/');
    const learnIdx = urlParts.indexOf('learn');
    if (learnIdx === -1 || urlParts.length <= learnIdx + 1) {
      sendResponse({ status: "Error: Could not determine course slug from URL." });
      return true;
    }
    const slug = urlParts[learnIdx + 1];

    chrome.runtime.sendMessage({
      action: "RUN_FULL_COURSE",
      slug: slug,
      settings: request.settings
    }, response => {
      sendResponse({ status: response?.status || "Background orchestrator started." });
    });
    
    return true;
  } else if (request.action === "UPDATE_PROGRESS") {
    showToast(request.message);
    sendResponse({ status: "OK" });
    return true;
  }
  return true;
});

// Toast UI Logic
let toastContainer = null;

function showToast(message) {
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.id = "skipera-toast-container";
    document.body.appendChild(toastContainer);
  }
  
  const toast = document.createElement('div');
  toast.className = "skipera-toast";
  toast.textContent = message;
  
  toastContainer.appendChild(toast);
  
  // Animate in
  setTimeout(() => toast.classList.add('show'), 10);
  
  // Remove after 5 seconds
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => {
      if (toast.parentNode === toastContainer) {
        toastContainer.removeChild(toast);
      }
    }, 300);
  }, 5000);
}

