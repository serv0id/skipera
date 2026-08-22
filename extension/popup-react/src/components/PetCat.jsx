import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Matter from 'matter-js';

const LAZY_PHRASES = [
  "Here again to give me all the work?",
  "Can't you Google it?",
  "I was sleeping...",
  "Fine, I'll solve it.",
  "Are we done yet?",
  "Zzz... oh, what now?"
];

// Oneko sprite offsets (32x32 grid)
const SPRITE_STATES = {
  idle: [[-3, -3]],
  sleep: [[-2, 0], [-2, -1]],
  runRight: [[-4, -2], [-4, -3]],
  runLeft: [[-4, 0], [-4, -1]]
};

export default function PetCat() {
  const containerRef = useRef(null);
  const spriteRef = useRef(null);
  const [dialogue, setDialogue] = useState(null);

  // Constants
  const CAT_SIZE = 32;
  const CAT_RADIUS = 16;
  const WANDER_FORCE = 0.00005; // Very small for rigid body force
  const MAX_SPEED = 1.5;

  // Matter.js references
  const engineRef = useRef(null);
  const catBodyRef = useRef(null);
  const obstaclesRef = useRef([]);

  // State machine logic
  const wanderAngle = useRef(Math.random() * Math.PI * 2);
  const state = useRef('walk');
  const stateTimer = useRef(4000);

  useEffect(() => {
    // 1. Setup Matter.js Engine
    const engine = Matter.Engine.create();
    engine.world.gravity.y = 0; // Top-down view, no gravity
    engine.world.gravity.x = 0;
    engineRef.current = engine;

    // Create the cat rigid body
    const cat = Matter.Bodies.circle(100, 100, CAT_RADIUS, {
      frictionAir: 0.1, // High air friction for top-down walking
      restitution: 0.5, // Bounciness
      mass: 1
    });
    catBodyRef.current = cat;
    Matter.World.add(engine.world, cat);

    // 2. Map DOM Obstacles to Static Bodies
    const mapObstacles = () => {
      // Remove old obstacles
      if (obstaclesRef.current.length > 0) {
        Matter.World.remove(engine.world, obstaclesRef.current);
      }
      
      const elements = document.querySelectorAll('.card, button, input');
      const newObstacles = [];
      
      elements.forEach(el => {
        const rect = el.getBoundingClientRect();
        // Skip elements with 0 size
        if (rect.width === 0 || rect.height === 0) return;
        
        // Matter.js positions bodies by their center
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        
        const body = Matter.Bodies.rectangle(centerX, centerY, rect.width, rect.height, {
          isStatic: true,
          restitution: 0.1
        });
        newObstacles.push(body);
      });
      
      // Add boundaries
      const thickness = 50;
      const w = window.innerWidth;
      const h = window.innerHeight;
      
      newObstacles.push(
        Matter.Bodies.rectangle(w / 2, -thickness / 2, w, thickness, { isStatic: true }), // Top
        Matter.Bodies.rectangle(w / 2, h + thickness / 2, w, thickness, { isStatic: true }), // Bottom
        Matter.Bodies.rectangle(-thickness / 2, h / 2, thickness, h, { isStatic: true }), // Left
        Matter.Bodies.rectangle(w + thickness / 2, h / 2, thickness, h, { isStatic: true }) // Right
      );

      Matter.World.add(engine.world, newObstacles);
      obstaclesRef.current = newObstacles;
    };

    // Initial map and listen for resizes
    mapObstacles();
    window.addEventListener('resize', mapObstacles);

    // 3. Render and Physics Loop
    let animationFrameId;
    let lastTime = performance.now();
    let spriteTimer = 0;
    let frameIndex = 0;

    const gameLoop = (time) => {
      const dt = time - lastTime;
      lastTime = time;

      // Update Matter Physics Engine (fixed timestep approximation)
      Matter.Engine.update(engine, dt);

      // State Machine (Walk vs Sleep)
      if (!dialogue) {
        stateTimer.current -= dt;
        if (stateTimer.current <= 0) {
          if (state.current === 'sleep') {
            state.current = 'walk';
            stateTimer.current = 4000 + Math.random() * 5000;
          } else {
            state.current = 'sleep';
            stateTimer.current = 5000 + Math.random() * 10000;
          }
        }
      } else {
        state.current = 'idle';
      }

      // Apply Steering Forces
      if (state.current === 'walk') {
        // Slowly change wander angle
        wanderAngle.current += (Math.random() * 0.4 - 0.2);
        
        const forceX = Math.cos(wanderAngle.current) * WANDER_FORCE;
        const forceY = Math.sin(wanderAngle.current) * WANDER_FORCE;
        
        Matter.Body.applyForce(cat, cat.position, { x: forceX, y: forceY });
        
        // Cap speed
        const speed = Matter.Vector.magnitude(cat.velocity);
        if (speed > MAX_SPEED) {
          Matter.Body.setVelocity(cat, Matter.Vector.mult(Matter.Vector.normalise(cat.velocity), MAX_SPEED));
        }
      } else {
        // Slow down to sleep
        if (Matter.Vector.magnitude(cat.velocity) > 0.01) {
          Matter.Body.setVelocity(cat, Matter.Vector.mult(cat.velocity, 0.9)); // Friction
        }
      }

      // Z-Depth Scaling Logic
      // Scale from 0.8 (top of screen) to 1.3 (bottom of screen)
      const depthRatio = Math.max(0, Math.min(1, cat.position.y / window.innerHeight));
      const scale = 0.8 + depthRatio * 0.5;
      
      // Update DOM visually
      if (containerRef.current) {
        containerRef.current.style.transform = `translate3d(${cat.position.x - CAT_RADIUS}px, ${cat.position.y - CAT_RADIUS}px, 0) scale(${scale})`;
        // Also update Z-index so it renders behind things when high up, and in front when low down
        containerRef.current.style.zIndex = Math.floor(depthRatio * 100) + 10;
      }

      // Sprite Animation (5 FPS)
      spriteTimer += dt;
      if (spriteTimer > 200) {
        spriteTimer = 0;
        frameIndex++;
        
        let visualState = 'idle';
        if (state.current === 'sleep') visualState = 'sleep';
        else if (state.current === 'walk') {
          visualState = cat.velocity.x >= 0 ? 'runRight' : 'runLeft';
        }

        const frames = SPRITE_STATES[visualState] || SPRITE_STATES.idle;
        const currentFrame = frames[frameIndex % frames.length];
        
        if (spriteRef.current) {
          spriteRef.current.style.backgroundPosition = `${currentFrame[0] * 32}px ${currentFrame[1] * 32}px`;
        }
      }

      animationFrameId = requestAnimationFrame(gameLoop);
    };

    animationFrameId = requestAnimationFrame(gameLoop);

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', mapObstacles);
      Matter.Engine.clear(engine);
    };
  }, [dialogue]);

  const handleTickle = () => {
    if (dialogue) return;
    
    // Apply a sudden impulse force (bounce away)
    if (catBodyRef.current) {
      const forceX = (Math.random() > 0.5 ? 1 : -1) * 0.005;
      const forceY = (Math.random() > 0.5 ? 1 : -1) * 0.005;
      Matter.Body.applyForce(catBodyRef.current, catBodyRef.current.position, { x: forceX, y: forceY });
    }
    
    const phrase = LAZY_PHRASES[Math.floor(Math.random() * LAZY_PHRASES.length)];
    setDialogue(phrase);
    
    setTimeout(() => {
      setDialogue(null);
      state.current = 'walk'; 
      stateTimer.current = 3000;
    }, 3000);
  };

  return (
    <div
      ref={containerRef}
      className="fixed top-0 left-0 flex flex-col items-center justify-center cursor-pointer pointer-events-auto origin-bottom"
      style={{ willChange: 'transform' }}
    >
      <AnimatePresence>
        {dialogue && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.8 }}
            animate={{ opacity: 1, y: -15, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            className="absolute bottom-full mb-2 w-[120px] bg-card/90 backdrop-blur-md text-foreground text-[10px] font-medium p-2 rounded-xl shadow-lg border border-border/50 text-center leading-tight pointer-events-none"
            style={{ 
              transformOrigin: 'bottom center',
              // Inverse scale the dialogue so it doesn't get massive when the cat is at the bottom
              transform: 'scale(0.8)' 
            }}
          >
            {dialogue}
            <div className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-l-[6px] border-r-[6px] border-t-[8px] border-l-transparent border-r-transparent border-t-card/90" />
          </motion.div>
        )}
      </AnimatePresence>

      <div 
        ref={spriteRef}
        onClick={handleTickle}
        style={{
          width: '32px',
          height: '32px',
          backgroundImage: 'url(./oneko.gif)',
          imageRendering: 'pixelated',
          filter: 'drop-shadow(0 0 8px var(--color-primary)) drop-shadow(0 0 2px var(--color-primary))',
          transition: 'filter 0.5s ease',
        }}
        className="active:scale-90 hover:scale-110"
      />
    </div>
  );
}
