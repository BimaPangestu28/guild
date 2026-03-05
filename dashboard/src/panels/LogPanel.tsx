import { activityLog } from '../data/mock';

interface Props { onClose: () => void; }

export default function LogPanel({ onClose }: Props) {
  return (
    <div className="game-panel panel-right">
      <div className="panel-header">
        <span>ACTIVITY LOG</span>
        <button className="panel-close" onClick={onClose}>x</button>
      </div>
      <div className="panel-body">
        {activityLog.map(entry => (
          <div key={entry.id} className={`log-entry ${entry.level}`}>
            <span className="log-time">
              {new Date(entry.timestamp).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
            </span>
            <span className="log-actor">{entry.actor}</span>
            <span className="log-action">{entry.action}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
