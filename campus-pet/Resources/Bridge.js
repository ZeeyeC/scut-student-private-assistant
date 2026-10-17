(() => {
  if (window.__campusPet) return;
  const pages = ['助手', '今日', '课表', '作业', '设置'];
  let lastState = '';
  let desiredPage = '助手';
  let backendState = null;
  let reviewThread = null;
  let inFlight = null;
  const notify = (state) => {
    if (state === lastState) return;
    lastState = state;
    window.webkit?.messageHandlers?.petState?.postMessage(state);
  };
  const style = document.createElement('style');
  style.textContent = `
    body[data-pet-layout="compact"] .shell { display:block; }
    body[data-pet-layout="compact"] .shell > aside { display:none; }
    body[data-pet-layout="compact"] .shell > main { padding:16px; height:100dvh; }
    body[data-pet-layout="compact"] .assistant-layout { grid-template-columns:minmax(0,1fr); }
    body[data-pet-layout="compact"] .assistant-layout.has-review { overflow:auto; }
    body[data-pet-layout="compact"] .assistant-layout.has-review .chat-area { min-height:340px; }
    body[data-pet-layout="compact"] .chat-toolbar p { font-size:12px; }
    body[data-pet-layout="compact"] .auth { padding:24px; min-height:100dvh; }
  `;
  document.head.append(style);
  document.body.dataset.petLayout = 'compact';
  const navigate = (page) => {
    if (!pages.includes(page)) return false;
    desiredPage = page;
    const button = [...document.querySelectorAll('.shell > aside nav button')]
      .find((b) => b.textContent.trim() === (page === '作业' ? '待办 / 作业' : page));
    if (!button) return false;
    button.click(); desiredPage = null;
    return true;
  };
  const observe = () => {
    if (desiredPage) navigate(desiredPage);
    const status = document.querySelector('.chat [role="status"]')?.textContent?.trim() || '';
    if (document.querySelector('.chat-area [role="alert"], main.auth [role="alert"]')) notify('error');
    else if (backendState) notify(backendState);
    else if (status.includes('等待') || document.querySelector('.review-panel')) notify('approval');
    else if (status.includes('回复')) notify('replying');
    else if (status) notify('thinking');
    else if (!lastState) notify('idle');
  };
  // Read the durable state even when React unmounts the chat page. One request
  // at a time; review navigation can share the same in-flight request.
  const refreshState = () => {
    if (inFlight) return inFlight;
    inFlight = (async () => {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);
      try {
        const response = await fetch('/api/agent/pet-state', { credentials:'same-origin', cache:'no-store', signal:controller.signal });
        if (response.status === 401) { backendState = 'idle'; reviewThread = null; observe(); return; }
        if (!response.ok) throw new Error('Pet state unavailable');
        const value = await response.json();
        if (!['idle', 'thinking', 'replying', 'approval'].includes(value.state)) throw new Error('Invalid pet state');
        backendState = value.state;
        reviewThread = typeof value.review_thread_id === 'string' ? value.review_thread_id : null;
        observe();
      } finally { clearTimeout(timeout); }
    })().finally(() => { inFlight = null; });
    return inFlight;
  };
  let failures = 0;
  const poll = async () => {
    try { await refreshState(); failures = 0; }
    catch { backendState = 'error'; notify('error'); failures = Math.min(failures + 1, 3); }
    setTimeout(poll, 1000 * 2 ** failures);
  };
  let queued = false;
  new MutationObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; observe(); });
  }).observe(document.body, {childList:true, subtree:true, characterData:true});
  document.addEventListener('submit', (event) => {
    if (event.target.matches('.composer')) notify('thinking');
  }, true);
  window.__campusPet = {
    navigate,
    layout: (compact) => { document.body.dataset.petLayout = compact ? 'compact' : 'full'; },
    showReview: async () => {
      try { await refreshState(); } catch { notify('error'); }
      navigate('助手');
      window.dispatchEvent(new CustomEvent('campus-pet-review', { detail:{ threadId:reviewThread } }));
    },
  };
  document.defaultView.addEventListener('campus-after-class-ready', () => {
    window.webkit?.messageHandlers?.petState?.postMessage('after-class-due');
  });
  document.defaultView.addEventListener('campus-calendar-saved', () => {
    window.webkit?.messageHandlers?.petState?.postMessage('calendar-saved');
  });
  observe();
  void poll();
})();
