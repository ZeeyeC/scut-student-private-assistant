(() => {
  if (window.__campusPet) return;
  const pages = ['助手', '今日', '课表', '作业', '设置'];
  let lastState = '';
  let desiredPage = '助手';
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
    else if (status.includes('等待') || document.querySelector('.review-panel')) notify('approval');
    else if (status.includes('回复')) notify('replying');
    else if (status) notify('thinking');
    else notify('idle');
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
  };
  document.defaultView.addEventListener('campus-after-class-ready', () => {
    window.webkit?.messageHandlers?.petState?.postMessage('after-class-due');
  });
  document.defaultView.addEventListener('campus-calendar-saved', () => {
    window.webkit?.messageHandlers?.petState?.postMessage('calendar-saved');
  });
  observe();
})();
