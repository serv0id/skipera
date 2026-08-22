import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Matter from 'matter-js';

const LAZY_PHRASES = [
  "Here again to give me all the work?",
  "Can't you Google it?",
  "I was sleeping...",
  "Fine, I'll solve it.",
  "Are we done yet?",
  "Zzz... oh, what now?",
  "Feed me tuna and I'll speed up!",
  "100% on the quiz? You're welcome."
];

// Oneko sprite offsets (32x32 grid — verified against actual sprite sheet)
// NOTE: This sprite sheet has E/W and diagonals mirrored vs the standard reference.
// col=3 (bg-pos -96px) = cat running LEFT = runW
// col=4 (bg-pos -128px) = cat running RIGHT = runE
// col=0 (bg-pos 0px) = NW diagonal (not NE)
// col=1 (bg-pos -32px) = NE diagonal (not NW)
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
  runN:  [[-1, -2], [-1, -3]],
  runNE: [[-1, 0],  [-1, -1]],   // was NW in reference — actual NE in this sheet
  runE:  [[-4, -2], [-4, -3]],   // was W in reference  — actual E  in this sheet
  runSE: [[-5, -3], [-6, -1]],   // was SW in reference — actual SE in this sheet
  runS:  [[-6, -3], [-7, -2]],
  runSW: [[-5, -1], [-5, -2]],   // was SE in reference — actual SW in this sheet
  runW:  [[-3, 0],  [-3, -1]],   // was E  in reference — actual W  in this sheet
  runNW: [[0, -2],  [0, -3]],    // was NE in reference — actual NW in this sheet
};

