// Settings stay usable when browser storage is unavailable.
const preferences = {mode: 'auto', font: 'normal'};
try {
    const mode = localStorage.getItem('mode');
    const font = localStorage.getItem('font');
    if (['auto','dark','light'].includes(mode)) preferences.mode = mode;
    if (['small','normal','large'].includes(font)) preferences.font = font;
} catch (_) { /* Private or restricted storage: keep in-memory preferences. */ }
function savePreference(key, value) {
    preferences[key] = value;
    try { localStorage.setItem(key, value); } catch (_) {}
}
function closeSettings(returnFocus = false) {
    const menu = document.getElementById('menu');
    menu.hidden = true;
    menu.classList.remove('open');
    document.getElementById('settings-toggle').setAttribute('aria-expanded', 'false');
    if (returnFocus) document.getElementById('settings-toggle').focus();
}
function toggleMenu() {
    const menu = document.getElementById('menu');
    if (!menu.hidden) { closeSettings(); return; }
    menu.hidden = false;
    menu.classList.add('open');
    document.getElementById('settings-toggle').setAttribute('aria-expanded', 'true');
}
function applyTheme(mode) {
    const effective = mode === 'auto' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : mode;
    document.body.classList.remove('dark','light');
    document.body.classList.add(effective);
}
function updateActiveButtons() {
    for (const [group, value] of [['theme', preferences.mode], ['font', preferences.font]]) {
        document.querySelectorAll(`[id^="${group}-"][id$="-btn"]`).forEach(button => {
            const active = button.id === `${group}-${value}-btn`;
            button.classList.toggle('active', active);
            button.setAttribute('aria-pressed', String(active));
        });
    }
}
function setMode(mode) {
    if (!['auto','dark','light'].includes(mode)) return;
    savePreference('mode',mode);
    applyTheme(mode);
    updateActiveButtons();
}
function setFont(size, persist = true) {
    if (!['small','normal','large'].includes(size)) return;
    if (persist) savePreference('font',size);
    document.body.classList.remove('font-small','font-normal','font-large');
    document.body.classList.add('font-'+size);
    updateActiveButtons();
}
applyTheme(preferences.mode);
setFont(preferences.font, false);
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (preferences.mode === 'auto') applyTheme('auto');
});
document.addEventListener('click', event => {
    if (!event.target.closest('.settings')) closeSettings();
});
document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !document.getElementById('menu').hidden) closeSettings(true);
});
document.addEventListener('focusin', event => {
    if (!event.target.closest('.settings')) closeSettings();
});
// Small previews remain readable by opening their original local SVG.
function addTheoryDiagramLinks() {
    document.querySelectorAll('.study-page .theory-text img').forEach((image) => {
        const source = new URL(image.src, window.location.href);
        if (source.origin !== window.location.origin ||
            !source.pathname.startsWith('/static/images/theory/')) return;
        const link = document.createElement('a');
        link.href = source.href;
        link.target = '_blank';
        link.rel = 'noopener';
        link.className = 'theory-diagram-link';
        link.textContent = 'Άνοιγμα σχήματος σε πλήρες μέγεθος';
        image.insertAdjacentElement('afterend', link);
    });
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', addTheoryDiagramLinks, { once: true });
} else {
    addTheoryDiagramLinks();
}
