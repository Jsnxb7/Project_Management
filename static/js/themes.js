let themeKits = [];
let currentKitId = "neo_mint";

function hexToRgba(hex, alpha) {
    const clean = String(hex || "#000000").replace("#", "");
    const full = clean.length === 3 ? clean.split("").map(ch => ch + ch).join("") : clean;
    const num = parseInt(full, 16);
    const r = (num >> 16) & 255;
    const g = (num >> 8) & 255;
    const b = num & 255;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function readThemeForm() {
    const bg = document.getElementById('backgroundColor').value;
    const sidebar = document.getElementById('sidebarColor').value;
    return {
        kit_id: currentKitId || "custom",
        name: document.getElementById('themeName').value || 'Custom Theme',
        primary: document.getElementById('primaryColor').value,
        secondary: document.getElementById('secondaryColor').value,
        background: bg,
        surface: hexToRgba(bg, 0.78),
        surface2: hexToRgba(bg, 0.88),
        text: document.getElementById('textColor').value,
        text2: document.getElementById('textColor').value,
        muted: document.getElementById('mutedColor').value,
        sidebar: hexToRgba(sidebar, 0.88),
        radius: document.getElementById('themeRadius').value,
        density: document.getElementById('themeDensity').value,
        video_opacity: document.getElementById('videoOpacity').value,
    };
}

function rgbaToHex(value, fallback) {
    if (!value) return fallback;
    if (String(value).startsWith('#')) return value;
    const parts = String(value).match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
    if (!parts) return fallback;
    return '#' + [parts[1], parts[2], parts[3]].map(n => Number(n).toString(16).padStart(2, '0')).join('');
}

function fillTheme(theme) {
    if (!theme) return;
    currentKitId = theme.kit_id || "custom";
    document.getElementById('themeName').value = theme.name || 'Neo Mint';
    document.getElementById('primaryColor').value = theme.primary || '#78e0c2';
    document.getElementById('secondaryColor').value = theme.secondary || '#8fb7ff';
    document.getElementById('backgroundColor').value = rgbaToHex(theme.background, '#080b12');
    document.getElementById('textColor').value = rgbaToHex(theme.text, '#f8fbff');
    document.getElementById('mutedColor').value = rgbaToHex(theme.muted, '#91a4b8');
    document.getElementById('sidebarColor').value = rgbaToHex(theme.sidebar, '#080b12');
    document.getElementById('themeRadius').value = theme.radius || '8px';
    document.getElementById('themeDensity').value = theme.density || 'comfortable';
    document.getElementById('videoOpacity').value = theme.video_opacity || '0.12';
    highlightActiveKit();
}

function renderThemeKits(kits) {
    const grid = document.getElementById('themeKitGrid');
    if (!grid) return;
    grid.innerHTML = kits.map(kit => `
        <button class="theme-kit-card" type="button" data-kit-id="${escapeHTML(kit.kit_id)}">
            <div class="theme-swatch-row">
                <span class="theme-swatch" style="background:${escapeHTML(kit.primary)}"></span>
                <span class="theme-swatch" style="background:${escapeHTML(kit.secondary)}"></span>
                <span class="theme-swatch" style="background:${escapeHTML(kit.background)}"></span>
                <span class="theme-swatch" style="background:${escapeHTML(rgbaToHex(kit.sidebar, kit.background))}"></span>
            </div>
            <strong>${escapeHTML(kit.name)}</strong>
            <span>${escapeHTML(kit.description || '')}</span>
        </button>
    `).join('');
    grid.querySelectorAll('[data-kit-id]').forEach(card => {
        card.addEventListener('click', () => {
            const kit = themeKits.find(item => item.kit_id === card.dataset.kitId);
            if (!kit) return;
            fillTheme(kit);
            applyTheme(kit);
        });
    });
    highlightActiveKit();
}

function highlightActiveKit() {
    document.querySelectorAll('.theme-kit-card').forEach(card => card.classList.toggle('active', card.dataset.kitId === currentKitId));
}

async function loadThemePage() {
    if (!requireAuth()) return;
    const res = await fetch('/api/theme/me', {headers: authHeaders(false)});
    const data = await res.json();
    if (!data.success) return toast(data.message || 'Theme load failed', false);
    themeKits = data.data.kits || [];
    renderThemeKits(themeKits);
    fillTheme(data.data.theme);
    applyTheme(data.data.theme);
}

['themeName','primaryColor','secondaryColor','backgroundColor','textColor','mutedColor','sidebarColor','themeRadius','themeDensity','videoOpacity'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', () => {
        currentKitId = "custom";
        const theme = readThemeForm();
        applyTheme(theme);
        highlightActiveKit();
    });
});

document.getElementById('themeForm')?.addEventListener('submit', async e => {
    e.preventDefault();
    const theme = readThemeForm();
    const res = await fetch('/api/theme/me', {method:'PUT', headers: authHeaders(), body: JSON.stringify(theme)});
    const data = await res.json();
    if (!data.success) return toast(data.message || 'Theme save failed', false);
    localStorage.setItem('userTheme', JSON.stringify(data.data.theme));
    applyTheme(data.data.theme);
    toast('Theme saved permanently for your user');
});

document.getElementById('resetThemeBtn')?.addEventListener('click', async () => {
    const kit = themeKits.find(item => item.kit_id === 'neo_mint') || themeKits[0];
    if (!kit) return;
    fillTheme(kit);
    applyTheme(kit);
    const res = await fetch('/api/theme/me', {method:'PUT', headers: authHeaders(), body: JSON.stringify(kit)});
    const data = await res.json();
    if (data.success) {
        localStorage.setItem('userTheme', JSON.stringify(data.data.theme));
        toast('Theme reset to Neo Mint');
    }
});

loadThemePage();
