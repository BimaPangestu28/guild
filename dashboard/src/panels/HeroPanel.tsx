import { heroes, quests } from '../data/mock';

interface Props {
  selectedHero: string | null;
  onClose: () => void;
}

export default function HeroPanel({ selectedHero, onClose }: Props) {
  const selected = selectedHero ? heroes.find(h => h.id === selectedHero) : null;

  return (
    <div className="game-panel panel-left">
      <div className="panel-header">
        <span>HERO ROSTER</span>
        <button className="panel-close" onClick={onClose}>x</button>
      </div>
      <div className="panel-body">
        {heroes.map((hero) => {
          const quest = hero.currentQuestId ? quests.find(q => q.id === hero.currentQuestId) : null;
          const xpNext = hero.level * 500;
          const isSelected = hero.id === selectedHero;

          return (
            <div
              key={hero.id}
              className="hero-row"
              style={isSelected ? { background: 'rgba(240,192,64,0.08)', margin: '0 -16px', padding: '10px 16px' } : undefined}
            >
              <div className="hero-row-sprite" style={{ width: 48, height: 48, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <img
                  src={`/assets/sprites/sliced/${hero.sprite}`}
                  className="sprite-strip"
                  style={{ height: Math.min(48, hero.frameHeight * 0.35), imageRendering: 'pixelated' }}
                  draggable={false}
                />
              </div>
              <div className="hero-row-info">
                <div className="hero-row-name">{hero.name}</div>
                <div className="hero-row-class">{hero.class}</div>
                <div className="hero-row-meta">
                  <span className="level-badge">LV.{hero.level}</span>
                  <span className={`status-badge ${hero.status}`}>{hero.status.replace('_', ' ')}</span>
                </div>
                <div className="xp-bar">
                  <div className="xp-bar-fill" style={{ width: `${(hero.xp / xpNext) * 100}%` }} />
                </div>
                {quest && (
                  <div style={{ marginTop: 4, fontSize: 13, color: 'var(--text-muted)' }}>
                    {quest.id}: {quest.title}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {/* Detail section for selected hero */}
        {selected && (
          <div style={{ marginTop: 12, padding: '12px 0', borderTop: '2px solid var(--border)' }}>
            <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 6 }}>SKILLS</div>
            <div>
              {selected.baseSkills.map(s => <span key={s} className="skill-tag">{s}</span>)}
              {selected.learnedSkills.map(s => <span key={s} className="skill-tag learned">{s}</span>)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
