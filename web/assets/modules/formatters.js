export function formatProviderModels(value) {
  const obj = value && typeof value === 'object' ? value : {};
  const entries = Object.entries(obj)
    .map(([provider, model]) => [String(provider || '').trim(), String(model || '').trim()])
    .filter(([provider, model]) => provider && model);
  if (!entries.length) return 'n/a';
  return entries.map(([provider, model]) => `${provider}=${model}`).join(', ');
}

export function formatProviderModelParams(value) {
  const obj = value && typeof value === 'object' ? value : {};
  const entries = Object.entries(obj)
    .map(([provider, params]) => [String(provider || '').trim(), String(params || '').trim()])
    .filter(([provider, params]) => provider && params);
  if (!entries.length) return 'n/a';
  return entries.map(([provider, params]) => `${provider}=${params}`).join(' | ');
}

export function formatParticipantModels(value) {
  const obj = value && typeof value === 'object' ? value : {};
  const entries = Object.entries(obj)
    .map(([participant, model]) => [String(participant || '').trim(), String(model || '').trim()])
    .filter(([participant, model]) => participant && model);
  if (!entries.length) return 'n/a';
  return entries.map(([participant, model]) => `${participant}=${model}`).join(' | ');
}

export function formatParticipantModelParams(value) {
  const obj = value && typeof value === 'object' ? value : {};
  const entries = Object.entries(obj)
    .map(([participant, params]) => [String(participant || '').trim(), String(params || '').trim()])
    .filter(([participant, params]) => participant && params);
  if (!entries.length) return 'n/a';
  return entries.map(([participant, params]) => `${participant}=${params}`).join(' | ');
}

export function formatParticipantBoolOverrides(value) {
  const obj = value && typeof value === 'object' ? value : {};
  const entries = Object.entries(obj)
    .map(([participant, enabled]) => [String(participant || '').trim(), !!enabled])
    .filter(([participant]) => participant);
  if (!entries.length) return 'n/a';
  return entries.map(([participant, enabled]) => `${participant}=${enabled ? 1 : 0}`).join(' | ');
}

export function statusPill(status) {
  const text = String(status || 'unknown');
  if (text === 'passed') return `<span class="pill ok">${text}</span>`;
  if (['failed_gate', 'failed_system', 'canceled'].includes(text)) return `<span class="pill warn">${text}</span>`;
  return `<span class="pill">${text}</span>`;
}

export function isActiveStatus(status) {
  return ['running', 'queued', 'waiting_manual'].includes(String(status || ''));
}

export function taskSortPriority(status) {
  const text = String(status || '').trim().toLowerCase();
  if (text === 'running') return 30;
  if (text === 'waiting_manual') return 20;
  if (text === 'queued') return 10;
  return 0;
}

export function taskSortStamp(task, parseEventDateFn) {
  const raw = String(
    task.updated_at
    || task.created_at
    || task._history_stamp
    || ''
  ).trim();
  if (!raw) return 0;
  const dt = parseEventDateFn(raw);
  if (Number.isNaN(dt.getTime())) return 0;
  return dt.getTime();
}
