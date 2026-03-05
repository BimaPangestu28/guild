import { useState } from 'react';
import AnimatedSprite from './AnimatedSprite';
import { heroes } from '../data/mock';

// Display size for heroes in the scene (scaled down from sprite strip)
const DISPLAY_SCALE = 0.55;

// Hero positions inside the guild hall (percentage-based)
const heroPositions: Record<string, { x: number; y: number }> = {
  h1: { x: 38, y: 58 },
  h2: { x: 28, y: 68 },
  h3: { x: 62, y: 68 },
  h4: { x: 55, y: 78 },
};

interface Props {
  onHeroClick: (heroId: string) => void;
}

export default function GuildScene({ onHeroClick }: Props) {
  const [hoveredHero, setHoveredHero] = useState<string | null>(null);

  return (
    <>
      <img
        src="/assets/guild-hall-interior.png"
        alt="Guild Hall Interior"
        className="guild-bg"
        style={{ height: '100%', maxWidth: '140%' }}
      />

      {heroes.map((hero) => {
        const pos = heroPositions[hero.id];
        if (!pos) return null;

        const isOffline = hero.status === 'offline';
        const displayW = Math.round(hero.frameWidth * DISPLAY_SCALE);
        const displayH = Math.round(hero.frameHeight * DISPLAY_SCALE);

        return (
          <div key={hero.id}>
            <AnimatedSprite
              src={`/assets/sprites/sliced/${hero.sprite}`}
              frames={hero.frames}
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
