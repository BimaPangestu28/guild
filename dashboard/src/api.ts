const API_BASE = '/api';

export async function fetchStatus() {
  const res = await fetch(`${API_BASE}/status`);
  return res.json();
}

export async function fetchHeroes() {
  const res = await fetch(`${API_BASE}/heroes`);
  return res.json();
}

export async function fetchQuests() {
  const res = await fetch(`${API_BASE}/quests`);
  return res.json();
}

export async function fetchProjects() {
  const res = await fetch(`${API_BASE}/projects`);
  return res.json();
}

export async function fetchLog() {
  const res = await fetch(`${API_BASE}/log`);
  return res.json();
}
