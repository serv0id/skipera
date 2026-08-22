import React from 'react';
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion';
import { ExternalLink } from 'lucide-react';

export function AuthorCard({ name, role, username, colorHex }) {
  const openUrl = (e) => {
    e.preventDefault();
    if (window.chrome && chrome.tabs) {
      chrome.tabs.create({ url: `https://github.com/${username}` });
    } else {
      window.open(`https://github.com/${username}`, '_blank');
    }
  };

  const x = useMotionValue(0);
  const y = useMotionValue(0);
  
  const mouseXSpring = useSpring(x, { stiffness: 500, damping: 30 });
  const mouseYSpring = useSpring(y, { stiffness: 500, damping: 30 });
  
  const rotateX = useTransform(mouseYSpring, [-0.5, 0.5], ["5deg", "-5deg"]);
  const rotateY = useTransform(mouseXSpring, [-0.5, 0.5], ["-5deg", "5deg"]);
  
  const handleMouseMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    const xPct = mouseX / width - 0.5;
    const yPct = mouseY / height - 0.5;
    x.set(xPct);
    y.set(yPct);
  };
  
  const handleMouseLeave = () => {
    x.set(0);
    y.set(0);
  };

  return (
    <motion.a
      href={`https://github.com/${username}`}
      onClick={openUrl}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{ rotateX, rotateY, transformPerspective: 800 }}
      className="flex items-center gap-2 p-1.5 px-2 md:p-2 md:px-3 rounded-xl bg-card/60 backdrop-blur-md border border-border/50 decoration-none text-inherit overflow-hidden relative group shadow-sm hover:shadow-md"
      whileHover={{ 
        scale: 1.02, 
        backgroundColor: "var(--card)", 
        borderColor: "var(--primary)"
      }}
      whileTap={{ scale: 0.98 }}
      transition={{ type: "spring", stiffness: 400, damping: 25 }}
    >
      <motion.div style={{ x: useTransform(mouseXSpring, [-0.5, 0.5], [-2, 2]), y: useTransform(mouseYSpring, [-0.5, 0.5], [-2, 2]) }} className="relative w-7 h-7 shrink-0 pointer-events-none">
        <img 
          src={`https://github.com/${username}.png`} 
          alt={name}
          className="w-full h-full rounded-full object-cover border-[1.5px] border-background shadow-sm z-10 relative transition-transform duration-300 group-hover:scale-105"
        />
        <div className="absolute -bottom-0.5 -right-0.5 w-[7px] h-[7px] rounded-full bg-primary border-[1.5px] border-background z-20"></div>
      </motion.div>
      
      <motion.div style={{ x: useTransform(mouseXSpring, [-0.5, 0.5], [-1, 1]), y: useTransform(mouseYSpring, [-0.5, 0.5], [-1, 1]) }} className="flex flex-col overflow-hidden flex-1 pointer-events-none">
        <span className="text-[10.5px] md:text-xs font-bold text-foreground truncate leading-tight tracking-tight">{name}</span>
        <span className="text-[9px] md:text-[10px] text-muted-foreground leading-tight">{role}</span>
      </motion.div>

      <motion.div 
        className="text-muted-foreground shrink-0 ml-1 pointer-events-none"
        style={{ x: useTransform(mouseXSpring, [-0.5, 0.5], [-3, 3]), y: useTransform(mouseYSpring, [-0.5, 0.5], [-3, 3]) }}
        whileHover={{ scale: 1.15, rotate: 8, color: "var(--foreground)" }}
      >
        <ExternalLink size={13} strokeWidth={2.5} />
      </motion.div>
    </motion.a>
  );
}

