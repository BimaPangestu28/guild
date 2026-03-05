import { projects, quests } from '../data/mock';

interface Props { onClose: () => void; }

export default function ProjectPanel({ onClose }: Props) {
  return (
    <div className="game-panel panel-center">
      <div className="panel-header">
        <span>PROJECTS</span>
        <button className="panel-close" onClick={onClose}>x</button>
      </div>
      <div className="panel-body">
        {projects.map(proj => {
          const pq = quests.filter(q => q.projectId === proj.id);
          const active = pq.filter(q => q.status === 'active').length;
          const backlog = pq.filter(q => q.status === 'backlog').length;
          const done = pq.filter(q => q.status === 'done').length;

          return (
            <div key={proj.id} className="project-row">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span className="project-name">{proj.displayName}</span>
                <span className={`status-badge ${proj.status === 'active' ? 'idle' : 'offline'}`}>
                  {proj.status}
                </span>
              </div>
              <div className="project-meta">{proj.language} &middot; {proj.name}</div>
              <div className="project-stats">
                <span><span style={{ color: 'var(--status-on-quest)' }}>{active}</span> active</span>
                <span><span style={{ color: 'var(--text-secondary)' }}>{backlog}</span> backlog</span>
                <span><span style={{ color: 'var(--accent-green)' }}>{done}</span> done</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
