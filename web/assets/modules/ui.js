export function renderModelSelect(elm, values) {
  if (!elm) return;
  const current = String(elm.value || '').trim();
  elm.innerHTML = '';
  const list = Array.isArray(values) ? values : [];
  const seen = new Set();
  const normalized = [];
  for (const raw of list) {
    const text = String(raw || '').trim();
    const key = text.toLowerCase();
    if (!text || seen.has(key)) continue;
    seen.add(key);
    normalized.push(text);
  }
  if (current && !seen.has(current.toLowerCase())) {
    normalized.unshift(current);
  }
  for (const text of normalized) {
    const option = document.createElement('option');
    option.value = text;
    option.textContent = text;
    elm.appendChild(option);
  }
  if (normalized.length) {
    elm.value = normalized.includes(current) ? current : normalized[0];
  }
}

export function initElements(doc = document) {
  return {
    projectSelect: doc.getElementById('projectSelect'),
    projectTree: doc.getElementById('projectTree'),
    projectTreeMeta: doc.getElementById('projectTreeMeta'),
    roleList: doc.getElementById('roleList'),
    statsLine: doc.getElementById('statsLine'),
    kpiStrip: doc.getElementById('kpiStrip'),
    analyticsSummary: doc.getElementById('analyticsSummary'),
    taskSelect: doc.getElementById('taskSelect'),
    dialogue: doc.getElementById('dialogue'),
    githubSummaryMeta: doc.getElementById('githubSummaryMeta'),
    githubSummaryText: doc.getElementById('githubSummaryText'),
    reloadGithubSummaryBtn: doc.getElementById('reloadGithubSummaryBtn'),
    actionStatus: doc.getElementById('actionStatus'),
    taskSnapshot: doc.getElementById('taskSnapshot'),
    projectHistory: doc.getElementById('projectHistory'),
    historySummary: doc.getElementById('historySummary'),
    projectHistoryBody: doc.getElementById('projectHistoryBody'),
    clearHistoryBtn: doc.getElementById('clearHistoryBtn'),
    toggleHistoryBtn: doc.getElementById('toggleHistoryBtn'),
    openCreateHelpBtn: doc.getElementById('openCreateHelpBtn'),
    closeCreateHelpBtn: doc.getElementById('closeCreateHelpBtn'),
    createHelpPanel: doc.getElementById('createHelpPanel'),
    createHelpHint: doc.getElementById('createHelpHint'),
    createHelpList: doc.getElementById('createHelpList'),
    createHelpLangEnBtn: doc.getElementById('createHelpLangEnBtn'),
    createHelpLangZhBtn: doc.getElementById('createHelpLangZhBtn'),
    createStatus: doc.getElementById('createStatus'),
    pollBtn: doc.getElementById('pollBtn'),
    streamDetailBtn: doc.getElementById('streamDetailBtn'),
    startBtn: doc.getElementById('startBtn'),
    cancelBtn: doc.getElementById('cancelBtn'),
    forceFailBtn: doc.getElementById('forceFailBtn'),
    customReplyBtn: doc.getElementById('customReplyBtn'),
    promoteRoundBtn: doc.getElementById('promoteRoundBtn'),
    promoteRound: doc.getElementById('promoteRound'),
    forceReason: doc.getElementById('forceReason'),
    manualReplyNote: doc.getElementById('manualReplyNote'),
    connBadge: doc.getElementById('connBadge'),
    themeSelect: doc.getElementById('themeSelect'),
    expandTreeBtn: doc.getElementById('expandTreeBtn'),
    collapseTreeBtn: doc.getElementById('collapseTreeBtn'),
    approveQueueBtn: doc.getElementById('approveQueueBtn'),
    approveStartBtn: doc.getElementById('approveStartBtn'),
    rejectBtn: doc.getElementById('rejectBtn'),
    policyTemplate: doc.getElementById('policyTemplate'),
    applyPolicyTemplateBtn: doc.getElementById('applyPolicyTemplateBtn'),
    policyProfileHint: doc.getElementById('policyProfileHint'),
    workspacePath: doc.getElementById('workspacePath'),
    author: doc.getElementById('author'),
    reviewers: doc.getElementById('reviewers'),
    matrixAddReviewerBtn: doc.getElementById('matrixAddReviewerBtn'),
    selfLoopMode: doc.getElementById('selfLoopMode'),
    claudeModel: doc.getElementById('claudeModel'),
    codexModel: doc.getElementById('codexModel'),
    geminiModel: doc.getElementById('geminiModel'),
    claudeModelCustom: doc.getElementById('claudeModelCustom'),
    codexModelCustom: doc.getElementById('codexModelCustom'),
    geminiModelCustom: doc.getElementById('geminiModelCustom'),
    claudeModelParams: doc.getElementById('claudeModelParams'),
    codexModelParams: doc.getElementById('codexModelParams'),
    geminiModelParams: doc.getElementById('geminiModelParams'),
    participantCapabilityMatrix: doc.getElementById('participantCapabilityMatrix'),
    sandboxMode: doc.getElementById('sandboxMode'),
    autoMerge: doc.getElementById('autoMerge'),
    mergeTargetPath: doc.getElementById('mergeTargetPath'),
    evolveUntil: doc.getElementById('evolveUntil'),
    maxRounds: doc.getElementById('maxRounds'),
    repairMode: doc.getElementById('repairMode'),
    plainMode: doc.getElementById('plainMode'),
    streamMode: doc.getElementById('streamMode'),
    debateMode: doc.getElementById('debateMode'),
  };
}