export default function PetCat() {
  const containerRef = useRef(null);
  const spriteRef = useRef(null);
  const [dialogue, setDialogue] = useState(null);
  const [hearts, setHearts] = useState([]);

  // Constants
  const CAT_SIZE = 32;
  const CAT_RADIUS = 16;
  const WANDER_FORCE = 0.00003;
  const CHASE_FORCE = 0.000075;
  const MAX_SPEED = 1.1;

  // Matter.js references
  const engineRef = useRef(null);
  const catBodyRef = useRef(null);
  const obstaclesRef = useRef([]);

  // Mouse tracking
  const mousePos = useRef({ x: 200, y: 200, lastMove: 0, isActive: false });

  // State machine logic
  const wanderAngle = useRef(Math.random() * Math.PI * 2);
  const state = useRef('walk');
  const stateTimer = useRef(3000);

  useEffect(() => {
    // Mouse move tracker
    const handleMouseMove = (e) => {
      mousePos.current.x = e.clientX;
      mousePos.current.y = e.clientY;
      mousePos.current.lastMove = performance.now();
      mousePos.current.isActive = true;
    };
    window.addEventListener('pointermove', handleMouseMove);

    // 1. Setup Matter.js Engine
    const engine = Matter.Engine.create({
      enableSleeping: false
    });
    engine.world.gravity.y = 0;
    engine.world.gravity.x = 0;
    engineRef.current = engine;

    // Create the cat rigid body
    const cat = Matter.Bodies.circle(120, 120, CAT_RADIUS, {
      frictionAir: 0.08,
      restitution: 0.4,
      mass: 1
    });
    catBodyRef.current = cat;
    Matter.World.add(engine.world, cat);

    // 2. Map DOM Obstacles to Static Bodies
    const mapObstacles = () => {
      if (obstaclesRef.current.length > 0) {
        Matter.World.remove(engine.world, obstaclesRef.current);
      }
      
      const elements = document.querySelectorAll('.card, button, textarea, select');
      const newObstacles = [];
      
      elements.forEach(el => {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;
        
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        
        const body = Matter.Bodies.rectangle(centerX, centerY, rect.width * 0.9, rect.height * 0.9, {
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
        Matter.Bodies.rectangle(w / 2, -thickness / 2, w, thickness, { isStatic: true }),
        Matter.Bodies.rectangle(w / 2, h + thickness / 2, w, thickness, { isStatic: true }),
        Matter.Bodies.rectangle(-thickness / 2, h / 2, thickness, h, { isStatic: true }),
        Matter.Bodies.rectangle(w + thickness / 2, h / 2, thickness, h, { isStatic: true })
      );

      Matter.World.add(engine.world, newObstacles);
      obstaclesRef.current = newObstacles;
    };

    mapObstacles();
    window.addEventListener('resize', mapObstacles);

    // 3. Render and Physics Loop
    let animationFrameId;
    let lastTime = performance.now();
    let spriteTimer = 0;
    let frameIndex = 0;

    const gameLoop = (time) => {
      const dt = Math.min(time - lastTime, 16.667); // Delta cap avoids Matter.js warnings
      lastTime = time;

      // Update Matter Physics Engine with capped delta
      Matter.Engine.update(engine, dt);

      const dx = mousePos.current.x - cat.position.x;
      const dy = mousePos.current.y - cat.position.y;
      const distToMouse = Math.sqrt(dx * dx + dy * dy);
      const isMouseRecent = time - mousePos.current.lastMove < 2500;

      // State Machine & Steering
      if (dialogue) {
        state.current = 'alert';
      } else if (isMouseRecent && distToMouse > 35) {
        // Chase mouse with potential-field obstacle avoidance
        state.current = 'chase';
        const angle = Math.atan2(dy, dx);
        let forceX = Math.cos(angle) * CHASE_FORCE;
        let forceY = Math.sin(angle) * CHASE_FORCE;

        // Repulsion from nearby static obstacle bodies
        // ponytail: naive potential field, no guarantees in tight concave pockets
        const REPEL_RADIUS = 48;
        const REPEL_STRENGTH = CHASE_FORCE * 3.5;
        for (const obs of obstaclesRef.current) {
          if (!obs.isStatic) continue;
          // Closest point on AABB to cat
          const b = obs.bounds;
          const cx = Math.max(b.min.x, Math.min(cat.position.x, b.max.x));
          const cy = Math.max(b.min.y, Math.min(cat.position.y, b.max.y));
          const ex = cat.position.x - cx;
          const ey = cat.position.y - cy;
          const dist = Math.sqrt(ex * ex + ey * ey) || 0.1;
          if (dist < REPEL_RADIUS) {
            const strength = REPEL_STRENGTH * (1 - dist / REPEL_RADIUS);
            forceX += (ex / dist) * strength;
            forceY += (ey / dist) * strength;
          }
        }

        Matter.Body.applyForce(cat, cat.position, { x: forceX, y: forceY });
      } else if (isMouseRecent && distToMouse <= 35) {
        // Arrived at mouse -> sit & scratch
        state.current = 'scratch';
        Matter.Body.setVelocity(cat, Matter.Vector.mult(cat.velocity, 0.7));
      } else {
        // Wandering / Sleeping
        stateTimer.current -= dt;
        if (stateTimer.current <= 0) {
          if (state.current === 'sleep' || state.current === 'scratch') {
            state.current = 'walk';
            stateTimer.current = 3000 + Math.random() * 4000;
          } else {
            if (Math.random() > 0.4) {
              state.current = 'sleep';
              stateTimer.current = 4000 + Math.random() * 6000;
            } else {
              state.current = 'scratch';
              stateTimer.current = 2500 + Math.random() * 2500;
            }
          }
        }

        if (state.current === 'walk') {
          wanderAngle.current += (Math.random() * 0.4 - 0.2);
          const forceX = Math.cos(wanderAngle.current) * WANDER_FORCE;
          const forceY = Math.sin(wanderAngle.current) * WANDER_FORCE;
          Matter.Body.applyForce(cat, cat.position, { x: forceX, y: forceY });
        } else {
          if (Matter.Vector.magnitude(cat.velocity) > 0.01) {
            Matter.Body.setVelocity(cat, Matter.Vector.mult(cat.velocity, 0.85));
          }
        }
      }

      // Cap speed
      const speed = Matter.Vector.magnitude(cat.velocity);
      if (speed > MAX_SPEED) {
        Matter.Body.setVelocity(cat, Matter.Vector.mult(Matter.Vector.normalise(cat.velocity), MAX_SPEED));
      }

      // Z-Depth Scaling Logic
      const depthRatio = Math.max(0, Math.min(1, cat.position.y / window.innerHeight));
      const scale = 0.85 + depthRatio * 0.4;
      
      // Update DOM visually
      if (containerRef.current) {
        containerRef.current.style.transform = `translate3d(${cat.position.x - CAT_RADIUS}px, ${cat.position.y - CAT_RADIUS}px, 0) scale(${scale})`;
        containerRef.current.style.zIndex = Math.floor(depthRatio * 100) + 15;
        
        if (state.current === 'sleep') {
          containerRef.current.style.opacity = '0.5';
        } else {
          containerRef.current.style.opacity = '1';
        }
      }

      // Sprite Animation (5 FPS)
      spriteTimer += dt;
      if (spriteTimer > 180) {
        spriteTimer = 0;
        frameIndex++;
        
        let visualState = 'idle';
        if (state.current === 'sleep') {
          visualState = 'sleep';
        } else if (state.current === 'alert') {
          visualState = 'alert';
        } else if (state.current === 'scratch') {
          visualState = 'scratchSelf';
        } else if (state.current === 'walk' || state.current === 'chase') {
          let moveAngle = Math.atan2(cat.velocity.y, cat.velocity.x);
          if (state.current === 'chase' && isMouseRecent) {
            moveAngle = Math.atan2(dy, dx);
          }

          if (speed > 0.05 || (state.current === 'chase' && distToMouse > 25)) {
            const octant = Math.round(8 * moveAngle / (2 * Math.PI) + 8) % 8;
            const dirs = ['runE', 'runSE', 'runS', 'runSW', 'runW', 'runNW', 'runN', 'runNE'];
            visualState = dirs[octant];
          } else {
            visualState = 'idle';
          }
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
      window.removeEventListener('pointermove', handleMouseMove);
      Matter.Engine.clear(engine);
    };
  }, [dialogue]);

  const handleTickle = () => {
    // Spawn floating heart particles
    const id = Date.now() + Math.random();
    setHearts(prev => [...prev.slice(-4), { id, text: ['💖', '✨', '🐾', ' purr~ '][Math.floor(Math.random() * 4)] }]);
    setTimeout(() => {
      setHearts(prev => prev.filter(h => h.id !== id));
    }, 1200);

    if (catBodyRef.current) {
      const forceX = (Math.random() > 0.5 ? 1 : -1) * 0.004;
      const forceY = (Math.random() > 0.5 ? 1 : -1) * 0.004;
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
      {/* Floating Hearts/Purr particles */}
      <AnimatePresence>
        {hearts.map(heart => (
          <motion.div
            key={heart.id}
            initial={{ opacity: 1, y: 0, scale: 0.6 }}
            animate={{ opacity: 0, y: -40, scale: 1.2 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1.1, ease: "easeOut" }}
            className="absolute text-[13px] font-bold pointer-events-none select-none z-50 text-primary drop-shadow"
          >
            {heart.text}
          </motion.div>
        ))}
      </AnimatePresence>

      <AnimatePresence>
        {dialogue && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.8 }}
            animate={{ opacity: 1, y: -15, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            className="absolute bottom-full mb-2 w-[130px] bg-card/95 backdrop-blur-md text-foreground text-[10.5px] font-semibold p-2.5 rounded-xl shadow-xl border border-border text-center leading-tight pointer-events-none z-50"
            style={{ 
              transformOrigin: 'bottom center',
              transform: 'scale(0.85)' 
            }}
          >
            {dialogue}
            <div className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-l-[6px] border-r-[6px] border-t-[8px] border-l-transparent border-r-transparent border-t-card/95" />
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
        className="active:scale-90 hover:scale-125 transition-transform"
      />
    </div>
  );
}
