import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2, XCircle, Clock, AlertCircle, RefreshCw, Terminal } from 'lucide-react';

const LogItem = ({ log }) => {
  const [visible, setVisible] = useState(true);
  
  const msgStr = String(log.msg || "");
  const isError = log.type === "error" || msgStr.includes("ERROR") || msgStr.includes("Failed") || msgStr.includes("Error");
  const isWarning = log.type === "skip" || msgStr.includes("Skipping");
  const isCompleted = log.type === "complete" || 
    msgStr.includes("Passed") || 
    msgStr.includes("Complete") || 
    msgStr.includes("successfully") || 
    msgStr.includes("Finished");
  
  useEffect(() => {
    // ONLY completed / finished items Thanos snap out of existence
    if (!isCompleted) return;
    const timer = setTimeout(() => setVisible(false), 3500);
    return () => clearTimeout(timer);
  }, [isCompleted]);

  let colorClass = "text-green-400";
  if (isError) colorClass = "text-red-400 font-semibold";
  else if (isWarning) colorClass = "text-yellow-400";
  else if (isCompleted) colorClass = "text-emerald-400 font-semibold";
  else if (msgStr.includes("Starting") || msgStr.includes("Processing") || msgStr.includes("Triggering") || msgStr.includes("Resuming")) {
    colorClass = "text-cyan-300";
  }

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          layout
          initial={{ opacity: 0, x: -5, filter: "blur(2px)" }}
          animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
          exit={{ 
            opacity: 0, 
            scale: 0.9,
            filter: "blur(8px)",
            x: Math.random() * 20 - 10,
            y: Math.random() * -15 - 5,
            transition: { duration: 0.7, ease: "easeIn" } 
          }}
          className={`break-words ${colorClass}`}
        >
          <span className="opacity-50 mr-2 text-[9px]">{new Date(log.time).toLocaleTimeString([], { hour12: false })}</span>
          {msgStr}
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default function Dashboard({ courseSlug, onClose }) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  
  const terminalRef = useRef(null);
  const safeSlug = courseSlug || "default";

  useEffect(() => {
    // 1. Fetch initial state for THIS course
    chrome.storage.local.get(["dashboardStates"], (res) => {
      const courseState = res.dashboardStates?.[safeSlug];
      if (courseState) {
        setData(courseState);
      } else {
        setData({
          courseSlug: safeSlug,
          completionRate: 0,
          activeTask: { title: "Idle", timeElapsed: "00:00" },
          completedTasks: [],
          skippedTasks: [],
          errors: [],
          logs: []
        });
      }
      setLoading(false);
    });

    // 2. Listen for live updates for THIS course
    const messageListener = (msg) => {
      if (msg.action === "DASHBOARD_UPDATE") {
        if (!msg.slug || msg.slug === safeSlug) {
          setData(msg.state);
        }
      }
    };
    chrome.runtime.onMessage.addListener(messageListener);

    return () => {
      chrome.runtime.onMessage.removeListener(messageListener);
    };
  }, [safeSlug]);

  // Auto-scroll terminal
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [data?.logs]);

  if (error) {
    return (
      <div className="absolute inset-0 z-50 bg-background/95 backdrop-blur-md flex flex-col items-center justify-center p-6 text-center text-destructive">
        <AlertCircle size={32} className="mb-2" />
        <h3 className="font-semibold text-lg">Something went wrong</h3>
        <p className="text-sm opacity-80">{error}</p>
        <button onClick={() => window.location.reload()} className="mt-4 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium">Try Again</button>
      </div>
    );
  }

  return (
    <motion.div 
      initial={{ opacity: 0, scale: 0.9, y: 20 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95, y: 20 }}
      transition={{ duration: 0.4, type: "spring", bounce: 0.2 }}
      className="absolute inset-0 z-50 bg-background/90 backdrop-blur-xl overflow-hidden p-3 flex flex-col gap-3 border-t border-border/50 origin-bottom"
    >
      <div className="flex justify-between items-center shrink-0">
        <div className="flex items-center gap-2 overflow-hidden">
          <h2 className="text-lg font-bold tracking-tight text-foreground flex items-center gap-2 shrink-0">
            <Terminal size={18} className="text-primary" />
            Dashboard
          </h2>
          {courseSlug && (
            <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-primary/10 text-primary truncate max-w-[170px]" title={courseSlug}>
              {courseSlug}
            </span>
          )}
        </div>
        <button 
          onClick={onClose}
          className="p-1.5 rounded-full hover:bg-black/10 text-foreground transition-colors cursor-pointer"
        >
          <XCircle size={20} />
        </button>
      </div>

      {loading && !data ? (
        <div className="flex-1 flex flex-col items-center justify-center text-primary">
          <RefreshCw className="animate-spin mb-4" size={24} />
          <p className="text-xs font-medium animate-pulse">Loading metrics...</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3 h-full overflow-hidden pb-4">
          
          {/* Top Stats Row */}
          <div className="grid grid-cols-4 gap-2 shrink-0">
            {/* Completion Rate */}
            <div className="col-span-2 p-3 rounded-lg bg-card border border-border shadow-sm flex flex-col items-center justify-center gap-0.5 hover:bg-primary/5 transition-colors">
              <span className="text-2xl font-bold text-primary">{data?.completionRate || 0}%</span>
              <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Completed</span>
            </div>

            {/* Completed Count */}
            <div className="col-span-1 p-3 rounded-lg bg-card border border-border shadow-sm flex flex-col items-center justify-center gap-0.5 hover:bg-primary/5 transition-colors">
              <span className="text-xl font-bold text-primary">{data?.completedTasks?.length || 0}</span>
              <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Done</span>
            </div>

            {/* Errors */}
            <div className="col-span-1 p-3 rounded-lg bg-destructive/10 border border-destructive/20 shadow-sm flex flex-col items-center justify-center gap-0.5 group hover:bg-destructive/20 transition-colors">
              <span className="text-xl font-bold text-destructive">{data?.errors?.length || 0}</span>
              <span className="text-[10px] font-semibold text-destructive uppercase tracking-wider">Errs</span>
            </div>
          </div>

          {/* Active Task */}
          <div className="p-3 rounded-lg bg-card border border-border shadow-sm flex flex-col gap-1 relative overflow-hidden group shrink-0">
            <div className="absolute inset-0 bg-gradient-to-r from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
            <div className="flex items-center justify-between text-primary font-semibold text-[10px] uppercase tracking-wider">
              <div className="flex items-center gap-1.5">
                <Clock size={12} className="animate-pulse" />
                On Task Right Now
              </div>
              <span className="text-muted-foreground">{data?.activeTask?.timeElapsed || "00:00"}</span>
            </div>
            {/* Extremely prominent exact task name */}
            <p className="text-sm font-bold text-card-foreground leading-snug line-clamp-2">
              {(data?.activeTask?.title || "Idle").replace(/Processing item: |Triggering quiz solver for |Starting run for course: /, '')}
            </p>
          </div>

          {/* High Speed Terminal Feed */}
          <div className="flex-1 min-h-0 p-3 rounded-lg bg-black/90 dark:bg-black/80 border border-border shadow-inner flex flex-col gap-2 relative">
            <div className="absolute top-0 left-0 w-full h-4 bg-gradient-to-b from-black/90 to-transparent pointer-events-none z-10 rounded-t-lg" />
            <h4 className="text-[10px] font-bold text-primary/70 uppercase tracking-widest absolute top-2 right-3 z-20">Live Feed</h4>
            
            <div 
              ref={terminalRef}
              className="flex-1 overflow-y-auto space-y-1.5 pr-2 pt-4 pb-2 font-mono text-[11px] leading-tight text-green-400 scrollbar-thin scrollbar-thumb-white/20 scrollbar-track-transparent"
            >
              {(!data?.logs || data.logs.length === 0) ? (
                <div className="text-muted-foreground/50 text-xs text-center mt-2 font-mono">Waiting for solver stream...</div>
              ) : (
                data.logs.map((log, i) => (
                  <LogItem key={log.time + '-' + i} log={log} />
                ))
              )}
            </div>
          </div>
          
        </div>
      )}
    </motion.div>
  );
}
