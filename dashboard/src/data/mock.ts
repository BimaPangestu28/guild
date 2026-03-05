export type HeroStatus = 'idle' | 'on_quest' | 'resting' | 'blocked' | 'offline';
export type QuestStatus = 'backlog' | 'active' | 'blocked' | 'done';
export type QuestTier = 'COMMON' | 'RARE' | 'EPIC' | 'LEGENDARY' | 'BOSS';
export type QuestType = 'impl' | 'test' | 'review' | 'merge' | 'chore';

export interface Hero {
  id: string;
  name: string;
  class: string;
  status: HeroStatus;
  level: number;
  xp: number;
  currentQuestId: string | null;
  baseSkills: string[];
  learnedSkills: string[];
  sprite: string; // sliced sprite strip filename
  frames: number;
  frameWidth: number;  // scaled px
  frameHeight: number; // scaled px
}

export interface Quest {
  id: string;
  chainId: string;
  title: string;
  description: string;
  tier: QuestTier;
  type: QuestType;
  status: QuestStatus;
  projectId: string;
  branch: string;
  assignedTo: string | null;
  createdAt: string;
}

export interface Project {
  id: string;
  name: string;
  displayName: string;
  language: string;
  status: 'active' | 'paused' | 'archived';
  lastActive: string;
}

export interface ActivityEntry {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  questId: string | null;
  level: 'info' | 'warning' | 'critical';
}

export const heroes: Hero[] = [
  {
    id: 'h1', name: 'StormForge', class: 'Rust Sorcerer', status: 'on_quest',
    level: 5, xp: 1450, currentQuestId: 'GLD-042',
    baseSkills: ['rust', 'wasm', 'systems'], learnedSkills: ['greentic-codebase'],
    sprite: 'mage1-idle.png', frames: 3, frameWidth: 192, frameHeight: 156,
  },
  {
    id: 'h2', name: 'IronWeave', class: 'Python Sage', status: 'idle',
    level: 3, xp: 680, currentQuestId: null,
    baseSkills: ['python', 'ml', 'data'], learnedSkills: ['map-conventions'],
    sprite: 'mage3-idle.png', frames: 3, frameWidth: 192, frameHeight: 156,
  },
  {
    id: 'h3', name: 'ShadowBlade', class: 'Node Assassin', status: 'resting',
    level: 4, xp: 1100, currentQuestId: null,
    baseSkills: ['node', 'typescript', 'api'], learnedSkills: ['greentic-codebase'],
    sprite: 'fighter-sword-idle.png', frames: 3, frameWidth: 192, frameHeight: 192,
  },
  {
    id: 'h4', name: 'EmberShield', class: 'DevOps Paladin', status: 'offline',
    level: 2, xp: 320, currentQuestId: null,
    baseSkills: ['devops', 'kubernetes', 'docker'], learnedSkills: [],
    sprite: 'fighter2-idle.png', frames: 12, frameWidth: 96, frameHeight: 96,
  },
];

export const quests: Quest[] = [
  { id: 'GLD-042', chainId: 'GLC-015', title: 'Implement Telegram Adapter', description: 'Create TelegramAdapter struct implementing MessageAdapter trait', tier: 'RARE', type: 'impl', status: 'active', projectId: 'greentic', branch: 'feature/GLD-042-telegram-adapter', assignedTo: 'h1', createdAt: '2026-03-06T08:00:00' },
  { id: 'GLD-043', chainId: 'GLC-015', title: 'Test Telegram Adapter', description: 'Write integration tests for TelegramAdapter', tier: 'COMMON', type: 'test', status: 'backlog', projectId: 'greentic', branch: 'feature/GLD-042-telegram-adapter', assignedTo: null, createdAt: '2026-03-06T08:05:00' },
  { id: 'GLD-044', chainId: 'GLC-016', title: 'Add daily sales report endpoint', description: 'Implement GET /reports/daily-sales', tier: 'RARE', type: 'impl', status: 'backlog', projectId: 'map-group', branch: 'feature/GLD-044-daily-sales', assignedTo: null, createdAt: '2026-03-06T07:00:00' },
  { id: 'GLD-045', chainId: 'GLC-017', title: 'Fix WebSocket reconnect logic', description: 'Implement exponential backoff', tier: 'COMMON', type: 'impl', status: 'done', projectId: 'greentic', branch: 'fix/GLD-045-ws-reconnect', assignedTo: 'h3', createdAt: '2026-03-05T14:00:00' },
  { id: 'GLD-046', chainId: 'GLC-017', title: 'Review WebSocket PR', description: 'Code review', tier: 'COMMON', type: 'review', status: 'done', projectId: 'greentic', branch: 'fix/GLD-045-ws-reconnect', assignedTo: 'h2', createdAt: '2026-03-05T16:00:00' },
  { id: 'GLD-047', chainId: 'GLC-018', title: 'Refactor WASM adapters', description: 'Extract shared logic', tier: 'EPIC', type: 'impl', status: 'blocked', projectId: 'greentic', branch: 'feature/GLD-047-wasm-refactor', assignedTo: 'h1', createdAt: '2026-03-06T06:00:00' },
];

export const projects: Project[] = [
  { id: 'greentic', name: 'greentic', displayName: 'Greentic AI', language: 'Rust', status: 'active', lastActive: '2026-03-06T10:30:00' },
  { id: 'map-group', name: 'map-group', displayName: 'MAP Group Platform', language: 'TypeScript', status: 'active', lastActive: '2026-03-06T07:00:00' },
];

export const activityLog: ActivityEntry[] = [
  { id: 'a1', timestamp: '2026-03-06T10:30:00', actor: 'StormForge', action: '[GLD-042] Add TelegramAdapter struct', questId: 'GLD-042', level: 'info' },
  { id: 'a2', timestamp: '2026-03-06T10:15:00', actor: 'Guild Master', action: 'Assigned GLD-042 to StormForge', questId: 'GLD-042', level: 'info' },
  { id: 'a3', timestamp: '2026-03-06T10:00:00', actor: 'Guild Master', action: 'Decomposed goal → chain GLC-015', questId: null, level: 'info' },
  { id: 'a4', timestamp: '2026-03-06T09:45:00', actor: 'System', action: 'GLD-047 blocked: dependency on GLD-042', questId: 'GLD-047', level: 'warning' },
  { id: 'a5', timestamp: '2026-03-06T09:00:00', actor: 'Guild Master', action: 'Daily briefing sent', questId: null, level: 'info' },
  { id: 'a6', timestamp: '2026-03-05T18:00:00', actor: 'ShadowBlade', action: 'GLD-045 completed', questId: 'GLD-045', level: 'info' },
  { id: 'a7', timestamp: '2026-03-05T17:30:00', actor: 'Guild Master', action: 'PR #23 merged to development', questId: 'GLD-045', level: 'info' },
];

export const costData = { today: 2.84, cap: 5.00 };
