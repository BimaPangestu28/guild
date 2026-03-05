import { useState } from 'react';
import GuildScene from './components/GuildScene';
import HeroPanel from './panels/HeroPanel';
import QuestPanel from './panels/QuestPanel';
import ProjectPanel from './panels/ProjectPanel';
import LogPanel from './panels/LogPanel';
import MemoryPanel from './panels/MemoryPanel';
import { heroes, quests, costData } from './data/mock';

type PanelId = 'heroes' | 'quests' | 'projects' | 'log' | 'memory' | null;

export default function App() {
  const [activePanel, setActivePanel] = useState<PanelId>(null);
  const [selectedHero, setSelectedHero] = useState<string | null>(null);

  const toggle = (id: PanelId) => setActivePanel(prev => prev === id ? null : id);

  const activeQuests = quests.filter(q => q.status === 'active').length;
  const backlog = quests.filter(q => q.status === 'backlog').length;
  const blocked = quests.filter(q => q.status === 'blocked').length;
  const onlineHeroes = heroes.filter(h => h.status !== 'offline').length;
  const costPct = (costData.today / costData.cap) * 100;
  const costClass = costPct > 80 ? 'danger' : costPct > 60 ? 'warning' : 'ok';

  return (
    <div className="guild-scene">
      {/* Background scene */}
      <GuildScene
        onHeroClick={(id) => { setSelectedHero(id); setActivePanel('heroes'); }}
      />

      {/* HUD Overlay */}
      <div className="hud">
        {/* Top bar */}
        <div className="hud-top">
          <div className="hud-title">CODE GUILD</div>
          <div className="hud-stats">
            <div className="hud-stat">
              <span className="hud-stat-value">{onlineHeroes}/{heroes.length}</span>
              <span className="hud-stat-label">Heroes</span>
            </div>
            <div className="hud-stat">
              <span className="hud-stat-value">{activeQuests}</span>
              <span className="hud-stat-label">Active</span>
            </div>
            <div className="hud-stat">
              <span className="hud-stat-value">{backlog}</span>
              <span className="hud-stat-label">Backlog</span>
            </div>
            {blocked > 0 && (
              <div className="hud-stat">
                <span className="hud-stat-value" style={{ color: 'var(--accent-red)' }}>{blocked}</span>
                <span className="hud-stat-label">Blocked</span>
              </div>
            )}
            <div className="hud-stat">
              <span className="hud-stat-value">${costData.today.toFixed(2)}</span>
              <div>
                <div className="hud-stat-label">${costData.cap.toFixed(2)} cap</div>
                <div className="cost-bar-hud">
                  <div className={`cost-bar-hud-fill ${costClass}`} style={{ width: `${Math.min(costPct, 100)}%` }} />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom nav buttons */}
        <div className="hud-bottom">
          <button className={`hud-btn ${activePanel === 'heroes' ? 'active' : ''}`} onClick={() => toggle('heroes')}>
            Heroes
          </button>
          <button className={`hud-btn ${activePanel === 'quests' ? 'active' : ''}`} onClick={() => toggle('quests')}>
            Quest Board
          </button>
          <button className={`hud-btn ${activePanel === 'projects' ? 'active' : ''}`} onClick={() => toggle('projects')}>
            Projects
          </button>
          <button className={`hud-btn ${activePanel === 'memory' ? 'active' : ''}`} onClick={() => toggle('memory')}>
            Memory
          </button>
          <button className={`hud-btn ${activePanel === 'log' ? 'active' : ''}`} onClick={() => toggle('log')}>
            Log
          </button>
        </div>

        {/* Panels */}
        {activePanel === 'heroes' && (
          <HeroPanel selectedHero={selectedHero} onClose={() => setActivePanel(null)} />
        )}
        {activePanel === 'quests' && (
          <QuestPanel onClose={() => setActivePanel(null)} />
        )}
        {activePanel === 'projects' && (
          <ProjectPanel onClose={() => setActivePanel(null)} />
        )}
        {activePanel === 'memory' && (
          <MemoryPanel onClose={() => setActivePanel(null)} />
        )}
        {activePanel === 'log' && (
          <LogPanel onClose={() => setActivePanel(null)} />
        )}
      </div>
    </div>
  );
}
