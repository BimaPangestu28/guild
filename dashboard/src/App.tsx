import { useState, useCallback } from 'react';
import GuildScene from './components/GuildScene';
import HeroPanel from './panels/HeroPanel';
import QuestPanel from './panels/QuestPanel';
import ProjectPanel from './panels/ProjectPanel';
import LogPanel from './panels/LogPanel';
import MemoryPanel from './panels/MemoryPanel';
import { heroes as mockHeroes, quests as mockQuests, projects as mockProjects, activityLog as mockLog, costData as mockCostData } from './data/mock';
import type { Hero, Quest, Project, ActivityEntry } from './data/mock';
import { fetchStatus, fetchHeroes, fetchQuests, fetchProjects, fetchLog } from './api';
import { usePolling } from './hooks/usePolling';

type PanelId = 'heroes' | 'quests' | 'projects' | 'log' | 'memory' | null;

interface StatusData {
  onlineHeroes: number;
  totalHeroes: number;
  activeQuests: number;
  backlog: number;
  blocked: number;
  costToday: number;
  costCap: number;
}

const defaultStatus: StatusData = {
  onlineHeroes: mockHeroes.filter(h => h.status !== 'offline').length,
  totalHeroes: mockHeroes.length,
  activeQuests: mockQuests.filter(q => q.status === 'active').length,
  backlog: mockQuests.filter(q => q.status === 'backlog').length,
  blocked: mockQuests.filter(q => q.status === 'blocked').length,
  costToday: mockCostData.today,
  costCap: mockCostData.cap,
};

export default function App() {
  const [activePanel, setActivePanel] = useState<PanelId>(null);
  const [selectedHero, setSelectedHero] = useState<string | null>(null);

  const fetchStatusCb = useCallback(() => fetchStatus(), []);
  const fetchHeroesCb = useCallback(() => fetchHeroes(), []);
  const fetchQuestsCb = useCallback(() => fetchQuests(), []);
  const fetchProjectsCb = useCallback(() => fetchProjects(), []);
  const fetchLogCb = useCallback(() => fetchLog(), []);

  const { data: status, error: statusErr } = usePolling<StatusData>(fetchStatusCb, 5000, defaultStatus);
  const { data: heroes } = usePolling<Hero[]>(fetchHeroesCb, 5000, mockHeroes);
  const { data: quests } = usePolling<Quest[]>(fetchQuestsCb, 5000, mockQuests);
  const { data: projects } = usePolling<Project[]>(fetchProjectsCb, 5000, mockProjects);
  const { data: log } = usePolling<ActivityEntry[]>(fetchLogCb, 5000, mockLog);

  const toggle = (id: PanelId) => setActivePanel(prev => prev === id ? null : id);

  // Use status from API, fall back to computing from local data if status endpoint fails
  const onlineHeroes = statusErr ? heroes.filter(h => h.status !== 'offline').length : status.onlineHeroes;
  const totalHeroes = statusErr ? heroes.length : status.totalHeroes;
  const activeQuests = statusErr ? quests.filter(q => q.status === 'active').length : status.activeQuests;
  const backlog = statusErr ? quests.filter(q => q.status === 'backlog').length : status.backlog;
  const blocked = statusErr ? quests.filter(q => q.status === 'blocked').length : status.blocked;
  const costToday = statusErr ? mockCostData.today : status.costToday;
  const costCap = statusErr ? mockCostData.cap : status.costCap;

  const costPct = (costToday / costCap) * 100;
  const costClass = costPct > 80 ? 'danger' : costPct > 60 ? 'warning' : 'ok';

  return (
    <div className="guild-scene">
      {/* Background scene */}
      <GuildScene
        heroes={heroes}
        onHeroClick={(id) => { setSelectedHero(id); setActivePanel('heroes'); }}
      />

      {/* HUD Overlay */}
      <div className="hud">
        {/* Top bar */}
        <div className="hud-top">
          <div className="hud-title">CODE GUILD</div>
          <div className="hud-stats">
            <div className="hud-stat">
              <span className="hud-stat-value">{onlineHeroes}/{totalHeroes}</span>
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
              <span className="hud-stat-value">${costToday.toFixed(2)}</span>
              <div>
                <div className="hud-stat-label">${costCap.toFixed(2)} cap</div>
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
          <HeroPanel heroes={heroes} quests={quests} selectedHero={selectedHero} onClose={() => setActivePanel(null)} />
        )}
        {activePanel === 'quests' && (
          <QuestPanel quests={quests} heroes={heroes} onClose={() => setActivePanel(null)} />
        )}
        {activePanel === 'projects' && (
          <ProjectPanel projects={projects} quests={quests} onClose={() => setActivePanel(null)} />
        )}
        {activePanel === 'memory' && (
          <MemoryPanel onClose={() => setActivePanel(null)} />
        )}
        {activePanel === 'log' && (
          <LogPanel log={log} onClose={() => setActivePanel(null)} />
        )}
      </div>
    </div>
  );
}
