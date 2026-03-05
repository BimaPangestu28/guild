import { useState } from 'react';
import type { Quest, Hero } from '../data/mock';

interface Props {
  quests: Quest[];
  heroes: Hero[];
  onClose: () => void;
}

const tabs = ['all', 'active', 'backlog', 'blocked', 'done'] as const;

export default function QuestPanel({ quests, heroes, onClose }: Props) {
  const [filter, setFilter] = useState<string>('all');
  const filtered = filter === 'all' ? quests : quests.filter(q => q.status === filter);

  return (
    <div className="game-panel panel-right">
      <div className="panel-header">
        <span>QUEST BOARD</span>
        <button className="panel-close" onClick={onClose}>x</button>
      </div>
      <div className="panel-tabs">
        {tabs.map(t => (
          <button
            key={t}
            className={`panel-tab ${filter === t ? 'active' : ''}`}
            onClick={() => setFilter(t)}
          >
            {t.toUpperCase()}
          </button>
        ))}
      </div>
      <div className="panel-body">
        {filtered.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', padding: 8 }}>No quests</div>
        ) : (
          filtered.map(q => {
            const hero = q.assignedTo ? heroes.find(h => h.id === q.assignedTo) : null;
            return (
              <div key={q.id} className="quest-item">
                <div className="quest-item-header">
                  <span className="quest-item-id">{q.id}</span>
                  <span className={`tier-badge ${q.tier}`}>{q.tier}</span>
                  <span className="type-badge">{q.type}</span>
                  <span className={`status-badge ${q.status}`}>{q.status}</span>
                </div>
                <div className="quest-item-title">{q.title}</div>
                <div className="quest-item-meta">
                  {hero && <span style={{ color: 'var(--accent-gold)' }}>{hero.name}</span>}
                  <span>{q.projectId}</span>
                  <span>{q.branch}</span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
