interface Props { onClose: () => void; }

export default function MemoryPanel({ onClose }: Props) {
  return (
    <div className="game-panel panel-left">
      <div className="panel-header">
        <span>GUILD MEMORY</span>
        <button className="panel-close" onClick={onClose}>x</button>
      </div>
      <div className="panel-body" style={{ fontSize: 16, color: 'var(--text-secondary)' }}>
        <div style={{ marginBottom: 12 }}>
          <div style={{ color: 'var(--accent-gold)', fontFamily: "'Press Start 2P', monospace", fontSize: 8, marginBottom: 8 }}>
            SHARED
          </div>
          <div style={{ paddingLeft: 8 }}>
            <div style={{ color: 'var(--accent-gold)' }}>&gt; projects/</div>
            <div style={{ paddingLeft: 16 }}>- greentic.md</div>
            <div style={{ paddingLeft: 16, color: 'var(--accent-gold)' }}>&gt; greentic-adr/</div>
            <div style={{ paddingLeft: 32 }}>- adr-001-use-tokio.md</div>
            <div style={{ paddingLeft: 32 }}>- adr-002-wasm-interface.md</div>
            <div style={{ paddingLeft: 16 }}>- map-group.md</div>
            <div style={{ color: 'var(--accent-gold)' }}>&gt; conventions/</div>
            <div style={{ paddingLeft: 16 }}>- git.md</div>
            <div style={{ paddingLeft: 16 }}>- code-style.md</div>
            <div style={{ paddingLeft: 16 }}>- testing.md</div>
          </div>
        </div>

        <div>
          <div style={{ color: 'var(--accent-gold)', fontFamily: "'Press Start 2P', monospace", fontSize: 8, marginBottom: 8 }}>
            HEROES
          </div>
          <div style={{ paddingLeft: 8 }}>
            {['StormForge', 'IronWeave', 'ShadowBlade', 'EmberShield'].map(name => (
              <div key={name}>
                <div style={{ color: 'var(--accent-gold)' }}>&gt; {name}/</div>
                <div style={{ paddingLeft: 16 }}>- CLAUDE.md</div>
                <div style={{ paddingLeft: 16 }}>- history.md</div>
                <div style={{ paddingLeft: 16 }}>- notes.md</div>
                <div style={{ paddingLeft: 16, color: 'var(--accent-gold)' }}>&gt; skills/</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
