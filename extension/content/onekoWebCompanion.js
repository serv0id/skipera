// Oneko Web Companion for Coursera
// Chases cursor, perches on elements, reacts to solver progress, and celebrates completions!

(function initOnekoWebCompanion() {
  if (window.__onekoInjected) return;
  window.__onekoInjected = true;

  const SPRITE_STATES = {
    idle: [[-3, -3]],
    alert: [[-7, -3]],
    scratchSelf: [[-5, 0], [-6, 0], [-7, 0]],
    scratchWallN: [[0, 0], [0, -1]],
    scratchWallS: [[-7, -1], [-6, -2]],
    scratchWallE: [[-2, -2], [-2, -3]],
    scratchWallW: [[-4, 0], [-4, -1]],
    tired: [[-3, -2]],
    sleep: [[-2, 0], [-2, -1]],
    runN: [[0, -2], [0, -3]],
    runNE: [[-1, -2], [-1, -3]],
    runE: [[-4, -2], [-4, -3]],
    runSE: [[-5, -1], [-5, -2]],
    runS: [[-5, -3], [-6, -1]],
    runSW: [[-3, 0], [-3, -1]],
    runW: [[-4, 0], [-4, -1]],
    runNW: [[-1, 0], [-1, -1]]
  };

  const LAZY_QUIPS = [
    "Did you just click me instead of studying? 🐱",
    "I'm doing all the heavy lifting here!",
    "Meow! Back to the lecture, human.",
    "100% on the quiz? You're welcome!",
    "Feed me tuna and I'll speed up the videos. 🐟",
    "Zzz... why is this week so long?",
    "Skipera + Oneko = Ultimate Degree Speedrun ⚡",
    "Purrr~ good job on completing that module! 💖"
  ];

  // Companion State
  let posX = 120;
  let posY = 120;
  let targetX = 120;
  let targetY = 120;
  let speed = 5; // Halved speed for gentle & smooth movement
  let state = "idle";
  let stateTimer = 0;
  let frameIndex = 0;
  let lastFrameTime = performance.now();
  let isSleepingInCorner = false;
  let dialogueTimer = null;

  // Create Container & Elements
  const container = document.createElement("div");
  container.id = "skipera-oneko-companion";
  container.style.cssText = `
    position: fixed;
    left: 0;
    top: 0;
    width: 32px;
    height: 32px;
    z-index: 9999999;
    pointer-events: auto;
    cursor: pointer;
    user-select: none;
    transform: translate3d(${posX}px, ${posY}px, 0);
    transition: transform 0.08s linear;
  `;

  // Sprite element
  const sprite = document.createElement("div");
  const spriteUrl = chrome.runtime.getURL("popup/oneko.gif");
  sprite.style.cssText = `
    width: 32px;
    height: 32px;
    background-image: url("${spriteUrl}");
    background-repeat: no-repeat;
    image-rendering: pixelated;
    filter: drop-shadow(0 0 6px rgba(59, 130, 246, 0.6)) drop-shadow(0 0 2px rgba(59, 130, 246, 0.8));
    transition: transform 0.15s ease, filter 0.3s ease;
  `;
  container.appendChild(sprite);

  // Thought/Dialogue Bubble
  const bubble = document.createElement("div");
  bubble.id = "skipera-oneko-bubble";
  bubble.style.cssText = `
    position: absolute;
    bottom: 38px;
    left: 50%;
    transform: translateX(-50%) scale(0.85);
    background: rgba(15, 23, 42, 0.92);
    color: #ffffff;
    font-family: system-ui, -apple-system, sans-serif;
    font-size: 11px;
    font-weight: 600;
    padding: 6px 10px;
    border-radius: 10px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.3), 0 0 0 1px rgba(255,255,255,0.15);
    white-space: nowrap;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.2s ease, transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
    z-index: 10000000;
  `;
  container.appendChild(bubble);

  document.body.appendChild(container);

  // Show Speech Bubble Helper
  function showBubble(text, duration = 3500) {
    bubble.textContent = text;
    bubble.style.opacity = "1";
    bubble.style.transform = "translateX(-50%) scale(1)";
    if (dialogueTimer) clearTimeout(dialogueTimer);
    dialogueTimer = setTimeout(() => {
      bubble.style.opacity = "0";
      bubble.style.transform = "translateX(-50%) scale(0.85)";
    }, duration);
  }

  // Celebration Sparkles
  function spawnCelebration() {
    for (let i = 0; i < 6; i++) {
      const particle = document.createElement("div");
      const icons = ["✨", "🎉", "💖", "🐾", "⭐"];
      particle.textContent = icons[Math.floor(Math.random() * icons.length)];
      particle.style.cssText = `
        position: fixed;
        left: ${posX + (Math.random() * 40 - 20)}px;
        top: ${posY + (Math.random() * 40 - 20)}px;
        font-size: 16px;
        pointer-events: none;
        z-index: 10000000;
        transition: transform 1s ease-out, opacity 1s ease-out;
      `;
      document.body.appendChild(particle);
      requestAnimationFrame(() => {
        particle.style.transform = `translate3d(${(Math.random() - 0.5) * 80}px, -${40 + Math.random() * 50}px, 0) scale(1.4)`;
        particle.style.opacity = "0";
      });
      setTimeout(() => particle.remove(), 1100);
    }
  }

  // Mouse Tracking
  let mouseMoveTimeout;
  window.addEventListener("mousemove", (e) => {
    if (isSleepingInCorner) return;
    targetX = e.clientX;
    targetY = e.clientY;
    clearTimeout(mouseMoveTimeout);
    mouseMoveTimeout = setTimeout(() => {
      // Idle after mouse stops moving
      if (state === "run") state = "idle";
    }, 2000);
  });

  // Click & Double Click Interactions
  container.addEventListener("click", () => {
    spawnCelebration();
    const quip = LAZY_QUIPS[Math.floor(Math.random() * LAZY_QUIPS.length)];
    showBubble(quip);
    sprite.style.transform = "scale(1.25) rotate(15deg)";
    setTimeout(() => {
      sprite.style.transform = "scale(1) rotate(0deg)";
    }, 200);
  });

  container.addEventListener("dblclick", () => {
    isSleepingInCorner = !isSleepingInCorner;
    if (isSleepingInCorner) {
      targetX = window.innerWidth - 60;
      targetY = window.innerHeight - 60;
      showBubble("Taking a nap in the corner... (Double-click to wake) 💤", 3000);
    } else {
      showBubble("I'm awake and ready to solve! ⚡", 2500);
    }
  });

  // Listen for solver messages from background script
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.action === "DASHBOARD_UPDATE") {
      const { updateType, data } = msg;
      if (updateType === "complete") {
        spawnCelebration();
        showBubble(`🎉 Completed: ${typeof data === "string" ? data.split(": ")[1] || data : "Item complete!"}`, 3000);
      } else if (updateType === "active") {
        if (typeof data === "string" && data.includes("lecture")) {
          showBubble("🎬 Speeding through lecture video...", 2500);
        } else if (typeof data === "string" && data.includes("quiz")) {
          showBubble("🧠 AI analyzing quiz questions...", 2500);
        }
      } else if (updateType === "completionRate") {
        if (data === 100) {
          spawnCelebration();
          showBubble("🎓 100% COURSE COMPLETED! Outstanding work!", 5000);
        }
      }
    }
  });

  // Main Companion Animation Loop
  function companionLoop(now) {
    const dt = now - lastFrameTime;

    const dx = targetX - (posX + 16);
    const dy = targetY - (posY + 16);
    const dist = Math.sqrt(dx * dx + dy * dy);

    if (dist > 30) {
      state = "run";
      const angle = Math.atan2(dy, dx);
      const moveDist = Math.min(dist, speed);
      posX += Math.cos(angle) * moveDist;
      posY += Math.sin(angle) * moveDist;
      container.style.transform = `translate3d(${posX}px, ${posY}px, 0)`;

      // Direction calculation
      const octant = Math.round(8 * angle / (2 * Math.PI) + 8) % 8;
      const dirs = ["runE", "runSE", "runS", "runSW", "runW", "runNW", "runN", "runNE"];
      currentVisualState = dirs[octant];
    } else {
      if (isSleepingInCorner) {
        currentVisualState = "sleep";
      } else {
        stateTimer += dt;
        if (stateTimer > 4000) {
          stateTimer = 0;
          currentVisualState = Math.random() > 0.5 ? "scratchSelf" : "sleep";
        } else if (stateTimer < 1500) {
          currentVisualState = "idle";
        }
      }
    }

    // Sprite frame ticking (5 FPS)
    if (dt > 180) {
      lastFrameTime = now;
      frameIndex++;
      const frames = SPRITE_STATES[currentVisualState] || SPRITE_STATES.idle;
      const curFrame = frames[frameIndex % frames.length];
      sprite.style.backgroundPosition = `${curFrame[0] * 32}px ${curFrame[1] * 32}px`;
    }

    requestAnimationFrame(companionLoop);
  }

  let currentVisualState = "idle";
  requestAnimationFrame(companionLoop);

  console.log("Skipera: Oneko Web Companion activated on Coursera.");
})();
