import React from 'react';
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export function Button({ 
  children, 
  variant = 'primary', 
  className, 
  icon,
  ...props 
}) {
  const baseStyles = "relative w-full py-2.5 px-4 rounded-lg text-sm font-semibold flex items-center justify-center gap-2 overflow-hidden outline-none";
  
  const variants = {
    primary: "bg-primary/80 backdrop-blur-md text-primary-foreground hover:bg-primary/90 shadow-md shadow-primary/20 border border-primary/30",
    secondary: "bg-secondary/80 backdrop-blur-md text-secondary-foreground border border-border hover:bg-secondary/90 shadow-sm"
  };

  const x = useMotionValue(0);
  const y = useMotionValue(0);
  
  const mouseXSpring = useSpring(x, { stiffness: 500, damping: 30 });
  const mouseYSpring = useSpring(y, { stiffness: 500, damping: 30 });
  
  const rotateX = useTransform(mouseYSpring, [-0.5, 0.5], ["7deg", "-7deg"]);
  const rotateY = useTransform(mouseXSpring, [-0.5, 0.5], ["-7deg", "7deg"]);
  
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
    <motion.button
      style={{ rotateX, rotateY, transformPerspective: 800 }}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      transition={{ type: "spring", stiffness: 400, damping: 25 }}
      className={cn(
        baseStyles,
        "backdrop-blur-md bg-opacity-80 border border-primary/20",
        variants[variant], 
        className
      )}
      {...props}
    >
      <div className="relative z-10 flex items-center justify-center gap-2 pointer-events-none">
        {icon && <motion.span style={{ x: useTransform(mouseXSpring, [-0.5, 0.5], [-3, 3]), y: useTransform(mouseYSpring, [-0.5, 0.5], [-3, 3]) }} className="flex-shrink-0">{icon}</motion.span>}
        <motion.span style={{ x: useTransform(mouseXSpring, [-0.5, 0.5], [-2, 2]), y: useTransform(mouseYSpring, [-0.5, 0.5], [-2, 2]) }}>{children}</motion.span>
      </div>
      
      {variant === 'primary' && (
        <motion.div 
          className="absolute -inset-8 z-0 opacity-30 bg-[conic-gradient(from_0deg,transparent,var(--color-primary-foreground),transparent)] blur-xl mix-blend-overlay pointer-events-none"
          initial={{ rotate: 0 }}
          animate={{ rotate: 360 }}
          transition={{ duration: 6, ease: "linear", repeat: Infinity }}
          whileHover={{ opacity: 0.8, scale: 1.2, filter: "blur(16px)" }}
        />
      )}
    </motion.button>
  );
}
