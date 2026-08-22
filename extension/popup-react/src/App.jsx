import React, { useState, useEffect } from 'react';
import { Settings2, KeyRound, Sparkles, BrainCircuit, Play, LayoutGrid, Palette } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from './components/Button';
import { AuthorCard } from './components/AuthorCard';

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

  useEffect(() => {
    // Apply theme to document html element so CSS variables propagate correctly
    document.documentElement.className = theme;
  }, [theme]);

  useEffect(() => {
    if (window.chrome && chrome.storage) {
      chrome.storage.local.get(['apiKey', 'provider', 'modelName', 'theme'], (result) => {
        if (result.apiKey) setApiKey(result.apiKey);
        if (result.theme) setTheme(result.theme);
        if (result.provider) {
          setProvider(result.provider);
          setModelName(result.modelName || defaultModels[result.provider]);
        }
      });
    }
  }, []);

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
    if (!apiKey.trim()) {
      setStatus({ text: "Error: API Key required", state: "error" });
      return;
    }
    
    setStatus({ text: "Connecting to Coursera...", state: "working" });
    
    if (window.chrome && chrome.tabs) {
      try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!tab || !tab.url || !tab.url.includes("coursera.org")) {
          setStatus({ text: "Error: Must be on a Coursera tab", state: "error" });
          return;
        }

        const response = await chrome.tabs.sendMessage(tab.id, {
          action: action,
          settings: { apiKey, provider, modelName }
        });
        
        setStatus({ text: response?.status || "Solver running...", state: "working" });
      } catch (err) {
        setStatus({ text: "Error: Reload the page", state: "error" });
      }
    } else {
      // Mock for dev
      setTimeout(() => setStatus({ text: "Solver complete", state: "idle" }), 2000);
    }
  };

  return (
    <div className="flex flex-col min-h-screen relative overflow-hidden p-4">
      {/* Soft background blobs */}
      <div className="absolute top-[-20%] left-[-20%] w-[60%] h-[50%] bg-accent rounded-full blur-[60px] opacity-40 mix-blend-multiply pointer-events-none" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[70%] h-[60%] bg-primary rounded-full blur-[80px] opacity-10 mix-blend-multiply pointer-events-none" />

      {/* Theme Toggle Button */}
      <motion.button
        onClick={toggleTheme}
        whileHover={{ scale: 1.1, rotate: 15 }}
        whileTap={{ scale: 0.9 }}
        className="absolute top-4 right-4 z-20 w-8 h-8 flex items-center justify-center rounded-full bg-surface shadow-sm border border-secondary/10 text-primary hover:bg-surface/80 transition-colors cursor-pointer"
        title="Toggle Theme"
      >
        <Palette size={16} />
      </motion.button>

      <main className="relative z-10 flex flex-col flex-1 mt-6">
        
        {/* Header */}
        <header className="flex flex-col items-center justify-center mb-5 mt-1">
          <motion.div 
            className="flex items-center gap-2.5"
            initial={{ y: -10, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.5, type: "spring" }}
          >
            <motion.div 
              whileHover={{ scale: 1.15, rotate: 12 }}
              whileTap={{ scale: 0.9, rotate: -12 }}
              transition={{ type: "spring", stiffness: 400, damping: 15 }}
              className="relative w-9 h-9 rounded-xl bg-gradient-to-br from-primary to-primary-hover flex items-center justify-center shadow-lg shadow-primary/20 border border-background/20 cursor-pointer overflow-hidden group"
            >
              <motion.div 
                className="absolute inset-0 opacity-0 bg-[radial-gradient(circle_at_center,var(--color-primary-foreground)_0%,transparent_70%)] mix-blend-overlay transition-opacity duration-300 group-hover:opacity-50"
              />
              <Sparkles className="w-5 h-5 text-primary-foreground relative z-10 transition-transform duration-300 group-hover:scale-125 group-hover:text-white" />
            </motion.div>
            <div className="flex flex-col">
              <h1 className="text-xl font-extrabold tracking-tight text-primary leading-none">Skipera</h1>
              <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mt-0.5">Next-Gen Solver</span>
            </div>
          </motion.div>
        </header>

        {/* Form Container */}
        <div className="flex flex-col gap-3.5 bg-card backdrop-blur-xl rounded-2xl p-4 border border-border shadow-sm flex-1">
          
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
                <KeyRound size={13} /> API Key
              </label>
            </div>
            <textarea 
              rows={2}
              className="w-full bg-background/50 border border-input text-foreground text-[11.5px] font-mono rounded-xl px-3 py-2.5 outline-none focus:border-ring focus:ring-2 focus:ring-ring/20 transition-all shadow-sm resize-none"
              placeholder="nvapi-... or sk-..."
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>

        </div>

        {/* Action Buttons */}
        <div className="flex flex-col gap-2 mt-4">
          <Button 
            variant="primary" 
            onClick={() => executeSolver('START_SOLVER')}
            icon={<Play size={16} fill="currentColor" />}
          >
            Solve Current Quiz
          </Button>
          <Button 
            variant="secondary" 
            onClick={() => executeSolver('START_FULL_COURSE_SOLVER')}
            icon={<LayoutGrid size={16} />}
          >
            Auto-Solve Entire Course
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

      </main>

      {/* Footer Authors */}
      <footer className="mt-5 relative z-10">
        <div className="text-[9px] font-bold text-muted-foreground/60 uppercase tracking-widest text-center mb-2">Created By</div>
        <div className="grid grid-cols-2 gap-2">
          <AuthorCard name="serv0id" role="Original Creator" username="serv0id" />
          <AuthorCard name="yamantaka" role="Extension & Engine" username="yamantaka-singh" />
        </div>
      </footer>
    </div>
  );
}
