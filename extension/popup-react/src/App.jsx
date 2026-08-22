import React, { useState, useEffect } from 'react';
import { Settings2, KeyRound, Sparkles, BrainCircuit, Play, LayoutGrid, Palette, Atom, Pin, FastForward } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from './components/Button';
import { AuthorCard } from './components/AuthorCard';
import PetCat from './components/PetCat';
import Dashboard from './components/Dashboard';

const modelOptions = {
  nvidia: [
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-4-340b-instruct",
    "nvidia/nemotron-3.5-lightning-30b-a3b"
  ],
  openai: [
    "gpt-4o",
    "gpt-4o-mini",
    "o1-mini",
    "o1-preview"
  ],
  anthropic: [
    "claude-3-5-sonnet-latest",
    "claude-3-opus-20240229",
    "claude-3-haiku-20240307"
  ],
  gemini: [
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b"
  ]
};

const defaultModels = {
  nvidia: "nvidia/nemotron-3-ultra-550b-a55b",
  openai: "gpt-4o-mini",
  anthropic: "claude-3-5-sonnet-latest",
  gemini: "gemini-1.5-flash"
};

export default function App() {
  const [provider, setProvider] = useState('nvidia');
  const [modelName, setModelName] = useState(defaultModels.nvidia);
  const [apiKey, setApiKey] = useState('');
  const [status, setStatus] = useState({ text: 'Ready', state: 'idle' });
  const [theme, setTheme] = useState('theme-earth'); // Default theme
  const [showDashboard, setShowDashboard] = useState(false);
  const [completionRate, setCompletionRate] = useState(0);
  const [courseSlug, setCourseSlug] = useState('');
  const [hoveredBtn, setHoveredBtn] = useState(null);

  const isStickyMode = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('sticky') === 'true';

  useEffect(() => {
    // Apply theme to document html element so CSS variables propagate correctly
    document.documentElement.className = theme;
  }, [theme]);

  const openStickyMode = () => {
    if (isStickyMode) return;
    if (window.chrome && chrome.windows) {
      chrome.windows.create({
        url: chrome.runtime.getURL("popup/index.html?sticky=true"),
        type: "popup",
        width: 440,
        height: 640,
        top: 80,
        left: (window.screen.availWidth || 1200) - 460,
        focused: true
      }, () => {
        window.close();
      });
    } else {
      window.open(window.location.href + "?sticky=true", "skipera_sticky", "width=440,height=640");
    }
  };

  // 1. Detect current course from active tab (works in popup and sticky mode)
  useEffect(() => {
    if (window.chrome && chrome.tabs) {
      const detectSlug = async () => {
        try {
          // Check coursera tabs across windows first
          const courseraTabs = await chrome.tabs.query({ url: "*://*.coursera.org/*" });
          const targetTab = courseraTabs?.find(t => t.active) || courseraTabs?.[0];
          if (targetTab?.url) {
            const urlObj = new URL(targetTab.url);
            const urlParts = urlObj.pathname.split('/');
            const learnIdx = urlParts.indexOf('learn');
            if (learnIdx !== -1 && urlParts[learnIdx + 1]) {
              setCourseSlug(urlParts[learnIdx + 1]);
              return;
            }
          }
          
          // Fallback to active tab in current window
          const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
          if (tab?.url) {
            const urlObj = new URL(tab.url);
            const urlParts = urlObj.pathname.split('/');
            const learnIdx = urlParts.indexOf('learn');
            if (learnIdx !== -1 && urlParts[learnIdx + 1]) {
              setCourseSlug(urlParts[learnIdx + 1]);
            }
          }
        } catch (e) {
          console.warn("Could not detect course tab", e);
        }
      };

      detectSlug();
      const tabActivatedListener = () => detectSlug();
      chrome.tabs.onActivated?.addListener(tabActivatedListener);
      return () => chrome.tabs.onActivated?.removeListener(tabActivatedListener);
    }
  }, []);

  // 2. Load settings and course-specific completion rate
  useEffect(() => {
    if (window.chrome && chrome.storage) {
      chrome.storage.local.get(['apiKey', 'provider', 'modelName', 'theme', 'dashboardStates'], (result) => {
        if (result.apiKey) setApiKey(result.apiKey);
        if (result.theme) setTheme(result.theme);
        if (result.provider) {
          setProvider(result.provider);
          setModelName(result.modelName || defaultModels[result.provider]);
        }
        if (courseSlug && result.dashboardStates?.[courseSlug]) {
          setCompletionRate(result.dashboardStates[courseSlug].completionRate || 0);
        } else if (!courseSlug) {
          setCompletionRate(0);
        }
      });

      const messageListener = (msg) => {
        if (msg.action === "DASHBOARD_UPDATE") {
          const currentSlug = courseSlug || "default";
          if (!msg.slug || msg.slug === currentSlug) {
            setCompletionRate(msg.state?.completionRate || 0);
          }
        }
      };
      chrome.runtime.onMessage.addListener(messageListener);
      return () => chrome.runtime.onMessage.removeListener(messageListener);
    }
  }, [courseSlug]);

  useEffect(() => {
    if (window.chrome && chrome.storage) {
      chrome.storage.local.set({ apiKey, provider, modelName, theme });
    }
  }, [apiKey, provider, modelName, theme]);

  const handleProviderChange = (e) => {
    const newProv = e.target.value;
    setProvider(newProv);
    setModelName(defaultModels[newProv] || modelOptions[newProv][0]);
  };

  const themes = ['theme-earth', 'theme-fire', 'theme-sage'];

  const toggleTheme = (e) => {
    const nextThemeIndex = (themes.indexOf(theme) + 1) % themes.length;
    const nextTheme = themes[nextThemeIndex];

    if (!document.startViewTransition) {
      document.documentElement.className = nextTheme;
      setTheme(nextTheme);
      return;
    }

    const x = e?.clientX ?? window.innerWidth - 30;
    const y = e?.clientY ?? 30;
    const endRadius = Math.hypot(
      Math.max(x, window.innerWidth - x),
      Math.max(y, window.innerHeight - y)
    );

    const transition = document.startViewTransition(() => {
      document.documentElement.className = nextTheme;
      setTheme(nextTheme);
    });

    transition.ready.then(() => {
      if (nextTheme === 'theme-fire') {
        // Fire Theme: Deep Z-Axis Push (iOS App Switcher Style)
        // Old view shrinks and blurs backward, new view scales down and snaps into focus
        document.documentElement.animate(
          {
            filter: ['blur(0px)', 'blur(12px)'],
            opacity: [1, 0],
            transform: ['scale(1)', 'scale(0.92)']
          },
          { duration: 600, easing: 'cubic-bezier(0.32, 0.72, 0, 1)', pseudoElement: '::view-transition-old(root)' }
        );
        document.documentElement.animate(
          {
            filter: ['blur(12px)', 'blur(0px)'],
            opacity: [0, 1],
            transform: ['scale(1.08)', 'scale(1)']
          },
          { duration: 600, easing: 'cubic-bezier(0.32, 0.72, 0, 1)', pseudoElement: '::view-transition-new(root)' }
        );
      } else if (nextTheme === 'theme-sage') {
        // Sage Theme: Parallax Navigation Glide (iOS Settings Push)
        // Smooth horizontal slide with a parallax trailing effect
        document.documentElement.animate(
          {
            opacity: [1, 0],
            transform: ['translateX(0px)', 'translateX(-30px)']
          },
          { duration: 500, easing: 'cubic-bezier(0.32, 0.72, 0, 1)', pseudoElement: '::view-transition-old(root)' }
        );
        document.documentElement.animate(
          {
            opacity: [0, 1],
            transform: ['translateX(30px)', 'translateX(0px)']
          },
          { duration: 500, easing: 'cubic-bezier(0.32, 0.72, 0, 1)', pseudoElement: '::view-transition-new(root)' }
        );
      } else {
        // Earth Theme: Spring Modal Pop (iOS Sheet Presentation)
        // New view pops up from the bottom slightly and settles into place
        document.documentElement.animate(
          {
            opacity: [1, 0],
            transform: ['scale(1)', 'scale(0.96)']
          },
          { duration: 550, easing: 'cubic-bezier(0.32, 0.72, 0, 1)', pseudoElement: '::view-transition-old(root)' }
        );
        document.documentElement.animate(
          {
            opacity: [0, 1],
            transform: ['translateY(24px) scale(0.98)', 'translateY(0px) scale(1)']
          },
          { duration: 550, easing: 'cubic-bezier(0.32, 0.72, 0, 1)', pseudoElement: '::view-transition-new(root)' }
        );
      }
    });
  };

  const executeSolver = async (action) => {
    const isVideosOnly = action === 'START_VIDEOS_ONLY' || !apiKey.trim();
    
    if (action === 'START_FULL_COURSE_SOLVER' && !apiKey.trim()) {
      setStatus({ text: "No API Key: Running Videos & Readings only", state: "working" });
    } else if (action === 'START_VIDEOS_ONLY') {
      setStatus({ text: "Fast-forwarding videos & readings...", state: "working" });
    } else if (!apiKey.trim()) {
      setStatus({ text: "Error: API Key required for AI quiz solver", state: "error" });
      return;
    }
    
    setShowDashboard(true);
    
    if (window.chrome && chrome.tabs) {
      try {
        let targetTab = null;
        
        // Find Coursera tab (active one preferred, cross-window compatible for sticky mode)
        const courseraTabs = await chrome.tabs.query({ url: "*://*.coursera.org/*" });
        if (courseraTabs && courseraTabs.length > 0) {
          targetTab = courseraTabs.find(t => t.active) || courseraTabs[0];
        } else {
          const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
          targetTab = tab;
        }

        if (!targetTab || !targetTab.url || !targetTab.url.includes("coursera.org")) {
          setStatus({ text: "Error: Must have an open Coursera tab", state: "error" });
          return;
        }

        const response = await chrome.tabs.sendMessage(targetTab.id, {
          action: action,
          settings: { 
            apiKey, 
            provider, 
            modelName, 
            videosOnly: isVideosOnly 
          }
        });
        
        if (response?.error || response?.status === "Error" || response?.status?.startsWith("Error")) {
          setStatus({ text: response?.error || response?.status, state: "error" });
        } else {
          setStatus({ 
            text: isVideosOnly ? "Fast-forwarding videos & readings..." : (response?.status || "Solver running..."), 
            state: "working" 
          });
        }
      } catch (err) {
        setStatus({ text: "Error: Reload the Coursera page", state: "error" });
      }
    } else {
      // Mock for dev
      setTimeout(() => setStatus({ text: "Completed successfully", state: "idle" }), 2000);
    }
  };

  const [mouseTrail, setMouseTrail] = useState({ x: -100, y: -100 });

  const handlePointerMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setMouseTrail({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top
    });
  };

  return (
    <div 
      onPointerMove={handlePointerMove}
      className="flex flex-col min-h-screen relative overflow-hidden p-4 md:p-8 w-full max-w-5xl mx-auto select-none group"
    >
      {/* Dynamic Cursor Illumination Spotlight & Laser Glow */}
      <div 
        className="pointer-events-none absolute -inset-px transition-opacity duration-300 opacity-70"
        style={{
          background: `radial-gradient(400px circle at ${mouseTrail.x}px ${mouseTrail.y}px, var(--color-primary) 0%, transparent 80%)`,
          opacity: 0.12,
          mixBlendMode: 'screen'
        }}
      />
      <div 
        className="pointer-events-none absolute w-3 h-3 rounded-full bg-primary/40 blur-[2px] transition-transform duration-75 ease-out"
        style={{
          transform: `translate3d(${mouseTrail.x - 6}px, ${mouseTrail.y - 6}px, 0)`,
          boxShadow: '0 0 12px var(--color-primary)'
        }}
      />

      {/* Dashboard Overlay */}
      <AnimatePresence>
        {showDashboard && (
          <Dashboard courseSlug={courseSlug} onClose={() => setShowDashboard(false)} />
        )}
      </AnimatePresence>

      <PetCat />
      {/* Soft background blobs */}
      <div className="absolute top-[-20%] left-[-20%] w-[60%] h-[50%] bg-accent rounded-full blur-[60px] opacity-40 mix-blend-multiply pointer-events-none" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[70%] h-[60%] bg-primary rounded-full blur-[80px] opacity-10 mix-blend-multiply pointer-events-none" />

      <main className="relative z-10 flex flex-col flex-1 mt-6 md:mt-10 gap-6 md:grid md:grid-cols-12 md:items-start">
        
        {/* Header */}
        <header className="flex items-center justify-between md:col-span-12 mb-3 md:mb-6">
          <motion.div 
            className="flex items-center gap-3"
            initial={{ y: -10, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.5, type: "spring" }}
          >
            {/* Interactive Logo */}
            <motion.div 
              className="w-11 h-11 bg-primary/10 text-primary rounded-xl flex items-center justify-center cursor-pointer shadow-sm border border-primary/15"
              whileHover={{ scale: 1.15, rotate: 180, transition: { type: "spring", stiffness: 400, damping: 10 } }}
              whileTap={{ scale: 0.85, rotate: -180 }}
            >
              <motion.div whileHover={{ scale: 1.2 }}>
                <Atom size={24} strokeWidth={2.5} />
              </motion.div>
            </motion.div>
            <div className="flex flex-col">
              <h1 className="text-2xl font-extrabold tracking-tight text-primary leading-none">Skipera</h1>
              <span className="text-[10.5px] font-semibold text-muted-foreground uppercase tracking-wider mt-0.5">Next-Gen Solver</span>
            </div>
          </motion.div>

          {/* Action Buttons Toolbar with Dynamic Hover Tooltips */}
          <div className="flex items-center gap-2.5">
            
            {/* 1. Pin / Stick Me Button */}
            <div className="relative flex flex-col items-center">
              <motion.button 
                onClick={openStickyMode}
                onMouseEnter={() => setHoveredBtn('pin')}
                onMouseLeave={() => setHoveredBtn(null)}
                whileHover={{ scale: 1.15, rotate: isStickyMode ? 0 : 25, transition: { type: "spring", stiffness: 400, damping: 12 } }}
                whileTap={{ scale: 0.85, rotate: -30 }}
                className={`w-11 h-11 rounded-xl flex items-center justify-center transition-all cursor-pointer shadow-sm border ${
                  isStickyMode 
                    ? "bg-primary text-primary-foreground border-primary shadow-md shadow-primary/30" 
                    : "bg-primary/10 hover:bg-primary/20 text-primary border-primary/15 hover:border-primary/30"
                }`}
                aria-label="Pin window"
              >
                <Pin size={22} strokeWidth={2.2} className={isStickyMode ? "fill-current" : ""} />
              </motion.button>
              
              <AnimatePresence>
                {hoveredBtn === 'pin' && (
                  <motion.div 
                    initial={{ opacity: 0, y: 6, scale: 0.85 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 4, scale: 0.85 }}
                    transition={{ duration: 0.15 }}
                    className="absolute top-13 px-2.5 py-1 rounded-lg bg-card/95 text-foreground border border-border shadow-xl text-[11px] font-bold whitespace-nowrap pointer-events-none z-50 backdrop-blur-md"
                  >
                    {isStickyMode ? "Pinned 🧲📌" : "Stick Me !! 🧲📌"}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* 2. Completion Percentage / Dashboard Button */}
            <div className="relative flex flex-col items-center">
              <motion.button 
                onClick={() => setShowDashboard(true)}
                onMouseEnter={() => setHoveredBtn('dashboard')}
                onMouseLeave={() => setHoveredBtn(null)}
                whileHover={{ scale: 1.15, rotate: 12, transition: { type: "spring", stiffness: 400, damping: 12 } }}
                whileTap={{ scale: 0.85, rotate: -15 }}
                className="w-11 h-11 rounded-xl bg-primary/10 hover:bg-primary/20 text-primary flex items-center justify-center transition-all cursor-pointer relative shadow-sm border border-primary/15 hover:border-primary/30"
                aria-label="View Dashboard"
              >
                <svg className="w-9 h-9 transform -rotate-90 absolute inset-0 m-auto" viewBox="0 0 36 36">
                  <circle cx="18" cy="18" r="15" fill="none" className="stroke-primary/20" strokeWidth="3" />
                  <circle 
                    cx="18" cy="18" r="15" 
                    fill="none" 
                    className="stroke-primary transition-all duration-500 ease-out" 
                    strokeWidth="3" 
                    strokeDasharray="94.25" 
                    strokeDashoffset={94.25 - (94.25 * completionRate) / 100} 
                    strokeLinecap="round" 
                  />
                </svg>
                <span className="text-[10px] font-extrabold z-10 select-none">{completionRate}%</span>
              </motion.button>
              
              <AnimatePresence>
                {hoveredBtn === 'dashboard' && (
                  <motion.div 
                    initial={{ opacity: 0, y: 6, scale: 0.85 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 4, scale: 0.85 }}
                    transition={{ duration: 0.15 }}
                    className="absolute top-13 px-2.5 py-1 rounded-lg bg-card/95 text-foreground border border-border shadow-xl text-[11px] font-bold whitespace-nowrap pointer-events-none z-50 backdrop-blur-md"
                  >
                    Dashboard 📊
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* 3. Theme Toggle Button */}
            <div className="relative flex flex-col items-center">
              <motion.button 
                onClick={toggleTheme}
                onMouseEnter={() => setHoveredBtn('theme')}
                onMouseLeave={() => setHoveredBtn(null)}
                whileHover={{ scale: 1.15, rotate: 90, transition: { type: "spring", stiffness: 400, damping: 12 } }}
                whileTap={{ scale: 0.85, rotate: 270 }}
                className="w-11 h-11 rounded-xl bg-primary/10 hover:bg-primary/20 text-primary flex items-center justify-center transition-all cursor-pointer shadow-sm border border-primary/15 hover:border-primary/30"
                aria-label="Toggle Theme"
              >
                <Palette size={22} strokeWidth={2.2} />
              </motion.button>
              
              <AnimatePresence>
                {hoveredBtn === 'theme' && (
                  <motion.div 
                    initial={{ opacity: 0, y: 6, scale: 0.85 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 4, scale: 0.85 }}
                    transition={{ duration: 0.15 }}
                    className="absolute top-13 px-2.5 py-1 rounded-lg bg-card/95 text-foreground border border-border shadow-xl text-[11px] font-bold whitespace-nowrap pointer-events-none z-50 backdrop-blur-md"
                  >
                    Theme 🎨
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

          </div>
        </header>

        {/* Form Container */}
        <div className="flex flex-col gap-4 bg-card backdrop-blur-xl rounded-2xl p-5 md:p-6 border border-border shadow-sm flex-1 md:col-span-7 lg:col-span-8 h-full">
          
          {/* Provider Select */}
          <div className="flex flex-col gap-1.5">
            <label className="text-[10.5px] font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-1.5 ml-0.5">
              <BrainCircuit size={13} /> Provider
            </label>
            <div className="relative">
              <select 
                className="w-full appearance-none bg-background/50 border border-input text-foreground text-[12.5px] font-medium rounded-xl px-3 py-2.5 outline-none focus:border-ring focus:ring-2 focus:ring-ring/20 transition-all shadow-sm"
                value={provider}
                onChange={handleProviderChange}
              >
                <option value="nvidia">NVIDIA NIM (Recommended)</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="gemini">Google Gemini</option>
              </select>
            </div>
          </div>

          {/* Model Select */}
          <div className="flex flex-col gap-1.5">
            <label className="text-[10.5px] font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-1.5 ml-0.5">
              <Settings2 size={13} /> Architecture
            </label>
            <div className="relative">
              <select 
                className="w-full appearance-none bg-background/50 border border-input text-foreground text-[12.5px] font-medium rounded-xl px-3 py-2.5 outline-none focus:border-ring focus:ring-2 focus:ring-ring/20 transition-all shadow-sm"
                value={modelName}
                onChange={(e) => setModelName(e.target.value)}
              >
                {modelOptions[provider]?.map(opt => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            </div>
          </div>

          {/* API Key */}
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between items-end">
              <label className="text-[10.5px] font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-1.5 ml-0.5">
                <KeyRound size={13} /> API Key <span className="text-[9px] font-medium text-muted-foreground/70 lowercase tracking-normal">(optional for videos & readings)</span>
              </label>
            </div>
            <textarea 
              rows={2}
              className="w-full bg-background/50 border border-input text-foreground text-[11.5px] font-mono rounded-xl px-3 py-2.5 outline-none focus:border-ring focus:ring-2 focus:ring-ring/20 transition-all shadow-sm resize-none"
              placeholder="nvapi-... or sk-... (Leave blank for Videos/Readings only)"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>

        </div>

        {/* Actions & Status Container */}
        <div className="flex flex-col gap-4 md:col-span-5 lg:col-span-4 h-full">
          {/* Action Buttons */}
          <div className="flex flex-col gap-3 bg-card/50 backdrop-blur-xl rounded-2xl p-5 md:p-6 border border-border/50 shadow-sm">
            <Button 
              variant="primary" 
              onClick={() => executeSolver('START_VIDEOS_ONLY')}
              icon={<FastForward size={16} />}
            >
              <div className="flex items-center justify-between w-full">
                <span>Fast-Forward Videos & Readings</span>
                <span className="text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded bg-primary-foreground/20 text-primary-foreground tracking-wider ml-1">
                  No Key Needed
                </span>
              </div>
            </Button>
            <Button 
              variant="secondary" 
              onClick={() => executeSolver('START_FULL_COURSE_SOLVER')}
              icon={<Sparkles size={16} />}
            >
              Auto-Solve Entire Course (with AI)
            </Button>
          </div>

        {/* Status Indicator */}
        <AnimatePresence>
          {status.state !== 'idle' && (
            <motion.div 
              initial={{ opacity: 0, height: 0, marginTop: 0 }}
              animate={{ opacity: 1, height: 'auto', marginTop: 12 }}
              exit={{ opacity: 0, height: 0, marginTop: 0 }}
              className="overflow-hidden"
            >
              <div className="flex items-center gap-2.5 bg-card border border-border rounded-lg px-3 py-2 text-[11.5px] font-medium text-foreground shadow-sm">
                <div className="relative flex items-center justify-center shrink-0">
                  <div className={`w-2 h-2 rounded-full ${status.state === 'error' ? 'bg-destructive' : 'bg-primary'}`} />
                  {status.state === 'working' && (
                    <motion.div 
                      className="absolute inset-0 rounded-full bg-primary"
                      animate={{ scale: [1, 2.5], opacity: [0.5, 0] }}
                      transition={{ duration: 1.2, repeat: Infinity, ease: "easeOut" }}
                    />
                  )}
                </div>
                <span className="truncate">{status.text}</span>
              </div>
            </motion.div>
          )}
          </AnimatePresence>
        </div>

      </main>

      {/* Footer Authors */}
      <footer className="mt-auto sticky bottom-0 z-30 pb-4 pt-4 bg-background/90 backdrop-blur-md">
        <div className="text-[9px] font-bold text-muted-foreground/60 uppercase tracking-widest text-center mb-2">Created By</div>
        <div className="grid grid-cols-2 gap-2">
          <AuthorCard name="serv0id" role="Original Creator" username="serv0id" />
          <AuthorCard name="Mrityunjay" role="Extension & Engine" username="yamantaka-singh" />
        </div>
      </footer>
    </div>
  );
}