export function renderParticipantCapabilityMatrixHtml({
  roleRows,
  draftMap,
  parseProvider,
  providerDefaultsFromForm,
  participantModelOptions,
  escapeHtml,
}) {
  const rows = roleRows.map((roleRow, rowIndex) => {
    const role = String((roleRow && roleRow.role) || 'reviewer').trim().toLowerCase() === 'author'
      ? 'author'
      : 'reviewer';
    const participantId = String((roleRow && roleRow.participantId) || '').trim();
    const provider = participantId ? parseProvider(participantId) : '';
    const defaults = providerDefaultsFromForm(provider);
    const draft = participantId ? (draftMap[participantId] || {}) : {};
    const selectedModel = String(draft.model || defaults.model || '').trim();
    const customModel = String(draft.customModel || '').trim();
    const params = String(
      draft.params !== undefined && draft.params !== null
        ? draft.params
        : defaults.params
    ).trim();
    const rowDisabled = !participantId;
    const claudeToggleDisabled = provider !== 'claude';
    const codexToggleDisabled = provider !== 'codex';
    const claudeAgentsModeRaw = String(draft.claudeAgentsMode || '0').trim().toLowerCase();
    const codexMultiAgentsModeRaw = String(draft.codexMultiAgentsMode || '0').trim().toLowerCase();
    const claudeAgentsMode = claudeToggleDisabled
      ? '0'
      : (['1', '0'].includes(claudeAgentsModeRaw) ? claudeAgentsModeRaw : '0');
    const codexMultiAgentsMode = codexToggleDisabled
      ? '0'
      : (['1', '0'].includes(codexMultiAgentsModeRaw) ? codexMultiAgentsModeRaw : '0');
    const options = participantModelOptions(provider, selectedModel);
    const optionHtml = options.length
      ? options
        .map((model) => `<option value="${escapeHtml(model)}"${model === selectedModel ? ' selected' : ''}>${escapeHtml(model)}</option>`)
        .join('')
      : `<option value="">${escapeHtml(participantId ? '(no model candidates)' : '(set Bot ID first)')}</option>`;
    const participantAttr = participantId ? `data-participant="${escapeHtml(participantId)}"` : '';

    return `
      <div class="participant-matrix-row">
        <div class="participant-role-line">
          <div>
            <label>Bot ID</label>
            <input
              data-row-index="${rowIndex}"
              data-field="participantId"
              value="${escapeHtml(participantId)}"
              placeholder="${role === 'author' ? 'provider#author-A' : 'provider#review-B'}"
            />
          </div>
          <span class="participant-role-pill">${role}</span>
          ${role === 'reviewer'
            ? `<button class="participant-remove-btn" data-remove-row="${rowIndex}" type="button">Remove</button>`
            : '<span></span>'}
        </div>
        <div class="participant-matrix-head">
          <span>${escapeHtml(participantId || '(empty)')}</span>
          <span class="participant-matrix-meta">provider=${escapeHtml(provider || 'n/a')}</span>
        </div>
        <div class="participant-matrix-fields">
          <div>
            <label>Model</label>
            <select data-row-index="${rowIndex}" data-field="model" ${participantAttr} ${rowDisabled ? 'disabled' : ''}>${optionHtml}</select>
          </div>
          <div>
            <label>Custom Model (override)</label>
            <input
              data-row-index="${rowIndex}"
              data-field="customModel"
              ${participantAttr}
              value="${escapeHtml(customModel)}"
              placeholder="optional custom model id"
              ${rowDisabled ? 'disabled' : ''}
            />
          </div>
          <div>
            <label>Model Params</label>
            <input
              data-row-index="${rowIndex}"
              data-field="params"
              ${participantAttr}
              value="${escapeHtml(params)}"
              placeholder="optional CLI params"
              ${rowDisabled ? 'disabled' : ''}
            />
          </div>
          <div>
            <label>Claude Team Agents</label>
            <select
              data-row-index="${rowIndex}"
              data-field="claudeAgentsMode"
              ${participantAttr}
              ${rowDisabled || claudeToggleDisabled ? 'disabled' : ''}
            >
              <option value="1"${claudeAgentsMode === '1' ? ' selected' : ''}>1 | on</option>
              <option value="0"${claudeAgentsMode === '0' ? ' selected' : ''}>0 | off</option>
            </select>
          </div>
          <div>
            <label>Codex Multi Agents</label>
            <select
              data-row-index="${rowIndex}"
              data-field="codexMultiAgentsMode"
              ${participantAttr}
              ${rowDisabled || codexToggleDisabled ? 'disabled' : ''}
            >
              <option value="1"${codexMultiAgentsMode === '1' ? ' selected' : ''}>1 | on</option>
              <option value="0"${codexMultiAgentsMode === '0' ? ' selected' : ''}>0 | off</option>
            </select>
          </div>
        </div>
      </div>
    `;
  }).join('');
  return rows;
}
