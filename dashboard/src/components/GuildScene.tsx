import { useState } from 'react';
import AnimatedSprite from './AnimatedSprite';
import type { Hero } from '../data/mock';

// Display size for heroes in the scene (scaled down from sprite strip)
const DISPLAY_SCALE = 0.55;

// Hero positions inside the guild hall (percentage-based)
const heroPositions: Record<string, { x: number; y: number }> = {
  h1: { x: 38, y: 58 },
  h2: { x: 28, y: 68 },
  h3: { x: 62, y: 68 },
  h4: { x: 55, y: 78 },
};

// Default positions for heroes beyond the first 4
const extraPositions = [
  { x: 45, y: 72 },
  { x: 35, y: 75 },
  { x: 52, y: 65 },
  { x: 48, y: 80 },
];

// Map hero class to sprite info when API data lacks sprite fields
const classSpriteMap: Record<string, { sprite: string; frames: number; frameWidth: number; frameHeight: number }> = {
  'Rust Sorcerer': { sprite: 'mage1-idle.png', frames: 3, frameWidth: 192, frameHeight: 156 },
  'Mage': { sprite: 'mage2-idle.png', frames: 3, frameWidth: 192, frameHeight: 156 },
  'Node Assassin': { sprite: 'fighter-sword-idle.png', frames: 3, frameWidth: 192, frameHeight: 192 },
  'Frontend Archer': { sprite: 'fighter2-idle.png', frames: 12, frameWidth: 96, frameHeight: 96 },
  'Python Sage': { sprite: 'mage3-idle.png', frames: 3, frameWidth: 192, frameHeight: 156 },
  'Data Shaman': { sprite: 'mage4-idle.png', frames: 3, frameWidth: 192, frameHeight: 156 },
  'ML Engineer': { sprite: 'citizen1-idle.png', frames: 3, frameWidth: 192, frameHeight: 156 },
  'DevOps Paladin': { sprite: 'fighter2-idle.png', frames: 12, frameWidth: 96, frameHeight: 96 },
};

// Fallback sprite mapping by keyword
function resolveSprite(heroClass: string) {
  if (classSpriteMap[heroClass]) return classSpriteMap[heroClass];
  const lc = heroClass.toLowerCase();
  if (lc.includes('mage') || lc.includes('sorcerer') || lc.includes('wizard'))
    return { sprite: 'mage1-idle.png', frames: 3, frameWidth: 192, frameHeight: 156 };
  if (lc.includes('assassin') || lc.includes('archer') || lc.includes('fighter') || lc.includes('paladin'))
    return { sprite: 'fighter-sword-idle.png', frames: 3, frameWidth: 192, frameHeight: 192 };
  if (lc.includes('sage') || lc.includes('shaman') || lc.includes('engineer'))
    return { sprite: 'citizen1-idle.png', frames: 3, frameWidth: 192, frameHeight: 156 };
  return { sprite: 'citizen2-idle.png', frames: 3, frameWidth: 192, frameHeight: 156 };
}

interface Props {
  heroes: Hero[];
  onHeroClick: (heroId: string) => void;
}

export default function GuildScene({ heroes, onHeroClick }: Props) {
  const [hoveredHero, setHoveredHero] = useState<string | null>(null);

  return (
    <>
      <img
        src="/assets/guild-hall-interior.png"
        alt="Guild Hall Interior"
        className="guild-bg"
        style={{ height: '100%', maxWidth: '140%' }}
      />

      {heroes.map((hero, idx) => {
        const pos = heroPositions[hero.id] ?? extraPositions[idx % extraPositions.length];
        if (!pos) return null;

        // Use hero's own sprite data if present, otherwise resolve from class
        const spriteInfo = hero.sprite ? hero : { ...resolveSprite(hero.class), sprite: hero.sprite || resolveSprite(hero.class).sprite };
        const isOffline = hero.status === 'offline';
        const displayW = Math.round(spriteInfo.frameWidth * DISPLAY_SCALE);
        const displayH = Math.round(spriteInfo.frameHeight * DISPLAY_SCALE);

        return (
          <div key={hero.id}>
            <AnimatedSprite
              src={`/assets/sprites/sliced/${spriteInfo.sprite}`}
              frames={spriteInfo.frames}
              frameWidth={displayW}
              frameHeight={displayH}
              fps={isOffline ? 0 : 5}
              style={{
                left: `${pos.x}%`,
                top: `${pos.y}%`,
                transform: 'translate(-50%, -50%)',
                opacity: isOffline ? 0.35 : 1,
                zIndex: 5,
              }}
              onClick={() => onHeroClick(hero.id)}
              onMouseEnter={() => setHoveredHero(hero.id)}
              onMouseLeave={() => setHoveredHero(null)}
            />

            {hoveredHero === hero.id && (
              <div
                className="hero-tooltip"
                style={{ left: `${pos.x}%`, top: `${pos.y}%`, zIndex: 25 }}
              >
                <div className="hero-tooltip-name">{hero.name}</div>
                <div className="hero-tooltip-class">
                  {hero.class} &middot; LV.{hero.level}
                </div>
                <span className={`status-badge ${hero.status}`} style={{ marginTop: 2 }}>
                  {hero.status.replace('_', ' ')}
                </span>
              </div>
            )}

            <div
              style={{
                position: 'absolute',
                left: `${pos.x}%`,
                top: `calc(${pos.y}% - ${displayH / 2 + 6}px)`,
                transform: 'translateX(-50%)',
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: `var(--status-${hero.status})`,
                border: '1px solid rgba(0,0,0,0.5)',
                zIndex: 6,
              }}
            />
          </div>
        );
      })}
    </>
  );
}
