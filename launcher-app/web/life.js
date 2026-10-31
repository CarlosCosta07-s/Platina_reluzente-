(function () {
  'use strict';
  // Personality layer: intro animation, ambient particles, card tilt, greeting,
  // session counter, optional UI sounds and an easter egg. It never touches the
  // launcher's game logic and degrades silently if anything here fails.
  const doc = document;
  const root = doc.documentElement;
  const reduceMotion = Boolean(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  function store(key, value) {
    try {
      if (value === undefined) return window.localStorage.getItem(key);
      window.localStorage.setItem(key, value);
    } catch (error) { /* storage can be unavailable; the UI must still work */ }
    return null;
  }
  const byId = (id) => doc.getElementById(id);

  // ---------- Intro / splash ----------
  const splash = byId('splash');
  let ready = false;
  function finishIntro() {
    if (ready) return;
    ready = true;
    root.classList.add('is-ready');
    if (splash) {
      splash.classList.add('leaving');
      setTimeout(() => { if (splash.parentNode) splash.parentNode.removeChild(splash); }, 700);
    }
  }
  let seenThisSession = false;
  try { seenThisSession = window.sessionStorage.getItem('platina:intro') === '1'; } catch (error) { /* ignore */ }
  if (!splash || reduceMotion || seenThisSession) {
    if (splash && splash.parentNode) splash.parentNode.removeChild(splash);
    ready = true;
    root.classList.add('is-ready');
  } else {
    try { window.sessionStorage.setItem('platina:intro', '1'); } catch (error) { /* ignore */ }
    const timer = setTimeout(finishIntro, 2300);
    const skip = () => { clearTimeout(timer); finishIntro(); };
    splash.addEventListener('click', skip);
    window.addEventListener('keydown', skip, { once: true });
  }

  // Staggered reveal of the main blocks once the intro ends.
  ['.topbar', '.library-heading', '.library-toolbar', '.game-library-grid', '.selected-game-panel', '.project-status-section']
    .forEach((selector, index) => {
      const element = doc.querySelector(selector);
      if (!element) return;
      element.setAttribute('data-reveal', '');
      element.style.setProperty('--i', String(index));
    });

  // ---------- Greeting by time of day ----------
  const subtitle = doc.querySelector('.library-subtitle');
  if (subtitle) {
    const hour = new Date().getHours();
    const greeting = hour < 5 ? 'Boa madrugada' : hour < 12 ? 'Bom dia' : hour < 18 ? 'Boa tarde' : 'Boa noite';
    subtitle.textContent = greeting + '! Seus jogos e projetos nativos em um só lugar.';
  }

  // ---------- Session counter (stored only on this device) ----------
  const statsElement = byId('session-stats');
  function formatLast(iso) {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return '';
    const time = date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    const today = new Date();
    const dayDiff = Math.round((new Date(today.getFullYear(), today.getMonth(), today.getDate())
      - new Date(date.getFullYear(), date.getMonth(), date.getDate())) / 86400000);
    if (dayDiff === 0) return 'hoje às ' + time;
    if (dayDiff === 1) return 'ontem às ' + time;
    return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) + ' às ' + time;
  }
  function renderStats() {
    if (!statsElement) return;
    const count = parseInt(store('platina:sessions') || '0', 10) || 0;
    if (!count) { statsElement.hidden = true; return; }
    const last = formatLast(store('platina:lastSession') || '');
    statsElement.textContent = 'Sessões iniciadas neste aparelho: ' + count + (last ? ' · última ' + last : '');
    statsElement.hidden = false;
  }
  renderStats();
  window.addEventListener('platina:launched', (event) => {
    if (!event.detail || !event.detail.ok) return;
    const count = (parseInt(store('platina:sessions') || '0', 10) || 0) + 1;
    store('platina:sessions', String(count));
    store('platina:lastSession', new Date().toISOString());
    renderStats();
  });

  // ---------- Toast ----------
  const toast = doc.createElement('div');
  toast.className = 'toast';
  toast.setAttribute('role', 'status');
  toast.setAttribute('aria-live', 'polite');
  doc.body.appendChild(toast);
  let toastTimer = null;
  function showToast(message) {
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), 3200);
  }

  // ---------- Optional UI sounds (off by default) ----------
  let soundOn = store('platina:sound') === '1';
  let audio = null;
  function tone(frequency, start, length, type, volume) {
    const oscillator = audio.createOscillator();
    const gain = audio.createGain();
    oscillator.type = type || 'sine';
    oscillator.frequency.value = frequency;
    gain.gain.setValueAtTime(0.0001, audio.currentTime + start);
    gain.gain.exponentialRampToValueAtTime(volume || 0.05, audio.currentTime + start + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + start + length);
    oscillator.connect(gain);
    gain.connect(audio.destination);
    oscillator.start(audio.currentTime + start);
    oscillator.stop(audio.currentTime + start + length + 0.02);
  }
  function sfx(kind) {
    if (!soundOn) return;
    try {
      const Context = window.AudioContext || window.webkitAudioContext;
      if (!Context) return;
      audio = audio || new Context();
      if (audio.state === 'suspended') audio.resume();
      if (kind === 'move') tone(880, 0, 0.07, 'triangle');
      else if (kind === 'select') { tone(660, 0, 0.09, 'triangle'); tone(990, 0.08, 0.12, 'triangle'); }
      else if (kind === 'launch') { [523, 659, 784, 1047].forEach((f, i) => tone(f, i * 0.09, 0.18, 'sine', 0.06)); }
      else if (kind === 'on') tone(740, 0, 0.1, 'sine');
    } catch (error) { /* audio is optional */ }
  }
  const topRight = doc.querySelector('.top-right');
  if (topRight) {
    const button = doc.createElement('button');
    button.type = 'button';
    button.className = 'sound-toggle';
    const render = () => {
      button.textContent = soundOn ? '🔊' : '🔇';
      button.setAttribute('aria-pressed', String(soundOn));
      button.setAttribute('aria-label', soundOn ? 'Desativar sons da interface' : 'Ativar sons da interface');
      button.title = soundOn ? 'Sons ligados' : 'Sons desligados';
    };
    render();
    button.addEventListener('click', () => {
      soundOn = !soundOn;
      store('platina:sound', soundOn ? '1' : '0');
      render();
      sfx('on');
    });
    topRight.insertBefore(button, topRight.firstChild);
  }
  doc.querySelectorAll('.game-card').forEach((card) => card.addEventListener('click', () => sfx('select')));
  const launchButton = byId('launch-button');
  if (launchButton) launchButton.addEventListener('click', () => sfx('launch'));
  window.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') sfx('move');
  });

  // ---------- Card tilt (mouse only) ----------
  if (!reduceMotion) {
    doc.querySelectorAll('.game-card').forEach((card) => {
      card.addEventListener('pointermove', (event) => {
        if (event.pointerType !== 'mouse') return;
        const box = card.getBoundingClientRect();
        const px = (event.clientX - box.left) / box.width - 0.5;
        const py = (event.clientY - box.top) / box.height - 0.5;
        card.style.setProperty('--rx', (-py * 7).toFixed(2) + 'deg');
        card.style.setProperty('--ry', (px * 9).toFixed(2) + 'deg');
      });
      card.addEventListener('pointerleave', () => {
        card.style.setProperty('--rx', '0deg');
        card.style.setProperty('--ry', '0deg');
      });
    });
  }

  // ---------- Ambient platinum sparkles ----------
  if (!reduceMotion) {
    const canvas = doc.createElement('canvas');
    canvas.className = 'sparkles';
    canvas.setAttribute('aria-hidden', 'true');
    doc.body.insertBefore(canvas, doc.body.firstChild);
    const context = canvas.getContext('2d');
    let width = 0;
    let height = 0;
    let dots = [];
    let frame = 0;
    let last = 0;
    const rand = (min, max) => min + Math.random() * (max - min);
    function resize() {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      canvas.style.width = width + 'px';
      canvas.style.height = height + 'px';
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      const count = Math.min(60, Math.max(18, Math.round((width * height) / 32000)));
      dots = Array.from({ length: count }, () => ({
        x: rand(0, width), y: rand(0, height), r: rand(0.7, 2.2),
        vx: rand(-4, 4), vy: rand(-14, -4), phase: rand(0, Math.PI * 2), speed: rand(0.6, 1.8),
        star: Math.random() < 0.22
      }));
    }
    function draw(now) {
      frame = requestAnimationFrame(draw);
      const delta = Math.min((now - last) / 1000 || 0.016, 0.05);
      last = now;
      context.clearRect(0, 0, width, height);
      for (const dot of dots) {
        dot.x += dot.vx * delta;
        dot.y += dot.vy * delta;
        dot.phase += dot.speed * delta;
        if (dot.y < -10) { dot.y = height + 10; dot.x = rand(0, width); }
        if (dot.x < -10) dot.x = width + 10;
        if (dot.x > width + 10) dot.x = -10;
        const alpha = 0.12 + 0.28 * (0.5 + 0.5 * Math.sin(dot.phase));
        context.fillStyle = 'rgba(190, 222, 255, ' + alpha.toFixed(3) + ')';
        if (dot.star) {
          const s = dot.r * 3;
          context.beginPath();
          context.moveTo(dot.x, dot.y - s);
          context.quadraticCurveTo(dot.x, dot.y, dot.x + s, dot.y);
          context.quadraticCurveTo(dot.x, dot.y, dot.x, dot.y + s);
          context.quadraticCurveTo(dot.x, dot.y, dot.x - s, dot.y);
          context.quadraticCurveTo(dot.x, dot.y, dot.x, dot.y - s);
          context.fill();
        } else {
          context.beginPath();
          context.arc(dot.x, dot.y, dot.r, 0, Math.PI * 2);
          context.fill();
        }
      }
    }
    function start() { if (!frame) { last = performance.now(); frame = requestAnimationFrame(draw); } }
    function stop() { if (frame) { cancelAnimationFrame(frame); frame = 0; } }
    resize();
    start();
    window.addEventListener('resize', resize);
    doc.addEventListener('visibilitychange', () => (doc.hidden ? stop() : start()));
  }

  // ---------- Easter egg: ↑ ↑ ↓ ↓ ← → ← → B A ----------
  const code = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'b', 'a'];
  let progress = 0;
  let chromeTimer = null;
  window.addEventListener('keydown', (event) => {
    const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
    progress = key === code[progress] ? progress + 1 : (key === code[0] ? 1 : 0);
    if (progress !== code.length) return;
    progress = 0;
    doc.body.classList.add('chrome-mode');
    showToast('✨ Modo Platina Cromada ativado!');
    sfx('launch');
    clearTimeout(chromeTimer);
    chromeTimer = setTimeout(() => doc.body.classList.remove('chrome-mode'), 9000);
  });
}());
