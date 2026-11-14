'use strict';
const decisions = {
  repair: {
    label: 'STABILITY OBJECTIVE NOT MET',
    title: 'Repair first. Restore quickly.',
    body: 'The incident resolves, but the documented station-stability objective fails. The trade-off is faster direct intervention without reducing noncritical demand first.',
    fill: '43%',
  },
  shed: {
    label: 'STABILITY PROTECTED',
    title: 'Reduce loads. Then repair.',
    body: 'The training simulator and laboratory analyzer are temporarily turned off before repair. Station stability is protected, while some scientific and training work pauses.',
    fill: '90%',
  },
};
for (const button of document.querySelectorAll('[data-choice]')) {
  button.addEventListener('click', () => {
    const choice = decisions[button.dataset.choice];
    if (!choice) return;
    for (const other of document.querySelectorAll('[data-choice]')) {
      other.setAttribute('aria-pressed', String(other === button));
    }
    document.getElementById('indicator').textContent = choice.label;
    document.getElementById('result-title').textContent = choice.title;
    document.getElementById('result-body').textContent = choice.body;
    document.getElementById('gauge-fill').style.width = choice.fill;
  });
}
fetch('./content.json', {cache:'no-cache'})
  .then(response => {
    if (!response.ok) throw new Error('Media manifest unavailable');
    return response.json();
  })
  .then(data => {
    const actions = document.getElementById('demo-actions');
    const videoArea = document.getElementById('video-area');
    const validHttpsUrl = value => {
      if (typeof value !== 'string' || !value.trim()) return null;
      try {
        const u = new URL(value, window.location.href);
        return u.protocol === 'https:' || (u.origin === window.location.origin && u.protocol === 'http:') ? u.href : null;
      } catch {
        return null;
      }
    };
    const live = validHttpsUrl(data.liveDemoUrl);
    if (live) {
      const button = document.createElement('a');
      button.className='action primary';
      button.href=live;
      button.target='_blank';
      button.rel='noopener noreferrer';
      button.textContent=(typeof data.liveDemoLabel === 'string' ? data.liveDemoLabel : 'Play live ODYSSEY') + ' ↗';
      actions.replaceChildren(button);
      document.getElementById('demo-description').textContent='Open the separate live stream when available. Streaming service availability may vary by session.';
    }
    const video = validHttpsUrl(data.videoUrl);
    if (video) {
      const player=document.createElement('video');
      player.controls=true;
      player.playsInline=true;
      player.preload='metadata';
      player.setAttribute('aria-label', typeof data.videoCaption === 'string' ? data.videoCaption : 'Project video');
      player.src=video;
      videoArea.replaceChildren(player);
    }
  }).catch(() => {
    // Keep the non-interactive media placeholder visible when no media is configured.
  });
