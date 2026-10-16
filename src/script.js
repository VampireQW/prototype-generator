/**
 * 原型生成器前端脚本
 * 简化版：AI调用在后端完成
 */

// ==================== 状态管理 ====================
let pages = [];
let pageFiles = {};
let pagePptImages = {};
let allProjects = [];
let searchQuery = '';
let currentRecordProject = null; // 当前查看的记录项目

// ==================== 协作状态 ====================
let currentUser = null;   // {id, username, displayName}
let userTeams = [];       // [{id, name, role, inviteCode}]
let currentTab = 'my';    // 'my' | 'team'
let selectedTeamId = null;

// ==================== 模型管理 ====================
let modelsList = [];
let currentModel = null;
let selectedModelId = '';
let designSystemsList = [];
let customColorFields = new Set();
let skillsList = [];
let pptInputMode = 'import'; // import | pages
let activeReferenceDropZoneId = null;
const MAX_REFERENCE_IMAGES_PER_PAGE = 5;
const MAX_PPT_IMAGES_PER_SLIDE = 5;
const MAX_AI_IMAGES_PER_REQUEST = 16;

function isSupportedRasterDataUrl(dataUrl) {
    try {
        if (!dataUrl || !dataUrl.includes(',')) return false;
        const base64 = dataUrl.split(',', 2)[1];
        const binary = atob(base64.slice(0, 64));
        const bytes = Array.from(binary, ch => ch.charCodeAt(0));
        const textHead = binary.slice(0, 12);
        const isPng = bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4E && bytes[3] === 0x47;
        const isJpeg = bytes[0] === 0xFF && bytes[1] === 0xD8 && bytes[2] === 0xFF;
        const isGif = textHead.startsWith('GIF87a') || textHead.startsWith('GIF89a');
        const isWebp = textHead.startsWith('RIFF') && textHead.slice(8, 12) === 'WEBP';
        return isPng || isJpeg || isGif || isWebp;
    } catch (e) {
        return false;
    }
}

const SKILL_INPUT_MODES = {
    'web-prototype': {
        unitLabel: '页面',
        addLabel: '添加新页面',
        pagePlaceholder: '页面名称（如：首页、用户列表）',
        layoutLabel: '布局描述',
        layoutPlaceholder: '描述页面的布局结构...\n如：顶部导航、左侧菜单、右侧内容区',
        featuresLabel: '核心功能',
        featuresPlaceholder: '- 表格排序筛选\n- 数据导出',
        interactionLabel: '交互说明',
        interactionPlaceholder: '点击按钮 → 弹出模态框',
        recommendedDesignSystems: ['linear-app', 'vercel', 'shadcn', 'apple', 'notion']
    },
    dashboard: {
        unitLabel: '页面',
        addLabel: '添加新页面',
        pagePlaceholder: '页面名称（如：经营看板、用户分析）',
        layoutLabel: '布局描述',
        layoutPlaceholder: '描述页面的布局结构...\n如：顶部导航、左侧菜单、右侧内容区',
        featuresLabel: '核心功能',
        featuresPlaceholder: '- 表格排序筛选\n- 数据导出',
        interactionLabel: '交互说明',
        interactionPlaceholder: '点击按钮 → 弹出模态框',
        recommendedDesignSystems: ['linear-app', 'github', 'vercel', 'shadcn', 'figma']
    },
    'mobile-app': {
        unitLabel: '页面',
        addLabel: '添加新页面',
        pagePlaceholder: '页面名称（如：首页、详情页、支付页）',
        layoutLabel: '布局描述',
        layoutPlaceholder: '描述页面的布局结构...\n如：顶部导航、左侧菜单、右侧内容区',
        featuresLabel: '核心功能',
        featuresPlaceholder: '- 表格排序筛选\n- 数据导出',
        interactionLabel: '交互说明',
        interactionPlaceholder: '点击按钮 → 弹出模态框',
        recommendedDesignSystems: ['apple', 'material', 'xiaohongshu', 'notion', 'duolingo']
    },
    'saas-landing': {
        unitLabel: '页面',
        addLabel: '添加新页面',
        pagePlaceholder: '页面名称（如：首页、产品介绍、定价页）',
        layoutLabel: '布局描述',
        layoutPlaceholder: '描述页面的布局结构...\n如：顶部导航、左侧菜单、右侧内容区',
        featuresLabel: '核心功能',
        featuresPlaceholder: '- 表格排序筛选\n- 数据导出',
        interactionLabel: '交互说明',
        interactionPlaceholder: '点击按钮 → 弹出模态框',
        recommendedDesignSystems: ['stripe', 'linear-app', 'vercel', 'supabase', 'framer']
    },
    'html-ppt': {
        unitLabel: '章节',
        addLabel: '添加章节',
        pagePlaceholder: 'PPT 标题（可选）',
        layoutLabel: '布局/内容描述',
        layoutPlaceholder: '写 PPT 主题、页数、受众、章节大纲、每页核心观点；也可以直接粘贴完整大纲',
        featuresLabel: '',
        featuresPlaceholder: '',
        interactionLabel: '动画描述',
        interactionPlaceholder: '描述主题风格、转场、动效、是否需要演讲者备注/逐字稿',
        compactPpt: true,
        recommendedDesignSystems: ['xiaohongshu', 'apple', 'stripe', 'linear-app', 'editorial']
    }
};

const DESIGN_SYSTEM_RECOMMENDED_FALLBACK = ['linear-app', 'apple', 'vercel', 'notion', 'xiaohongshu', 'stripe', 'figma', 'shadcn', 'default'];

// ==================== 增量更新相关 ====================
let sourceProjectId = null;       // 来源项目ID（用于增量更新）
let originalFormData = null;      // 原始表单数据快照
let originalImageHashes = {};     // 原始图片哈希 { pageIndex: hash }

// ==================== DOM 元素 ====================
const $ = (id) => document.getElementById(id);

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', async () => {
    setupEventListeners();
    HomeUI.init();
    addPage();
    await checkAuth();
    const params = new URLSearchParams(window.location.search);
    let homeSource = 'local';
    try { homeSource = localStorage.getItem('prototype-home-source') || 'local'; } catch (_) { /* 使用默认来源 */ }
    if (params.get('tab') === 'team' && currentUser) {
        switchProjectSource('ai');
        await switchProjectTab('team');
    } else switchProjectSource(homeSource);
    await Promise.all([loadModels(), loadDesignSystems(), loadSkills()]);
    HomeUI.summary();
});

// ==================== 外部项目（任意文件夹原型，可标注） ====================

function toggleExternalAdd() {
    const box = $('externalAddBox');
    box.classList.toggle('hidden');
    $('extAddToggleBtn').setAttribute('aria-expanded', String(!box.classList.contains('hidden')));
    if (!box.classList.contains('hidden')) $('externalPathInput').focus();
}

// 顶部「选择文件夹/粘贴路径」操作区默认收起为 header 右上角小按钮
function collapseExternalAddPanel() {
    $('externalAddPanel').classList.add('hidden');
    $('extAddPanelToggle').setAttribute('aria-expanded', 'false');
    $('externalAddBox').classList.add('hidden');
    $('extAddToggleBtn').setAttribute('aria-expanded', 'false');
    if ($('externalAddPanel').contains(document.activeElement)) $('extAddPanelToggle').focus({preventScroll: true});
}
function toggleExternalAddPanel() {
    if ($('externalAddPanel').classList.contains('hidden')) {
        $('externalAddPanel').classList.remove('hidden');
        $('extAddPanelToggle').setAttribute('aria-expanded', 'true');
        $('externalPickBtn').focus({preventScroll: true});
    } else collapseExternalAddPanel();
}

let externalLoading = false;
let externalAdding = false;
let externalProjects = [];
function externalStatus(text, error = false) {
    $('externalStatus').textContent = text;
    $('externalStatus').dataset.error = String(error);
}
async function externalPost(route, body) {
    const response = await fetch('/api/external/' + route, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
    });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || '操作失败');
    return data;
}
async function loadExternalProjects() {
    if (externalLoading) return;
    externalLoading = true;
    HomeUI.loading($('externalList'));
    document.querySelector('[aria-label="刷新本地项目"]').classList.add('is-loading');
    $('externalList').setAttribute('aria-busy', 'true');
    externalStatus('正在扫描…');
    try {
        const resp = await fetch('/api/external/list');
        const data = await resp.json();
        if (!resp.ok || !data.ok) throw new Error(data.error || '无法读取本地项目');
        renderExternalProjects(data.items || [], data.discovered || []);
        const roots = $('externalRoots');
        roots.replaceChildren();
        for (const path of data.roots || []) {
            const row = document.createElement('div'); row.className = 'ep-root';
            row.innerHTML = HomeUI.icon('folder');
            const label = document.createElement('span'); label.className = 'ep-root-path'; label.textContent = path; label.title = path;
            const button = document.createElement('button'); button.className = 'app-icon-button ep-root-remove'; button.type = 'button'; button.textContent = '×';
            button.setAttribute('aria-label', '停止监视 ' + path);
            button.title = '停止监视 ' + path;
            button.onclick = async () => {
                if (!confirm('停止监视此目录？已连接项目和磁盘文件会保留。')) return;
                try { await externalPost('roots/remove', {path}); loadExternalProjects(); }
                catch (e) { externalStatus(e.message, true); }
            };
            row.append(label, button); roots.append(row);
        }
        const errors = data.errors || [];
        externalStatus(errors.length ? errors.map(e => `${e.root}：${e.error}`).join('；') :
            `${data.items.length} 个已连接 · ${(data.discovered || []).length} 个新发现`, errors.length > 0);
    } catch (e) {
        externalStatus(e.message, true);
        if (!externalProjects.length) HomeUI.empty($('externalList'), '项目读取失败', e.message, '重试', loadExternalProjects, 'error');
    }
    finally { externalLoading = false; $('externalList').setAttribute('aria-busy', 'false'); document.querySelector('[aria-label="刷新本地项目"]').classList.remove('is-loading'); }
}
window.addEventListener('focus', () => { if (!document.hidden) loadExternalProjects(); });
document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !$('externalAddPanel').classList.contains('hidden')) collapseExternalAddPanel();
});
document.addEventListener('visibilitychange', () => { if (!document.hidden) loadExternalProjects(); });

function renderExternalProjects(items, discovered = []) {
    const box = $('externalList');
    if (!box) return;
    if (items) externalProjects = [...items, ...discovered];
    const query = ($('externalSearch')?.value || '').trim().toLocaleLowerCase();
    const timestamp = (item) => {
        const created = Date.parse(item.createdAt);
        if (Number.isFinite(created)) return created;
        const added = Date.parse(item.addedAt);
        return Number.isFinite(added) ? added : 0;
    };
    const entries = externalProjects.filter(item =>
        `${item.name || ''} ${item.root || ''}`.toLocaleLowerCase().includes(query) &&
        (($('externalFilter')?.value || 'all') === 'all' ||
         ($('externalFilter').value === 'discovered' && item.discovered) ||
         ($('externalFilter').value === 'connected' && item.exists && !item.discovered) ||
         ($('externalFilter').value === 'missing' && !item.exists))
    ).sort((a, b) => timestamp(b) - timestamp(a) ||
        (a.name || '').localeCompare(b.name || '', 'zh-CN', {numeric: true}));
    HomeUI.clear(box);
    const status = $('externalSearchStatus');
    status.hidden = !query;
    status.textContent = query ? `找到 ${entries.length} 个项目` : '';
    $('localResultCount').hidden = !!query;
    HomeUI.updateCounts('local', externalProjects.length, entries.length);
    if (!entries.length) {
        const filtered = !!query || $('externalFilter')?.value !== 'all';
        HomeUI.empty(box, filtered ? '没有匹配的项目' : '还没有本地原型', filtered ? '换个关键词，或清除筛选后查看全部项目。' : '添加一个项目文件夹，开始预览和标注。', filtered ? '清除筛选' : '添加本地项目', () => { if (filtered) { $('externalSearch').value = ''; $('externalFilter').value = 'all'; renderExternalProjects(); } else toggleExternalAddPanel(); });
    }
    for (const item of entries) box.append(buildExternalCard(item));
}

// 项目卡片与 AI 项目列表共用 project-card 卡片语言（名称 + 状态徽标 + 底部操作条）
function buildExternalCard(item) {
    const open = () => item.discovered ? connectExternalProject(item) : openExternalProject(item.projectId);
    const { article, actions } = HomeUI.card({
        id: item.projectId || item.root, name: item.name, kind: 'local',
        badge: item.discovered ? '新发现' : item.exists ? '已连接' : '目录失效',
        tone: item.discovered ? 'warning' : item.exists ? 'success' : 'danger',
        badgeIcon: item.discovered ? 'spark' : item.exists ? 'check' : 'error',
        meta: item.exists ? `${item.pages} 个页面${HomeUI.formatDate(item.createdAt) ? ' · ' + HomeUI.formatDate(item.createdAt) : ''}` : '请检查项目路径',
        detail: item.root, open, disabled: !item.exists, preview: { source: 'local', id: item.projectId }
    });
    if (item.discovered) {
        actions.append(HomeUI.action('connect', `连接项目 ${item.name}`, open));
    } else {
        actions.append(
            HomeUI.action('open', `预览 ${item.name}`, open, { disabled: !item.exists }),
            HomeUI.action('publish', `发布 / 导出 ${item.name}`, () => openExtPublishModal(item), { disabled: !item.exists }),
            HomeUI.more(item.name, [
                ...(!item.exists ? [{icon: 'folder', label: '添加新的项目目录', handler: () => { toggleExternalAddPanel(); if ($('externalAddBox').classList.contains('hidden')) toggleExternalAdd(); }}] : []),
                { icon: 'remove', label: '移出列表，保留磁盘文件', handler: () => removeExternalProject(item.projectId) },
                { icon: 'delete', label: '删除项目及本地文件', danger: true, handler: () => deleteExternalProject(item.projectId, item.name, item.root) }
            ])
        );
    }
    return article;
}

const connectingProjects = new Set();
async function connectExternalProject(item) {
    if (connectingProjects.has(item.projectId)) return;
    connectingProjects.add(item.projectId);
    const card = [...document.querySelectorAll('#externalList .project-card')].find(el => el.dataset.projectId === item.projectId);
    const badge = card?.querySelector('.project-badge');
    card?.setAttribute('aria-busy', 'true');
    card?.querySelectorAll('button').forEach(button => { button.disabled = true; });
    if (badge) { badge.innerHTML = HomeUI.icon('clock'); badge.append(document.createTextNode('连接中')); }
    try { const data = await externalPost('add', {path: item.root}); window.location.href = data.viewerUrl; }
    catch (e) {
        externalStatus(e.message, true);
        card?.querySelectorAll('button').forEach(button => { button.disabled = false; });
        if (badge) { badge.innerHTML = HomeUI.icon('spark'); badge.append(document.createTextNode('新发现')); }
    } finally { connectingProjects.delete(item.projectId); card?.removeAttribute('aria-busy'); }
}

function openExternalProject(pid) {
    window.open(`viewer.html?ext=${encodeURIComponent(pid)}`, '_blank');
}

async function pickExternalFolder() {
    const button = $('externalPickBtn');
    if (button.disabled) return;
    button.disabled = true; button.textContent = '选择中…';
    try {
        const data = await externalPost('pick-folder', {});
        if (!data.cancelled) { $('externalPathInput').value = data.path; await addExternalProject(); }
    } catch (e) {
        externalStatus(e.message, true);
        $('externalAddPanel').classList.remove('hidden');
        $('extAddPanelToggle').setAttribute('aria-expanded', 'true');
        $('externalAddBox').classList.remove('hidden');
        $('extAddToggleBtn').setAttribute('aria-expanded', 'true');
    } finally { button.disabled = false; button.textContent = '选择文件夹'; }
}

async function addExternalProject() {
    if (externalAdding) return;
    const input = $('externalPathInput');
    const raw = (input.value || '').trim().replace(/^"|"$/g, '');
    if (!raw) { externalStatus('请先选择文件夹或粘贴路径', true); return; }
    externalAdding = true; $('externalPathAddBtn').disabled = true;
    try {
        const data = await externalPost('roots/add', {path: raw});
        input.value = '';
        collapseExternalAddPanel();
        if (data.connected) window.location.href = data.viewerUrl;
        else await loadExternalProjects();
    } catch (e) { externalStatus(e.message, true); }
    finally { externalAdding = false; $('externalPathAddBtn').disabled = false; }
}

async function removeExternalProject(pid) {
    const confirmed = await showAppConfirm({
        title: '移出列表',
        message: '从列表移除该外部项目？磁盘文件与标注数据不会被删除。',
        confirmText: '移出列表',
        tone: 'warning'
    });
    if (!confirmed) return;
    try {
        await externalPost('remove', {projectId: pid});
        loadExternalProjects();
    } catch (e) {
        showToast('移除失败：' + e.message, 'error');
    }
}

// 删除项目：两级确认，明确告知本地文件夹会一起删除且不可恢复
async function deleteExternalProject(pid, name, root) {
    const first = await showAppConfirm({
        title: '删除项目',
        message: `确定要删除项目「${name}」吗？\n\n删除同样意味着要把本地的文件夹一起删除：\n${root}\n\n文件夹里的全部页面和 .prototype 标注数据都会一起删除。`,
        confirmText: '继续',
        cancelText: '再想想',
        tone: 'danger'
    });
    if (!first) return;
    const second = await showAppConfirm({
        title: '最后确认',
        message: `本地文件夹将被永久删除，此操作不可恢复：\n${root}`,
        confirmText: '永久删除',
        cancelText: '取消',
        tone: 'danger'
    });
    if (!second) return;
    try {
        const data = await externalPost('delete', {projectId: pid});
        if (data.publishedUrl) {
            showToast('项目已删除；GitHub 评审站不会自动下线，如需移除请到仓库删除对应目录', 'info');
        } else {
            showToast(data.folderDeleted ? '项目与本地文件夹已删除' : '登记已移除（本地文件夹原本就不存在）');
        }
        loadExternalProjects();
    } catch (e) {
        showToast('删除失败：' + e.message, 'error');
        loadExternalProjects();
    }
}

// ==================== 轻提示浮层 ====================
let helpBubbleEl = null;
let helpBubblePinned = false;

function ensureHelpBubble() {
    if (helpBubbleEl) return helpBubbleEl;
    helpBubbleEl = document.createElement('div');
    helpBubbleEl.id = 'helpBubble';
    helpBubbleEl.className = 'fixed z-[9999] max-w-xs rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs leading-relaxed text-gray-700 shadow-xl hidden';
    document.body.appendChild(helpBubbleEl);
    return helpBubbleEl;
}

function showHelpBubble(anchor, text, pinned = false) {
    const bubble = ensureHelpBubble();
    bubble.textContent = text;
    bubble.classList.remove('hidden');
    helpBubblePinned = pinned;

    const rect = anchor.getBoundingClientRect();
    const top = Math.min(window.innerHeight - 80, rect.bottom + 8);
    const left = Math.min(window.innerWidth - 300, Math.max(12, rect.left - 8));
    bubble.style.top = `${top}px`;
    bubble.style.left = `${left}px`;
}

function hideHelpBubble(force = false) {
    if (!helpBubbleEl) return;
    if (helpBubblePinned && !force) return;
    helpBubbleEl.classList.add('hidden');
    helpBubblePinned = false;
}

function bindHelpBubble(id, getText) {
    const el = $(id);
    if (!el) return;
    el.addEventListener('mouseenter', () => showHelpBubble(el, getText(), false));
    el.addEventListener('mouseleave', () => hideHelpBubble(false));
    el.addEventListener('click', (e) => {
        e.stopPropagation();
        if (helpBubbleEl && !helpBubbleEl.classList.contains('hidden') && helpBubblePinned) {
            hideHelpBubble(true);
        } else {
            showHelpBubble(el, getText(), true);
        }
    });
}

document.addEventListener('click', () => hideHelpBubble(true));

// ==================== 事件监听 ====================
function setupEventListeners() {
    // 新建项目
    $('createNewBtn').onclick = createNewProject;

    // 添加页面
    $('addPageBtn').onclick = addPage;

    // AI生成
    $('aiGenerateBtn').onclick = generateWithAI;

    // 外部 AI 生成
    if ($('externalAiBtn')) {
        $('externalAiBtn').onclick = openExternalAiModal;
    }

    if ($('skillSelect')) {
        $('skillSelect').onchange = () => {
            updateInputModeForSkill();
            renderDesignSystemSelect(true);
        };
    }
    if ($('pptImportModeBtn')) {
        $('pptImportModeBtn').onclick = () => setPptInputMode('import');
    }
    if ($('pptPagesModeBtn')) {
        $('pptPagesModeBtn').onclick = () => setPptInputMode('pages');
    }
    if ($('designSystemSelect')) {
        $('designSystemSelect').onchange = updateDesignSystemHint;
    }
    if ($('designSystemPickerBtn')) {
        $('designSystemPickerBtn').onclick = (e) => {
            e.stopPropagation();
            toggleDesignSystemMenu();
        };
    }
    if ($('designSystemMenu')) {
        $('designSystemMenu').onclick = (e) => e.stopPropagation();
    }
    document.addEventListener('click', closeDesignSystemMenu);
    document.addEventListener('paste', handleGlobalReferencePaste);
    bindHelpBubble('designSystemHelp', () => $('designSystemHelp')?.dataset.help || '');
    bindHelpBubble('skillModeHelp', () => $('skillModeHelp')?.dataset.help || '');

    // 颜色选择器
    $('primaryColor').oninput = (e) => {
        customColorFields.add('primaryColor');
        $('primaryColorValue').textContent = e.target.value;
        updateDesignSystemHint();
    };
    $('secondaryColor').oninput = (e) => {
        customColorFields.add('secondaryColor');
        $('secondaryColorValue').textContent = e.target.value;
        updateDesignSystemHint();
    };
    if ($('backgroundMode')) {
        $('backgroundMode').onchange = updateDesignSystemHint;
    }
    $('customColorsToggle').onchange = () => {
        if (!$('customColorsToggle').checked) customColorFields.clear();
        updateDesignSystemHint();
    };

    // 搜索
    $('externalSearch').oninput = () => renderExternalProjects();
    $('externalFilter').onchange = () => renderExternalProjects();
    $('externalSearch').onkeydown = (e) => {
        if (e.key === 'Escape' && !e.isComposing) {
            e.preventDefault();
            e.target.value = '';
            renderExternalProjects();
        }
    };
    $('projectSearch').oninput = (e) => {
        searchQuery = e.target.value.trim().toLocaleLowerCase();
        renderProjectList();
    };

    $('projectSearch').onkeydown = e => { if (e.key === 'Escape' && !e.isComposing) { e.target.value = ''; searchQuery = ''; renderProjectList(); } };

    // 记录模态框关闭
    $('closeRecordModal').onclick = closeRecordModal;
    $('recordModalOverlay').onclick = closeRecordModal;

    // 从记录重新生成
    $('regenerateFromRecord').onclick = regenerateFromRecord;

    // 回收站
    $('recycleBinBtn').onclick = openRecycleBin;
    $('closeRecycleBinModal').onclick = closeRecycleBinModal;
    $('recycleBinOverlay').onclick = closeRecycleBinModal;

    // 编辑标题弹窗
    $('editTitleOverlay').onclick = closeEditTitleModal;
    $('editTitleInput').onkeydown = (e) => {
        if (e.key === 'Enter') saveProjectTitle();
        if (e.key === 'Escape') closeEditTitleModal();
    };
}

// ==================== 项目管理 ====================
function createNewProject() {
    // 重置表单
    if ($('projectNameInput')) $('projectNameInput').value = '';
    $('customColorsToggle').checked = false;
    customColorFields.clear();
    $('backgroundMode').value = 'inherit';
    if ($('designSystemSelect')) $('designSystemSelect').value = '';
    if ($('skillSelect')) $('skillSelect').value = 'web-prototype';
    pptInputMode = 'import';
    renderDesignSystemSelect();
    updatePptModeButtons();
    updateInputModeForSkill();

    // 清空页面
    pages = [];
    pageFiles = {};
    pagePptImages = {};
    $('pageCardsContainer').innerHTML = '';
    addPage();

    $('headerTitle').textContent = '新建项目';
    currentRecordProject = null;

    // 清空增量更新状态
    sourceProjectId = null;
    originalFormData = null;
    originalImageHashes = {};
    HomeUI.show('new');
}

async function loadProjects() {
    if (currentUser && currentTab === 'team') return loadTeamProjects();
    const container = $('projectList');
    if (container.getAttribute('aria-busy') === 'true') return;
    HomeUI.loading(container);
    const refresh = document.querySelector('[aria-label="刷新 AI 项目"]'); refresh.classList.add('is-loading');
    container.setAttribute('aria-busy', 'true');
    try {
        const response = await fetch((currentUser ? '/api/projects/my' : '/data/projects.json') + '?t=' + Date.now());
        if (!response.ok) throw new Error('无法读取项目，请稍后重试。');
        const data = await response.json();
        allProjects = Array.isArray(data) ? data : data.projects || [];
        renderProjectList();
    } catch (error) {
        if (!allProjects.length) HomeUI.empty(container, '项目读取失败', error.message, '重试', loadProjects, 'error');
        else showToast(error.message, 'error');
    } finally { container.setAttribute('aria-busy', 'false'); refresh.classList.remove('is-loading'); }
}

function renderProjectList() {
    const container = $('projectList');
    const filtered = allProjects.filter(p => String(p.name || '').toLocaleLowerCase().includes(searchQuery))
        .sort((a, b) => (Date.parse(b.createdAt || b.date) || 0) - (Date.parse(a.createdAt || a.date) || 0));
    HomeUI.updateCounts('ai', allProjects.length, filtered.length);
    HomeUI.clear(container);
    if (!filtered.length) {
        HomeUI.empty(container, searchQuery ? '没有匹配的项目' : '还没有 AI 项目', searchQuery ? '换个关键词试试。' : '从一段设计需求开始，创建你的第一个原型。', searchQuery ? '清除搜索' : '新建项目', () => { if (searchQuery) { $('projectSearch').value = ''; searchQuery = ''; renderProjectList(); } else createNewProject(); }, 'spark');
        return;
    }
    for (const project of filtered) {
        const statuses = { generating: ['生成中', 'info', 'clock'], failed: ['生成失败', 'danger', 'error'], pending_external: ['待外部生成', 'warning', 'clock'] };
        const [badge, tone, badgeIcon] = statuses[project.status] || ['已完成', 'success', 'check'];
        const open = () => window.open(`viewer.html?project=${encodeURIComponent(project.id)}`, '_blank');
        const { article, actions } = HomeUI.card({ id: project.id, name: project.name, kind: 'ai', badge, tone, badgeIcon,
            meta: HomeUI.formatDate(project.createdAt || project.date) || project.date || '',
            detail: [project.model_name, project.ownerName].filter(Boolean).join(' · ') || '原型项目', open,
            preview: ['generating', 'pending_external', 'failed'].includes(project.status) ? null : { source: 'ai', id: project.id } });
        const extraActions = [
            { icon: 'edit', label: '编辑名称', handler: () => editProjectTitle(project.id, project.name) },
            { icon: 'copy', label: '复制项目', handler: () => copyProject(project.id, project.name) },
            { icon: 'history', label: '生成记录', handler: () => viewRecord(project.id) }
        ];
        if (currentUser && currentTab === 'my') extraActions.push({ icon: 'share', label: '分享到团队', handler: () => openShareModal(project.id) });
        extraActions.push({ icon: 'delete', label: '移到回收站', danger: true, handler: () => deleteProject(project.id, project.name) });
        actions.append(
            HomeUI.action('open', `预览 ${project.name}`, open),
            HomeUI.action('publish', `发布 / 导出 ${project.name}`, () => openExportModal(project.id, project.name)),
            HomeUI.more(project.name, extraActions)
        );
        container.append(article);
    }
}

function showGeneratedProjects() {
    currentTab = 'my';
    $('tabMy').className = 'scope-tab is-active'; $('tabTeam').className = 'scope-tab';
    $('teamSelector').classList.add('hidden');
    $('projectSearch').value = ''; searchQuery = '';
    switchProjectSource('ai');
    HomeUI.show('projects');
}

async function deleteProject(id, name) {
    const confirmed = await showAppConfirm({
        title: '移到回收站',
        message: `确定要将「${name}」移到回收站吗？`,
        confirmText: '移到回收站',
        tone: 'danger'
    });
    if (!confirmed) return;

    fetch('/delete-project', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id })
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                showToast('已移到回收站');
                allProjects = allProjects.filter(p => p.id !== id);
                renderProjectList();
            }
        })
        .catch(err => showToast('删除失败', 'error'));
}

async function copyProject(id, name) {
    const newName = await showAppPrompt({
        title: '复制项目',
        message: '请输入新项目名称',
        defaultValue: name + ' - 副本',
        placeholder: '新项目名称',
        confirmText: '复制'
    });
    if (!newName || !newName.trim()) return;

    try {
        showToast('正在复制项目...');
        const response = await fetch('/copy-project', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sourceProjectId: id,
                newProjectName: newName.trim()
            })
        });

        const data = await response.json();
        if (data.success && data.project) {
            showToast('项目复制成功');
            allProjects.unshift(data.project);
            renderProjectList();
        } else {
            showToast('复制失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (err) {
        console.error('复制项目失败:', err);
        showToast('复制失败', 'error');
    }
}

// ==================== 标题编辑功能 ====================
function editProjectTitle(id, currentName) {
    $('editProjectId').value = id;
    $('editTitleInput').value = currentName;
    $('editTitleModal').classList.remove('hidden');
    $('editTitleModal').classList.add('flex');
    setTimeout(() => $('editTitleInput').focus(), 100);
}

function closeEditTitleModal() {
    $('editTitleModal').classList.add('hidden');
    $('editTitleModal').classList.remove('flex');
}

async function saveProjectTitle() {
    const id = $('editProjectId').value;
    const newName = $('editTitleInput').value.trim();

    if (!newName) {
        showToast('标题不能为空', 'error');
        return;
    }

    try {
        const response = await fetch('/rename-project', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id, newName })
        });

        const data = await response.json();
        if (data.success) {
            showToast('标题已更新（文件夹已同步重命名）');
            // 使用后端返回的完整项目对象替换本地项目（包含新的id和url）
            const oldIndex = allProjects.findIndex(p => p.id === id);
            if (oldIndex !== -1 && data.project) {
                allProjects[oldIndex] = data.project;
            }
            renderProjectList();
            closeEditTitleModal();
        } else {
            showToast('更新失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (err) {
        showToast('更新失败', 'error');
    }
}

// ==================== 回收站功能 ====================
async function openRecycleBin() {
    $('recycleBinModal').classList.remove('hidden');
    $('recycleBinModal').classList.add('flex');
    $('recycleBinContent').innerHTML = '<div class="text-center py-8 text-gray-400 text-sm">加载中...</div>';

    try {
        const response = await fetch('/deleted-projects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });

        const data = await response.json();
        if (data.success) {
            renderRecycleBin(data.projects || []);
        } else {
            $('recycleBinContent').innerHTML = '<div class="text-center py-8 text-red-400 text-sm">加载失败</div>';
        }
    } catch (err) {
        $('recycleBinContent').innerHTML = '<div class="text-center py-8 text-red-400 text-sm">加载失败</div>';
    }
}

function renderRecycleBin(projects) {
    if (projects.length === 0) {
        $('recycleBinContent').innerHTML = '<div class="text-center py-8 text-gray-400 text-sm">回收站为空</div>';
        return;
    }

    $('recycleBinContent').innerHTML = projects.map(p => `
        <div class="flex items-start justify-between p-3 rounded-lg hover:bg-gray-50 transition-all border-b border-gray-100 last:border-0">
            <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-gray-900 line-clamp-2" title="${p.name}">${p.name}</p>
                <p class="text-xs text-gray-400 mt-1">删除于: ${p.deletedAt || p.date}</p>
            </div>
            <button onclick="restoreProject('${p.id}')"
                    class="flex-shrink-0 ml-2 px-3 py-1.5 text-sm text-indigo-600 hover:bg-indigo-50 rounded-lg transition flex items-center gap-1">
                <i class="fas fa-undo"></i> 恢复
            </button>
        </div>
    `).join('');
}

function closeRecycleBinModal() {
    $('recycleBinModal').classList.add('hidden');
    $('recycleBinModal').classList.remove('flex');
}

async function restoreProject(id) {
    try {
        const response = await fetch('/restore-project', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id })
        });

        const data = await response.json();
        if (data.success) {
            showToast('项目已恢复');
            // 添加到本地列表
            if (data.project) {
                allProjects.unshift(data.project);
                renderProjectList();
            }
            // 重新加载回收站
            openRecycleBin();
        } else {
            showToast('恢复失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (err) {
        showToast('恢复失败', 'error');
    }
}

// ==================== 记录查看功能 ====================
async function viewRecord(projectId) {
    try {
        // 获取项目记录
        const response = await fetch(`/projects/${projectId}/record.json?t=${Date.now()}`);
        if (!response.ok) {
            showToast('该项目没有保存记录', 'error');
            return;
        }

        const record = await response.json();
        currentRecordProject = { id: projectId, record };

        // 显示模态框
        renderRecordModal(record, projectId);
        $('recordModal').classList.remove('hidden');
        $('recordModal').classList.add('flex');

    } catch (error) {
        showToast('加载记录失败', 'error');
        console.error(error);
    }
}

function renderRecordModal(record, projectId) {
    const container = $('recordContent');
    const recordGlobal = record.global || {};
    const preset = designSystemsList.find(ds => ds.id === (recordGlobal.designSystemId || record.designSystemId || 'default'))?.preset;
    const design = DesignSettings.resolve(recordGlobal, preset);

    // 全局设置
    let html = `
        <div class="mb-6">
            <h4 class="font-bold text-gray-700 mb-3 flex items-center gap-2">
                <i class="fas fa-palette text-indigo-500"></i> 全局设置
            </h4>
            <div class="grid grid-cols-2 gap-3 text-sm">
                <div class="flex items-center gap-2">
                    <span class="text-gray-500">主色调:</span>
                    <span class="w-5 h-5 rounded" style="background:${design.primaryColor}"></span>
                    <span class="font-mono">${design.primaryColor}</span>
                </div>
                <div class="flex items-center gap-2">
                    <span class="text-gray-500">强调色:</span>
                    <span class="w-5 h-5 rounded" style="background:${design.secondaryColor}"></span>
                    <span class="font-mono">${design.secondaryColor}</span>
                </div>
                <div><span class="text-gray-500">主题模式:</span> ${{ inherit: '跟随风格', light: '浅色', dark: '深色' }[design.themeMode]}</div>
                <div><span class="text-gray-500">配色:</span> ${design.colorMode === 'custom' ? '自定义' : '跟随风格'}</div>
            </div>
        </div>
    `;

    // 页面列表
    if (record.pages && record.pages.length > 0) {
        html += `<h4 class="font-bold text-gray-700 mb-3 flex items-center gap-2">
            <i class="fas fa-file-alt text-green-500"></i> 页面信息
        </h4>`;

        record.pages.forEach((page, index) => {
            html += `
                <div class="bg-gray-50 rounded-lg p-4 mb-4">
                    <h5 class="font-bold text-gray-800 mb-2">页面 ${index + 1}: ${page.name || '未命名'}</h5>
                    <div class="space-y-2 text-sm">
                        ${page.layout ? `<div><span class="text-gray-500">布局描述:</span><p class="mt-1 text-gray-700">${page.layout}</p></div>` : ''}
                        ${page.features ? `<div><span class="text-gray-500">核心功能:</span><p class="mt-1 text-gray-700">${page.features}</p></div>` : ''}
                        ${page.interaction ? `<div><span class="text-gray-500">交互说明:</span><p class="mt-1 text-gray-700">${page.interaction}</p></div>` : ''}
                        <div><span class="text-gray-500">参考相似度:</span> ${page.similarity || 'layout'}</div>
                    </div>
            `;

            // 参考图片
            if (page.images && page.images.length > 0) {
                html += `
                    <div class="mt-3">
                        <span class="text-gray-500 text-sm">参考图片:</span>
                        <div class="grid grid-cols-4 gap-2 mt-2">
                            ${page.images.map(img => `
                                <img src="/projects/${projectId}/reference/${img}"
                                     class="w-full aspect-square object-cover rounded border cursor-pointer hover:opacity-80"
                                     onclick="previewImage('/projects/${projectId}/reference/${img}')">
                            `).join('')}
                        </div>
                    </div>
                `;
            }

            html += `</div>`;
        });
    }

    container.innerHTML = html;
}

function closeRecordModal() {
    $('recordModal').classList.add('hidden');
    $('recordModal').classList.remove('flex');
}

async function regenerateFromRecord() {
    if (!currentRecordProject) return;

    const record = currentRecordProject.record;
    closeRecordModal();
    const savedProject = allProjects.find(project => project.id === currentRecordProject.id);
    let savedName = savedProject?.name || record.global?.projectName || '';
    if (savedProject?.status === 'pending_external') savedName = savedName.replace(/ \((待外部生成|AI IDE待生成)\)$/, '');
    if ($('projectNameInput')) $('projectNameInput').value = savedName;

    // 保存来源项目ID（用于增量更新）
    sourceProjectId = currentRecordProject.id;
    console.log('[增量更新] 开始加载历史记录，sourceProjectId:', sourceProjectId);

    // 清空当前表单
    pages = [];
    pageFiles = {};
    pagePptImages = {};
    $('pageCardsContainer').innerHTML = '';

    // 恢复全局设置
    if (record.global) {
        if ($('designSystemSelect')) $('designSystemSelect').value = record.global.designSystemId || record.designSystemId || '';
        const restored = DesignSettings.resolve(record.global, getSelectedDesignPreset());
        customColorFields = new Set(restored.customColorFields);
        $('customColorsToggle').checked = restored.colorMode === 'custom';
        $('primaryColor').value = restored.primaryColor;
        $('secondaryColor').value = restored.secondaryColor;
        $('backgroundMode').value = restored.themeMode;
        if ($('skillSelect')) $('skillSelect').value = record.global.skillId || record.skillId || 'web-prototype';
        renderDesignSystemSelect();
        updateDesignSystemHint();
    }

    // 恢复页面
    if (record.pages && record.pages.length > 0) {
        for (const pageRecord of record.pages) {
            const id = Date.now().toString() + Math.random().toString(36).substr(2, 5);
            pages.push(id);
            pageFiles[id] = [];
            pagePptImages[id] = [];

            const index = pages.length;
            const html = createPageCardHtml(id, index);

            const div = document.createElement('div');
            div.id = `page-${id}`;
            div.className = 'creation-page-card';
            div.innerHTML = html;
            $('pageCardsContainer').appendChild(div);
            setupPageListeners(id);

            // 填入数据
            await new Promise(r => setTimeout(r, 50)); // 等待DOM更新
            if (pageRecord.name) $(`pageName_${id}`).value = pageRecord.name;
            if (pageRecord.layout) $(`layout_${id}`).value = pageRecord.layout;
            if (pageRecord.features) $(`features_${id}`).value = pageRecord.features;
            if (pageRecord.interaction) $(`interaction_${id}`).value = pageRecord.interaction;
            if (pageRecord.similarity) {
                const radio = document.querySelector(`input[name="similarity_${id}"][value="${pageRecord.similarity}"]`);
                if (radio) {
                    radio.checked = true;
                    // 更新 active 样式
                    const group = $(`similarityGroup_${id}`);
                    if (group) {
                        group.querySelectorAll('.similarity-btn').forEach(btn => btn.classList.remove('active'));
                        radio.closest('.similarity-btn').classList.add('active');
                    }
                }
            }

            const pptImageNames = pageRecord.pptImages || [];
            const referenceImageNames = pageRecord.referenceImages || pageRecord.images || [];

            // 加载 PPT 配图（从服务器）- 使用Promise确保等待完成
            if (pptImageNames.length > 0) {
                const pptImageLoadPromises = pptImageNames.map(item => {
                    return new Promise(async (resolve) => {
                        try {
                            const imgName = typeof item === 'string' ? item : item.file;
                            const imgUrl = `/projects/${currentRecordProject.id}/reference/${imgName}`;
                            const response = await fetch(imgUrl);
                            const blob = await response.blob();
                            const reader = new FileReader();
                            reader.onload = (e) => {
                                if (isSupportedRasterDataUrl(e.target.result)) {
                                    pagePptImages[id].push({
                                        name: imgName,
                                        base64: e.target.result,
                                        slideIndex: typeof item === 'object' ? item.slideIndex : index + 1,
                                        slideTitle: typeof item === 'object' ? item.slideTitle : ''
                                    });
                                    renderPptImagePreviews(id);
                                } else {
                                    console.warn('跳过不支持的历史 PPT 配图:', imgName);
                                }
                                resolve();
                            };
                            reader.onerror = () => resolve(); // 失败也继续
                            reader.readAsDataURL(blob);
                        } catch (e) {
                            console.error('加载参考图失败:', e);
                            resolve(); // 失败也继续
                        }
                    });
                });
                await Promise.all(pptImageLoadPromises);
            }

            // 加载参考图片（从服务器）- 使用Promise确保等待完成
            if (referenceImageNames.length > 0) {
                const imageLoadPromises = referenceImageNames.map(imgName => {
                    return new Promise(async (resolve) => {
                        try {
                            const imgUrl = `/projects/${currentRecordProject.id}/reference/${imgName}`;
                            const response = await fetch(imgUrl);
                            const blob = await response.blob();
                            const reader = new FileReader();
                            reader.onload = (e) => {
                                if (isSupportedRasterDataUrl(e.target.result)) {
                                    pageFiles[id].push({
                                        name: imgName,
                                        base64: e.target.result
                                    });
                                    renderPreviews(id);
                                } else {
                                    console.warn('跳过不支持的历史参考图:', imgName);
                                }
                                resolve();
                            };
                            reader.onerror = () => resolve();
                            reader.readAsDataURL(blob);
                        } catch (e) {
                            console.error('加载参考图失败:', e);
                            resolve();
                        }
                    });
                });
                await Promise.all(imageLoadPromises);
            }
        }
    } else {
        addPage();
    }

    updateInputModeForSkill();

    // 图片已全部加载完成，保存原始快照
    originalFormData = collectFormData();
    originalImageHashes = computeAllImageHashes();

    console.log('[增量更新] 已保存原始快照:', {
        sourceProjectId,
        originalFormData,
        originalImageHashes,
        pagesCount: pages.length,
        imagesCounts: pages.map(id => pageFiles[id]?.length || 0)
    });

    $('headerTitle').textContent = '继续编辑项目';
    HomeUI.show('new');
    HomeUI.summary();
    showToast('已加载历史记录，修改后将智能增量生成');
}

// ==================== 页面卡片管理 ====================
function addPage() {
    const id = Date.now().toString();
    pages.push(id);
    pageFiles[id] = [];
    pagePptImages[id] = [];

    const index = pages.length;
    const html = createPageCardHtml(id, index);

    const div = document.createElement('div');
    div.id = `page-${id}`;
    div.className = 'creation-page-card';
    div.innerHTML = html;

    $('pageCardsContainer').appendChild(div);
    setupPageListeners(id);
    updateInputModeForSkill();
}

function createPageCardHtml(id, index) {
    return `
        <div class="border-b border-gray-200 px-6 py-4 bg-gray-50 flex justify-between items-center">
            <div id="pageTitleWrap_${id}" class="flex items-center gap-3 flex-1">
                <span class="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center text-sm font-bold">${index}</span>
                <input type="text" id="pageName_${id}" class="flex-1 bg-transparent border-none focus:ring-0 font-bold text-lg placeholder-gray-400" placeholder="页面名称（如：首页、用户列表）">
            </div>
            <div id="pptCardTitle_${id}" class="hidden flex items-center gap-3 flex-1">
                <span class="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center text-sm font-bold">${index}</span>
                <div>
                    <div class="font-bold text-lg text-gray-900">HTML PPT 输入</div>
                    <div class="text-xs text-gray-400">导入 PPT 配图，填写布局/内容和动画要求</div>
                </div>
            </div>
            <button onclick="removePage('${id}')" class="text-gray-400 hover:text-red-500 p-2" title="删除页面">
                <i class="fas fa-trash-alt"></i>
            </button>
        </div>

        <div class="p-6 space-y-4">
            <div id="pptImportField_${id}" class="hidden rounded-lg border border-indigo-100 bg-indigo-50/60 p-4">
                <div class="flex flex-col md:flex-row md:items-center gap-3">
                    <div class="flex-1">
                        <div class="text-sm font-medium text-indigo-900">上传 PPTX 解析</div>
                        <div class="text-xs text-indigo-600 mt-1">提取文字、页面顺序和原始配图；配图会按原始页参与生成，不作为参考图。</div>
                    </div>
                    <label class="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-white border border-indigo-200 text-indigo-700 text-sm font-medium cursor-pointer hover:border-indigo-400">
                        <i class="fas fa-file-powerpoint"></i>
                        选择 PPTX
                        <input type="file" id="pptFileInput_${id}" class="hidden" accept=".pptx,.ppt">
                    </label>
                </div>
                <div id="pptParseStatus_${id}" class="mt-3 text-xs text-indigo-700"></div>
                <div id="pptAssetPanel_${id}" class="hidden mt-3 rounded-xl bg-blue-50 border-2 border-blue-200 p-4">
                    <div class="flex items-center justify-between gap-2 mb-2">
                        <div>
                            <div class="text-sm font-semibold text-blue-900 flex items-center gap-2">
                                <i class="fas fa-layer-group"></i>
                                PPT 原始配图
                            </div>
                            <div class="text-xs text-blue-600 mt-0.5">来自 PPTX，生成时会按原始页放回对应 slide</div>
                        </div>
                        <div id="pptAssetCount_${id}" class="text-xs font-medium text-blue-700"></div>
                    </div>
                    <div id="pptAssetPreview_${id}" class="grid grid-cols-6 gap-2"></div>
                </div>
            </div>
            <div id="primaryFields_${id}" class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <!-- 布局描述 -->
                <div>
                    <label for="layout_${id}" class="block text-sm font-medium text-gray-700 mb-1">布局描述</label>
                    <textarea id="layout_${id}" rows="6" class="w-full rounded-lg border-gray-200 border p-3 text-sm resize-y min-h-[160px]" placeholder="描述页面的布局结构...&#10;如：顶部导航、左侧菜单、右侧内容区"></textarea>
                </div>

                <!-- 参考图上传 -->
                <div id="referenceBox_${id}">
                    <div class="flex justify-between items-start gap-3 mb-3">
                        <div>
                            <label id="referenceLabel_${id}" class="text-sm font-medium text-gray-700">
                                <i id="referenceIcon_${id}" class="fas fa-images hidden"></i>
                                参考图
                            </label>
                            <div id="referenceHint_${id}" class="text-xs text-emerald-700 mt-0.5 hidden">可选：只用于补充视觉风格参考，不替代 PPT 原始配图</div>
                        </div>
                        <div class="flex gap-1" id="similarityGroup_${id}">
                            <label class="similarity-btn active" data-value="layout">
                                <input type="radio" name="similarity_${id}" value="layout" checked class="hidden">
                                仅参考布局
                            </label>
                            <label class="similarity-btn" data-value="style">
                                <input type="radio" name="similarity_${id}" value="style" class="hidden">
                                仅参考风格
                            </label>
                            <label class="similarity-btn" data-value="pixel">
                                <input type="radio" name="similarity_${id}" value="pixel" class="hidden">
                                像素级还原
                            </label>
                        </div>
                    </div>
                    <div id="dropZone_${id}" tabindex="0" class="border-2 border-dashed border-gray-200 rounded-lg h-32 flex items-center justify-center text-center hover:border-indigo-500 hover:bg-indigo-50/50 transition-all cursor-pointer focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200">
                        <div id="dropZoneText_${id}" class="text-gray-400 text-sm">
                            <i class="fas fa-image mr-2"></i>点击、拖拽或 Ctrl+V 粘贴参考图
                        </div>
                        <input type="file" id="fileInput_${id}" class="hidden" accept="image/*" multiple>
                    </div>
                    <div id="referencePreviewWrap_${id}" class="hidden mt-2">
                        <div id="referencePreviewHeader_${id}" class="hidden items-center justify-between mb-2">
                            <div class="text-xs font-medium text-emerald-900">已添加参考图</div>
                            <div id="referenceCount_${id}" class="text-xs text-emerald-600"></div>
                        </div>
                        <div id="preview_${id}" class="grid grid-cols-5 gap-2"></div>
                    </div>
                </div>
            </div>

            <div id="standardFields_${id}" class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <!-- 核心功能 -->
                <div id="featuresField_${id}">
                    <label for="features_${id}" class="block text-sm font-medium text-gray-700 mb-1">核心功能</label>
                    <textarea id="features_${id}" rows="4" class="w-full rounded-lg border-gray-200 border p-3 text-sm resize-y min-h-[120px]" placeholder="- 表格排序筛选&#10;- 数据导出"></textarea>
                </div>

                <!-- 交互说明 -->
                <div id="interactionField_${id}">
                    <label for="interaction_${id}" class="block text-sm font-medium text-gray-700 mb-1">交互说明</label>
                    <textarea id="interaction_${id}" rows="4" class="w-full rounded-lg border-gray-200 border p-3 text-sm resize-y min-h-[120px]" placeholder="点击按钮 → 弹出模态框"></textarea>
                </div>
            </div>
        </div>
    `;
}

function removePage(id) {
    if (pages.length <= 1) {
        showToast('至少需要一个页面', 'error');
        return;
    }

    const el = $(`page-${id}`);
    el.remove();
    pages = pages.filter(p => p !== id);
    delete pageFiles[id];
    delete pagePptImages[id];

    // 更新序号
    pages.forEach((pid, i) => {
        const badge = document.querySelector(`#page-${pid} .bg-indigo-600`);
        if (badge) badge.textContent = i + 1;
    });
}

function setupPageListeners(id) {
    const dropZone = $(`dropZone_${id}`);
    const fileInput = $(`fileInput_${id}`);
    const pptFileInput = $(`pptFileInput_${id}`);

    const activateReferenceDropZone = () => {
        activeReferenceDropZoneId = id;
        dropZone.focus();
    };

    dropZone.onmouseenter = activateReferenceDropZone;
    dropZone.onfocus = () => {
        activeReferenceDropZoneId = id;
    };

    dropZone.onclick = () => {
        activateReferenceDropZone();
        fileInput.click();
    };

    dropZone.ondragover = (e) => {
        e.preventDefault();
        const isPpt = isHtmlPptMode();
        dropZone.classList.add(isPpt ? 'border-emerald-500' : 'border-indigo-500', isPpt ? 'bg-emerald-50' : 'bg-indigo-50');
    };

    dropZone.ondragleave = () => {
        dropZone.classList.remove('border-emerald-500', 'bg-emerald-50', 'border-indigo-500', 'bg-indigo-50');
    };

    dropZone.ondrop = (e) => {
        e.preventDefault();
        dropZone.classList.remove('border-emerald-500', 'bg-emerald-50', 'border-indigo-500', 'bg-indigo-50');
        activeReferenceDropZoneId = id;
        handleFiles(id, e.dataTransfer.files);
    };

    fileInput.onchange = (e) => {
        handleFiles(id, e.target.files);
        fileInput.value = '';
    };

    if (pptFileInput) {
        pptFileInput.onchange = (e) => {
            const file = e.target.files && e.target.files[0];
            if (file) parsePptxForPage(id, file);
            pptFileInput.value = '';
        };
    }

    // 支持参考图框获得焦点时粘贴剪切板图片
    dropZone.addEventListener('paste', (e) => {
        handleReferencePasteEvent(e, id);
    });

    // 参考图相似度选项切换
    const similarityGroup = $(`similarityGroup_${id}`);
    if (similarityGroup) {
        similarityGroup.querySelectorAll('.similarity-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                similarityGroup.querySelectorAll('.similarity-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });
    }
}

function isHtmlPptMode() {
    return ($('skillSelect') ? $('skillSelect').value : 'web-prototype') === 'html-ppt';
}

function handleFiles(id, files) {
    const imageFiles = Array.from(files).filter(f => f.type.startsWith('image/'));
    const currentCount = pageFiles[id]?.length || 0;
    const remaining = MAX_REFERENCE_IMAGES_PER_PAGE - currentCount;

    if (remaining <= 0) {
        showToast(`每页最多添加 ${MAX_REFERENCE_IMAGES_PER_PAGE} 张参考图`, 'warning');
        return;
    }

    const acceptedFiles = imageFiles.slice(0, remaining);
    if (acceptedFiles.length < imageFiles.length) {
        showToast(`已限制为每页最多 ${MAX_REFERENCE_IMAGES_PER_PAGE} 张参考图`, 'warning');
    }

    acceptedFiles.forEach(file => {
        const reader = new FileReader();
        reader.onload = (e) => {
            if (!isSupportedRasterDataUrl(e.target.result)) {
                showToast('已跳过不支持的图片格式，请使用 PNG/JPG/GIF/WebP', 'warning');
                return;
            }
            pageFiles[id].push({
                name: file.name,
                base64: e.target.result
            });
            renderPreviews(id);
        };
        reader.readAsDataURL(file);
    });
}

function getImageFilesFromClipboard(event) {
    const items = event.clipboardData?.items;
    if (!items) return [];

    const imageFiles = [];
    for (const item of items) {
        if (item.type && item.type.startsWith('image/')) {
            const file = item.getAsFile();
            if (file) imageFiles.push(file);
        }
    }
    return imageFiles;
}

function handleReferencePasteEvent(event, id) {
    const imageFiles = getImageFilesFromClipboard(event);
    if (imageFiles.length === 0) return false;

    event.preventDefault();
    event.stopPropagation();
    handleFiles(id, imageFiles);
    showToast(`已粘贴 ${imageFiles.length} 张参考图`);
    return true;
}

function handleGlobalReferencePaste(event) {
    if (event.defaultPrevented) return;

    const target = event.target;
    const isTypingField = target && ['TEXTAREA', 'INPUT'].includes(target.tagName);
    if (isTypingField) return;

    const id = activeReferenceDropZoneId;
    if (!id || !pages.includes(id)) return;
    handleReferencePasteEvent(event, id);
}

function renderPreviews(id) {
    const wrap = $(`referencePreviewWrap_${id}`);
    const container = $(`preview_${id}`);
    const count = $(`referenceCount_${id}`);
    const header = $(`referencePreviewHeader_${id}`);
    const files = pageFiles[id];
    const isPpt = isHtmlPptMode();

    if (!container || !wrap) return;
    if (files.length === 0) {
        wrap.classList.add('hidden');
        container.innerHTML = '';
        if (count) count.textContent = '';
        return;
    }

    wrap.classList.remove('hidden');
    wrap.className = isPpt
        ? 'mt-3 rounded-lg bg-white border border-emerald-100 p-3'
        : 'mt-2';
    if (header) {
        header.className = isPpt
            ? 'flex items-center justify-between mb-2'
            : 'hidden';
    }
    if (count) count.textContent = `${files.length} 张`;
    container.innerHTML = files.map((f, i) => `
        <div class="relative aspect-square ${isPpt ? 'bg-emerald-50 border border-emerald-100' : 'bg-gray-100'} rounded overflow-hidden group">
            <img src="${f.base64}" class="w-full h-full object-cover cursor-zoom-in" onclick="previewImage('${f.base64}')">
            <button onclick="removeFile('${id}', ${i})" class="absolute top-1 right-1 w-5 h-5 bg-black/60 text-white rounded-full text-xs opacity-0 group-hover:opacity-100 transition-opacity">×</button>
        </div>
    `).join('');
}

function renderPptImagePreviews(id) {
    const panel = $(`pptAssetPanel_${id}`);
    const container = $(`pptAssetPreview_${id}`);
    const count = $(`pptAssetCount_${id}`);
    const files = pagePptImages[id] || [];

    if (!panel || !container) return;
    if (files.length === 0) {
        panel.classList.add('hidden');
        container.innerHTML = '';
        if (count) count.textContent = '';
        return;
    }

    panel.classList.remove('hidden');
    if (count) count.textContent = `${files.length} 张`;
    container.innerHTML = files.map((f, i) => `
        <div class="relative aspect-video bg-indigo-50 rounded overflow-hidden border border-indigo-100 group" title="第 ${escapeHtml(f.slideIndex || '-')} 页配图">
            <img src="${f.base64}" class="w-full h-full object-cover cursor-zoom-in" onclick="previewImage('${f.base64}')">
            <span class="absolute left-1 top-1 px-1.5 py-0.5 rounded bg-black/60 text-white text-[10px]">P${escapeHtml(f.slideIndex || '')}</span>
            <button onclick="removePptImage('${id}', ${i})" class="absolute top-1 right-1 w-5 h-5 bg-black/60 text-white rounded-full text-xs opacity-0 group-hover:opacity-100 transition-opacity">×</button>
        </div>
    `).join('');
}

function removeFile(id, index) {
    pageFiles[id].splice(index, 1);
    renderPreviews(id);
}

function removePptImage(id, index) {
    if (!pagePptImages[id]) return;
    pagePptImages[id].splice(index, 1);
    renderPptImagePreviews(id);
}

function sanitizePageImages(id) {
    const validPptImages = [];
    (pagePptImages[id] || []).forEach(f => {
        if (isSupportedRasterDataUrl(f.base64)) {
            validPptImages.push(f);
        } else {
            console.warn('生成前跳过不支持的 PPT 配图:', f.name);
        }
    });
    pagePptImages[id] = validPptImages;
    renderPptImagePreviews(id);

    const validReferenceImages = [];
    (pageFiles[id] || []).forEach(f => {
        if (isSupportedRasterDataUrl(f.base64)) {
            validReferenceImages.push(f);
        } else {
            console.warn('生成前跳过不支持的参考图:', f.name);
        }
    });
    pageFiles[id] = validReferenceImages;
    renderPreviews(id);
}

function enforceRequestImageLimit() {
    let remaining = MAX_AI_IMAGES_PER_REQUEST;
    let dropped = 0;

    pages.forEach(id => {
        const pptImages = pagePptImages[id] || [];
        if (pptImages.length > remaining) {
            dropped += pptImages.length - remaining;
            pagePptImages[id] = pptImages.slice(0, Math.max(remaining, 0));
        }
        remaining -= pagePptImages[id].length;
        renderPptImagePreviews(id);
    });

    pages.forEach(id => {
        const referenceImages = pageFiles[id] || [];
        if (remaining <= 0) {
            dropped += referenceImages.length;
            pageFiles[id] = [];
        } else if (referenceImages.length > remaining) {
            dropped += referenceImages.length - remaining;
            pageFiles[id] = referenceImages.slice(0, remaining);
        }
        remaining -= pageFiles[id].length;
        renderPreviews(id);
    });

    if (dropped > 0) {
        showToast(`图片超过模型网关上限，已优先保留前 ${MAX_AI_IMAGES_PER_REQUEST} 张 PPT 配图/参考图`, 'warning');
    }
}

function previewImage(src) {
    $('fullSizeImage').src = src;
    $('imagePreviewModal').classList.remove('hidden');
    $('imagePreviewModal').classList.add('flex');
}

async function parsePptxForPage(id, file) {
    const status = $(`pptParseStatus_${id}`);
    if (status) status.textContent = '正在解析 PPTX...';

    try {
        const form = new FormData();
        form.append('file', file);
        const res = await fetch('/api/pptx/parse', {
            method: 'POST',
            body: form
        });
        const data = await res.json();
        if (!res.ok || data.error) {
            throw new Error(data.error || 'PPTX 解析失败');
        }

        const sourceImageCount = data.sourceImageCount ?? data.imageCount;
        const attachedImageCount = data.imageCount || 0;
        const maxImagesPerSlide = data.maxImagesPerSlide || MAX_PPT_IMAGES_PER_SLIDE;
        const summaryLines = [
            `来源文件：${data.filename}`,
            `共 ${data.slideCount} 页，PPT 中图片 ${sourceImageCount} 张，已按每页最多 ${maxImagesPerSlide} 张选取 ${attachedImageCount} 张原始配图。`,
            '',
            ...data.slides.map(slide => {
                const text = (slide.texts || []).join('\n');
                return `第 ${slide.index} 页：${slide.title}\n${text}`;
            })
        ];

        const layout = $(`layout_${id}`);
        if (layout) {
            layout.value = `请将以下 PPT 内容重构为更精致的 HTML 演示文稿，保留原始信息层级、页序和关键图片，并整体美化视觉设计。\n\n${summaryLines.join('\n\n')}`;
        }

        pagePptImages[id] = [];
        (data.slides || []).forEach(slide => {
            (slide.images || []).slice(0, maxImagesPerSlide).forEach((img, imgIndex) => {
                pagePptImages[id].push({
                    name: `slide${slide.index}_${img.name || imgIndex + 1}`,
                    base64: img.base64,
                    slideIndex: slide.index,
                    slideTitle: slide.title || ''
                });
            });
        });
        renderPptImagePreviews(id);

        if (status) status.textContent = `解析完成：${data.slideCount} 页，已选取 ${pagePptImages[id].length} 张 PPT 原始配图（每页最多 ${maxImagesPerSlide} 张）。`;
        showToast('PPTX 已解析并填入内容');
    } catch (e) {
        if (status) status.textContent = e.message;
        showToast('PPTX 解析失败: ' + e.message, 'error');
    }
}

// ==================== Open Design 资产 ====================
async function loadDesignSystems() {
    try {
        const res = await fetch('/api/design-systems?t=' + Date.now());
        const data = await res.json();
        designSystemsList = data.designSystems || [];
        renderDesignSystemSelect();
    } catch (e) {
        console.error('加载设计系统失败:', e);
    }
}

async function loadSkills() {
    try {
        const res = await fetch('/api/skills?t=' + Date.now());
        const data = await res.json();
        skillsList = data.skills || [];
        renderSkillSelect();
    } catch (e) {
        console.error('加载Skills失败:', e);
    }
}

function renderDesignSystemSelect() {
    const select = $('designSystemSelect');
    if (!select) return;
    const current = select.value;

    const ordered = getOrderedDesignSystems();
    const byId = new Map(designSystemsList.map(ds => [ds.id, ds]));
    select.innerHTML = '<option value="">默认风格</option>' + ordered.map(ds => {
        const label = getDesignSystemLabel(ds);
        return `<option value="${ds.id}">${escapeHtml(label)}</option>`;
    }).join('');
    if (current && byId.has(current)) select.value = current;
    renderDesignSystemMenu(ordered);
    updateDesignSystemHint();
}

function getOrderedDesignSystems() {
    const skillId = $('skillSelect') ? $('skillSelect').value : 'web-prototype';
    const mode = SKILL_INPUT_MODES[skillId] || SKILL_INPUT_MODES['web-prototype'];
    const preferred = [...(mode.recommendedDesignSystems || []), ...DESIGN_SYSTEM_RECOMMENDED_FALLBACK];
    const uniquePreferred = [...new Set(preferred)];
    const byId = new Map(designSystemsList.map(ds => [ds.id, ds]));
    return [
        ...uniquePreferred.map(id => byId.get(id)).filter(Boolean),
        ...designSystemsList.filter(ds => !uniquePreferred.includes(ds.id))
    ];
}

function getDesignSystemLabel(ds) {
    if (!ds) return '默认风格';
    if (ds.label) return ds.label;
    return `${ds.displayName || ds.name || ds.id}${ds.categoryLabel ? ` · ${ds.categoryLabel}` : ''}`;
}

function getDesignSystemUiLabel(ds) {
    return getDesignSystemLabel(ds)
        .replace(/\s*设计系统/g, '')
        .replace(/\s*Design System\s*/gi, '')
        .trim() || '默认风格';
}

function renderMiniSwatches(colors, sizeClass = 'h-4 w-4') {
    return (colors || []).slice(0, 6).map(color => `
        <span class="inline-block ${sizeClass} rounded border border-black/10" title="${escapeHtml(color)}" style="background:${escapeHtml(color)}"></span>
    `).join('');
}

function renderDesignSystemMenu(ordered) {
    const menu = $('designSystemMenu');
    if (!menu) return;
    const selectedId = $('designSystemSelect') ? $('designSystemSelect').value : '';
    const defaultColors = getDefaultSwatchColors();
    const rows = [
        {
            id: '',
            label: '默认风格',
            categoryLabel: '中性现代',
            colors: defaultColors
        },
        ...ordered
    ];
    menu.innerHTML = rows.map(ds => {
        const isActive = (ds.id || '') === selectedId;
        const colors = Array.isArray(ds.colors) && ds.colors.length ? ds.colors : defaultColors;
        return `
            <button type="button" class="design-system-option w-full rounded-lg px-3 py-2 text-left flex items-center justify-between gap-3 ${isActive ? 'bg-indigo-50 text-indigo-700' : 'text-gray-700 hover:bg-gray-50'}" data-id="${escapeHtml(ds.id || '')}">
                <span class="min-w-0">
                    <span class="block text-sm font-medium truncate">${escapeHtml(getDesignSystemUiLabel(ds))}</span>
                    ${ds.categoryLabel ? `<span class="block text-xs text-gray-400 truncate">${escapeHtml(ds.categoryLabel)}</span>` : ''}
                </span>
                <span class="flex flex-shrink-0 items-center gap-1">${renderMiniSwatches(colors, 'h-4 w-4')}</span>
            </button>
        `;
    }).join('');
    menu.querySelectorAll('.design-system-option').forEach(btn => {
        btn.addEventListener('click', () => selectDesignSystem(btn.dataset.id || ''));
    });
}

function toggleDesignSystemMenu() {
    const menu = $('designSystemMenu');
    if (!menu) return;
    menu.classList.toggle('hidden');
}

function closeDesignSystemMenu() {
    const menu = $('designSystemMenu');
    if (menu) menu.classList.add('hidden');
}

function selectDesignSystem(id) {
    const select = $('designSystemSelect');
    if (!select) return;
    select.value = id;
    updateDesignSystemHint();
    renderDesignSystemMenu(getOrderedDesignSystems());
    closeDesignSystemMenu();
}

function getDefaultSwatchColors() {
    return DesignSettings.resolve({}, designSystemsList.find(ds => ds.id === 'default')?.preset).effectivePalette;
}

function getSelectedDesignPreset() {
    const id = $('designSystemSelect')?.value || 'default';
    return designSystemsList.find(ds => ds.id === id)?.preset || DesignSettings.fallback;
}

function getEffectiveDesignSettings() {
    return DesignSettings.resolve({
        designSettingsVersion: 2,
        colorMode: $('customColorsToggle').checked ? 'custom' : 'preset',
        customColorFields: [...customColorFields],
        themeMode: $('backgroundMode').value,
        primaryColor: $('primaryColor').value,
        secondaryColor: $('secondaryColor').value,
        designSystemId: $('designSystemSelect')?.value || '',
        designSystemName: getSelectedDesignSystemName(),
        skillId: $('skillSelect')?.value || 'web-prototype',
        skillName: getSelectedSkillName()
    }, getSelectedDesignPreset());
}

function renderSkillSelect() {
    const select = $('skillSelect');
    if (!select) return;

    const labels = {
        'web-prototype': 'Web 原型',
        'dashboard': '后台 Dashboard',
        'mobile-app': '移动 App',
        'saas-landing': 'SaaS Landing',
        'html-ppt': 'HTML PPT'
    };
    const preferred = ['web-prototype', 'dashboard', 'mobile-app', 'saas-landing', 'html-ppt'];
    const byId = new Map(skillsList.map(skill => [skill.id, skill]));
    const ordered = [
        ...preferred.map(id => byId.get(id)).filter(Boolean),
        ...skillsList.filter(skill => !preferred.includes(skill.id) && skill.id !== 'pptx-html-fidelity-audit')
    ];

    select.innerHTML = ordered.map(skill => {
        const label = labels[skill.id] || skill.name || skill.id;
        return `<option value="${skill.id}">${escapeHtml(label)}</option>`;
    }).join('');
    if (!select.value) select.value = 'web-prototype';
    updateInputModeForSkill();
}

function getSelectedDesignSystemName() {
    const id = $('designSystemSelect') ? $('designSystemSelect').value : '';
    if (!id) return '默认风格';
    const ds = designSystemsList.find(item => item.id === id);
    return ds ? (ds.displayName || ds.name || ds.id) : id;
}

function getSelectedSkillName() {
    const id = $('skillSelect') ? $('skillSelect').value : 'web-prototype';
    const skill = skillsList.find(item => item.id === id);
    return skill ? (skill.name || skill.id) : id;
}

function escapeHtml(str) {
    return String(str || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function updateDesignSystemHint() {
    const hint = $('designSystemHelp');
    const id = $('designSystemSelect') ? $('designSystemSelect').value : '';
    if (hint) hint.dataset.help = '配色、字体和组件语言跟随视觉风格；自定义配色和主题模式优先于预设。';
    const effective = getEffectiveDesignSettings();
    $('primaryColor').value = effective.primaryColor;
    $('secondaryColor').value = effective.secondaryColor;
    $('primaryColorValue').textContent = effective.primaryColor;
    $('secondaryColorValue').textContent = effective.secondaryColor;
    const custom = effective.colorMode === 'custom';
    $('customColorsPanel').hidden = !custom;
    $('customColorsToggle').setAttribute('aria-expanded', String(custom));
    $('primaryColor').disabled = !custom;
    $('secondaryColor').disabled = !custom;
    const ds = designSystemsList.find(item => item.id === id) || null;
    renderDesignSystemSwatches({ colors: effective.effectivePalette });
    updateDesignSystemPickerButton(ds);
    if (window.HomeUI) HomeUI.summary();
}

function renderDesignSystemSwatches(ds) {
    const container = $('designSystemSwatches');
    if (!container) return;
    const colors = (ds && Array.isArray(ds.colors)) ? ds.colors.slice(0, 6) : [];
    if (!colors.length) {
        container.innerHTML = '';
        container.classList.add('hidden');
        return;
    }
    container.classList.remove('hidden');
    container.innerHTML = renderMiniSwatches(colors, 'h-5 w-5');
}

function updateDesignSystemPickerButton(ds) {
    const label = $('designSystemPickerLabel');
    if (label) { label.textContent = getDesignSystemUiLabel(ds); label.title = label.textContent; }
}

function updateInputModeForSkill() {
    const skillId = $('skillSelect') ? $('skillSelect').value : 'web-prototype';
    const mode = SKILL_INPUT_MODES[skillId] || SKILL_INPUT_MODES['web-prototype'];
    const isPpt = skillId === 'html-ppt';
    const useCompactPpt = isPpt && pptInputMode === 'import';

    if ($('pptModeControls')) $('pptModeControls').classList.toggle('hidden', !isPpt);
    updatePptModeButtons();
    if ($('skillModeHelp')) {
        $('skillModeHelp').dataset.help = isPpt
            ? 'HTML PPT 支持两种输入：导入 PPTX 美化，或逐页描述生成。'
            : '当前产物类型使用统一的 Web 原型式输入：页面、布局、功能、交互和参考图。';
    }
    if ($('addPageBtn')) {
        $('addPageBtn').innerHTML = `<i class="fas fa-plus"></i> ${mode.addLabel}`;
        $('addPageBtn').classList.toggle('hidden', !!useCompactPpt);
    }

    if (useCompactPpt && pages.length > 1) {
        pages.slice(1).forEach((id) => {
            const el = $(`page-${id}`);
            if (el) el.remove();
            delete pageFiles[id];
            delete pagePptImages[id];
        });
        pages = pages.slice(0, 1);
    }
    pages.forEach((id) => applyInputModeToPage(id, mode, { compactPpt: useCompactPpt, isPpt }));
}

function updatePptModeButtons() {
    const importBtn = $('pptImportModeBtn');
    const pagesBtn = $('pptPagesModeBtn');
    if (!importBtn || !pagesBtn) return;
    const importActive = pptInputMode === 'import';
    importBtn.className = importActive
        ? 'px-3 py-2 rounded-lg text-sm font-medium bg-indigo-600 text-white border border-indigo-600'
        : 'px-3 py-2 rounded-lg text-sm font-medium bg-white text-gray-600 border border-gray-200 hover:border-indigo-300';
    pagesBtn.className = !importActive
        ? 'px-3 py-2 rounded-lg text-sm font-medium bg-indigo-600 text-white border border-indigo-600'
        : 'px-3 py-2 rounded-lg text-sm font-medium bg-white text-gray-600 border border-gray-200 hover:border-indigo-300';
}

function setPptInputMode(mode) {
    pptInputMode = mode === 'pages' ? 'pages' : 'import';
    updateInputModeForSkill();
}

function applyInputModeToPage(id, mode, options = {}) {
    const compactPpt = !!options.compactPpt;
    const isPpt = !!options.isPpt;
    const titleInput = $(`pageName_${id}`);
    const layout = $(`layout_${id}`);
    const features = $(`features_${id}`);
    const interaction = $(`interaction_${id}`);
    const titleWrap = $(`pageTitleWrap_${id}`);
    const pptTitle = $(`pptCardTitle_${id}`);
    const pptImportField = $(`pptImportField_${id}`);
    const primaryFields = $(`primaryFields_${id}`);
    const standardFields = $(`standardFields_${id}`);
    const featuresField = $(`featuresField_${id}`);
    const interactionField = $(`interactionField_${id}`);
    const similarityGroup = $(`similarityGroup_${id}`);
    const referenceBox = $(`referenceBox_${id}`);
    const referenceLabel = $(`referenceLabel_${id}`);
    const referenceIcon = $(`referenceIcon_${id}`);
    const referenceHint = $(`referenceHint_${id}`);
    const dropZone = $(`dropZone_${id}`);
    const dropZoneText = $(`dropZoneText_${id}`);
    if (titleInput) titleInput.placeholder = mode.pagePlaceholder;
    if (titleWrap) titleWrap.classList.toggle('hidden', compactPpt);
    if (pptTitle) pptTitle.classList.toggle('hidden', !compactPpt);
    if (pptImportField) pptImportField.classList.toggle('hidden', !(isPpt && pptInputMode === 'import'));
    if (similarityGroup) similarityGroup.classList.toggle('hidden', isPpt);
    if (referenceHint) referenceHint.classList.toggle('hidden', !isPpt);
    if (referenceBox) {
        referenceBox.className = isPpt
            ? 'rounded-xl border-2 border-emerald-200 bg-emerald-50 p-4'
            : '';
    }
    if (referenceLabel) {
        referenceLabel.className = isPpt
            ? 'text-sm font-semibold text-emerald-900 flex items-center gap-2'
            : 'text-sm font-medium text-gray-700';
    }
    if (referenceIcon) referenceIcon.classList.toggle('hidden', !isPpt);
    if (dropZone) {
        dropZone.className = isPpt
            ? 'border-2 border-dashed border-emerald-300 bg-white rounded-lg h-32 flex items-center justify-center text-center hover:border-emerald-500 hover:bg-emerald-50 transition-all cursor-pointer focus:outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200'
            : 'border-2 border-dashed border-gray-200 rounded-lg h-32 flex items-center justify-center text-center hover:border-indigo-500 hover:bg-indigo-50/50 transition-all cursor-pointer focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200';
    }
    if (dropZoneText) {
        dropZoneText.className = isPpt ? 'text-emerald-700 text-sm' : 'text-gray-400 text-sm';
        dropZoneText.innerHTML = isPpt
            ? '<i class="fas fa-plus-circle mr-2"></i>点击、拖拽或 Ctrl+V 粘贴参考图<div class="text-xs text-emerald-500 mt-1">上传后会显示在下方绿色预览区</div>'
            : '<i class="fas fa-image mr-2"></i>点击、拖拽或粘贴上传';
    }
    if (primaryFields) {
        primaryFields.className = compactPpt
            ? 'grid grid-cols-1 gap-4'
            : 'grid grid-cols-1 md:grid-cols-2 gap-4';
    }
    if (standardFields) standardFields.classList.toggle('hidden', compactPpt);
    if (featuresField) featuresField.classList.toggle('hidden', isPpt);
    if (compactPpt && primaryFields && interactionField && !primaryFields.contains(interactionField)) {
        primaryFields.appendChild(interactionField);
    }
    if (!compactPpt && standardFields && interactionField && !standardFields.contains(interactionField)) {
        standardFields.appendChild(interactionField);
    }
    if (layout) {
        layout.placeholder = mode.layoutPlaceholder;
        const label = document.querySelector(`label[for="layout_${id}"]`);
        if (label) label.textContent = mode.layoutLabel;
        layout.rows = compactPpt ? 12 : (isPpt ? 8 : 6);
    }
    if (features) {
        features.placeholder = mode.featuresPlaceholder;
        const label = document.querySelector(`label[for="features_${id}"]`);
        if (label) label.textContent = mode.featuresLabel;
    }
    if (interaction) {
        interaction.placeholder = mode.interactionPlaceholder;
        const label = document.querySelector(`label[for="interaction_${id}"]`);
        if (label) label.textContent = mode.interactionLabel;
        interaction.rows = compactPpt ? 8 : 4;
    }
    renderPreviews(id);
}

// ==================== AI 生成 ====================
function generatePrompt(options = {}) {
    const global = getEffectiveDesignSettings();
    const mode = SKILL_INPUT_MODES[global.skillId] || SKILL_INPUT_MODES['web-prototype'];
    const isPpt = global.skillId === 'html-ppt';
    const compactPpt = isPpt && pptInputMode === 'import';
    const productNoun = isPpt ? 'HTML 演示文稿' : 'HTML 原型页面';
    const splitPackage = options.packageLayout === 'split' || (options.packageLayout === 'auto' && pages.length >= 4);

    let prompt = `你是专业的前端工程师和UI/UX设计师。
请生成一个高保真的${productNoun}。

# 项目名称
${getProjectNameFromForm()}

# 技术栈
- Tailwind CSS (CDN)
- Vue 3 (CDN, 可选)
- FontAwesome (CDN)
- ECharts (如需图表)
- 中文优先的系统字体栈

# 工作台接入要求（必须实现）
- ${splitPackage ? 'index.html 为入口，子页放 pages/，共享样式与脚本放 assets/；每个 HTML 的 data-proto-page 根据文件名去扩展名后转为小写 slug，index.html 固定为 home。' : '当前输出为单个 index.html，data-proto-page 固定为 home。'}根元素声明 lang="zh-CN"、data-proto-state="default"、data-proto-preview="${global.skillId === 'mobile-app' ? 'mobile' : 'web'}"。
- 导航、按钮、表单行、表格、卡片和状态提示使用稳定的 data-proto-id，采用 kebab-case，页面内唯一；修改原型时保留已有 ID。
- 同一 HTML 内包含多个页面、Tab、分段或弹层状态时，提供 window.PrototypeBridge.enter(stateId)，复用原型自己的导航逻辑，重复调用结果一致；异步切换返回 Promise。
- 各页面视图的 stateId 由下方页面名称转为小写，保留中文、数字和英文，连续空格或符号替换为一个短横线；重复名称追加 -2、-3。default 指向初始视图。
- PrototypeBridge.enter 和原型自身的 Tab、路由、弹层交互都必须同步 document.documentElement.dataset.protoState；不得通过重新加载整页切换视图。
- 不在原型中自行制作工作台的编辑、标注或导出工具栏，这些由预览工作台提供。

# 全局设计规范
- 视觉风格: ${global.designSystemName}
- 产物类型: ${global.skillName}
${DesignSettings.promptRules(global)}

${isPpt ? `# HTML PPT 播放模式要求（必须实现）
- 生成单文件 HTML deck，不是长网页。
- 必须包含两个模式：概览模式（默认）和播放模式。
- 概览模式是默认首屏：用大缩略图网格展示所有 slide，每个缩略图按 16:9 比例渲染该页小图/摘要，缩略图必须足够大到能看清标题、主要文字和配图；桌面端建议每行 2-3 张，移动端每行 1 张，不要做成很小的卡片。
- 概览模式需要有明显的“播放”按钮；点击播放从第 1 页进入播放模式，点击任意缩略图则从对应页进入播放模式。
- 播放模式中每一页幻灯片必须独占整屏：\`width:100vw; height:100vh;\`，默认只显示当前页。
- 支持键盘翻页：ArrowRight / ArrowDown / PageDown / Space 进入下一页；ArrowLeft / ArrowUp / PageUp 返回上一页；Home 到首页；End 到末页。
- 支持鼠标点击或触摸点击进入下一页。
- 播放模式不要显示明显的关闭/返回按钮；只能通过按 Esc 或鼠标右键点击退出播放并返回概览模式。
- 播放模式中右键点击需要阻止浏览器默认菜单，并返回概览模式。
- 提供页码/进度提示和清晰的当前页状态；概览模式中也要显示总页数。
- 不能依赖浏览器滚动浏览全部页面；播放模式翻页逻辑必须由 JS 控制。
- 每个原始 PPT 页面对应一个独立 slide，保持原始页序、信息层级和该页配图归属。
` : ''}
# ${isPpt ? (compactPpt ? 'PPT 导入美化需求' : 'PPT 逐页生成需求') : '页面需求'}
`;

    pages.forEach((id, index) => {
        const name = $(`pageName_${id}`).value || `${mode.unitLabel}${index + 1}`;
        const layout = $(`layout_${id}`).value;
        const features = $(`features_${id}`).value;
        const interaction = $(`interaction_${id}`).value;
        const similarity = (document.querySelector(`input[name="similarity_${id}"]:checked`) || {}).value || 'layout';
        const pptImages = pagePptImages[id] || [];
        const referenceImages = pageFiles[id] || [];
        const hasImages = referenceImages.length > 0;

        prompt += `
## ${mode.unitLabel}${index + 1}: ${name}
`;
        if (layout) prompt += `**${mode.layoutLabel}**: ${layout}\n`;
        if (features && !compactPpt) prompt += `**${mode.featuresLabel}**: ${features}\n`;
        if (interaction) prompt += `**${mode.interactionLabel}**: ${interaction}\n`;
        if (isPpt && pptImages.length > 0) {
            const grouped = {};
            pptImages.forEach(img => {
                const key = img.slideIndex || index + 1;
                if (!grouped[key]) grouped[key] = 0;
                grouped[key] += 1;
            });
            prompt += `**PPT 原始配图**: 已附加 ${pptImages.length} 张配图。它们不是参考图，必须放回对应原始页。配图页归属：${Object.entries(grouped).map(([slide, count]) => `第${slide}页 ${count}张`).join('；')}。\n`;
        }
        if (hasImages) {
            prompt += `**参考图**: 已附加${referenceImages.length}张参考图。请先识别参考图中的页面类型、信息架构、主要模块、文字线索、视觉层级和交互控件；参考图是本页生成的核心依据，不要忽略，也不要自行替换成无关业务页面。`;
            if (isPpt) {
                prompt += `仅用于辅助整体视觉风格判断，不替代 PPT 原始配图，也不要按参考图相似度还原。\n`;
            } else {
                if (similarity === 'pixel') {
                    prompt += `参考图模式：像素级还原。必须严格还原参考图的布局、比例、颜色、字体层级、组件样式、内容密度、图标/图片位置和可读文字；不得主动改动参考图中的主要结构、视觉风格、模块顺序和关键文案。用户文字需求只用于补充缺失信息，不要改成无关主题。\n`;
                } else if (similarity === 'style') {
                    prompt += `参考图模式：仅参考风格。只提取色彩、字体气质、圆角/阴影、图标语言、留白、质感和整体视觉调性；不要照抄参考图的布局结构、模块顺序或具体内容，页面结构以用户文字需求为准。\n`;
                } else {
                    prompt += `参考图模式：仅参考布局。只提取页面类型、区域划分、模块层级、组件关系、排列方向、信息密度和交互入口位置；不要照抄参考图的配色、品牌视觉、字体风格或装饰质感，视觉风格以用户选择的设计系统/表单设置为准。\n`;
                }
            }
        }
    });

    prompt += `
# 输出要求（重要！）

${splitPackage ? '请交付完整的多页面静态项目，包含 index.html 入口、pages/ 子页面及必要的 assets/ 共享资源；保留不同页面间的导航。' : '请输出一个**完整的、独立的HTML文件**。'}

要求：
1. ${splitPackage ? 'CSS 可放入 assets/ 共享样式，使用正确的相对路径引用' : '所有CSS放在<style>标签中'}
2. ${splitPackage ? 'JS 可放入 assets/ 共享脚本，各页面能直接打开运行' : '所有JS放在<script>标签中'}
3. 使用真实的示例数据（不要Lorem ipsum）
4. 响应式设计
5. 直接可在浏览器中打开使用

输出格式：
${splitPackage ? '按文件路径分别交付各文件，以下为 index.html 入口示例。' : ''}
\`\`\`html
<!DOCTYPE html>
<html lang="zh-CN" data-proto-page="home" data-proto-state="default" data-proto-preview="${global.skillId === 'mobile-app' ? 'mobile' : 'web'}">
...完整代码...
</html>
\`\`\`
`;

    return prompt;
}

// 收集用户输入数据用于保存记录
function collectFormData() {
    const global = {
        projectName: getProjectNameFromForm(),
        ...getEffectiveDesignSettings()
    };
    global.previewType = global.skillId === 'mobile-app' ? 'mobile' : 'web';

    const pagesData = pages.map((id, index) => ({
        name: $(`pageName_${id}`).value || `页面${index + 1}`,
        layout: $(`layout_${id}`).value,
        features: $(`features_${id}`).value,
        interaction: $(`interaction_${id}`).value,
        similarity: (document.querySelector(`input[name="similarity_${id}"]:checked`) || {}).value || 'layout',
        imageCount: (pagePptImages[id]?.length || 0) + pageFiles[id].length,
        pptImageCount: pagePptImages[id]?.length || 0,
        referenceImageCount: pageFiles[id].length,
        pptImages: (pagePptImages[id] || []).map(img => ({
            name: img.name,
            slideIndex: img.slideIndex || index + 1,
            slideTitle: img.slideTitle || ''
        }))
    }));

    return { global, pages: pagesData };
}

function getProjectNameFromForm() {
    return $('projectNameInput')?.value.trim() || getDefaultProjectName();
}

function getDefaultProjectName() {
    const pageNames = pages.map(id => $(`pageName_${id}`)?.value.trim()).filter(Boolean).join(' + ');
    if (pageNames) return pageNames.slice(0, 80);

    const skillId = $('skillSelect') ? $('skillSelect').value : 'web-prototype';
    const firstLayout = pages.map(id => $(`layout_${id}`)?.value.trim()).find(Boolean);
    if (firstLayout) return firstLayout.split(/\r?\n/)[0].slice(0, 24);

    const now = new Date();
    const pad = value => String(value).padStart(2, '0');
    const time = `${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
    return `${skillId === 'html-ppt' ? 'HTML PPT' : '原型项目'} ${time}`;
}

function fillProjectName() {
    const name = getProjectNameFromForm();
    const input = $('projectNameInput');
    if (input && input.value !== name) {
        input.value = name;
        input.dispatchEvent(new Event('input', { bubbles: true }));
    }
    return name;
}

// ==================== 增量更新功能 ====================

// 计算简单的字符串哈希
function simpleHash(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash;
    }
    return hash.toString(16);
}

// 计算所有页面的图片哈希
function computeAllImageHashes() {
    const hashes = {};
    pages.forEach((id, index) => {
        const images = pageFiles[id] || [];
        const pptImages = pagePptImages[id] || [];
        const imageData = [
            ...pptImages.map(f => f.base64.substring(0, 100)),
            ...images.map(f => f.base64.substring(0, 100))
        ].join('|');
        hashes[index] = simpleHash(imageData);
    });
    return hashes;
}

// ==================== 输入验证 ====================
/**
 * 检查是否有任何用户输入
 * @returns {boolean} 如果有任何输入返回true，否则返回false
 */
function hasAnyInput() {
    // 检查是否有页面名称
    const hasPageName = pages.some(id => {
        const name = $(`pageName_${id}`);
        return name && name.value && name.value.trim() !== '';
    });

    // 检查是否有布局描述
    const hasLayout = pages.some(id => {
        const layout = $(`layout_${id}`);
        return layout && layout.value && layout.value.trim() !== '';
    });

    // 检查是否有功能点描述
    const hasFeatures = pages.some(id => {
        const features = $(`features_${id}`);
        return features && features.value && features.value.trim() !== '';
    });

    // 检查是否有交互方式描述
    const hasInteraction = pages.some(id => {
        const interaction = $(`interaction_${id}`);
        return interaction && interaction.value && interaction.value.trim() !== '';
    });

    // 检查是否有参考图片
    const hasImages = pages.some(id =>
        (pageFiles[id] && pageFiles[id].length > 0) ||
        (pagePptImages[id] && pagePptImages[id].length > 0)
    );

    // 只检查主动选择；继承的预设值不视为额外输入。
    const globalChanged = (
        $('customColorsToggle').checked ||
        $('backgroundMode').value !== 'inherit' ||
        !!$('designSystemSelect')?.value
    );

    // 只要有任何一项输入就返回true
    return hasPageName || hasLayout || hasFeatures || hasInteraction || hasImages || globalChanged;
}

/**
 * 显示Toast提示
 * @param {string} message - 提示消息
 * @param {string} type - 类型: 'success', 'error', 'info'
 */
function showToast(message, type = 'success') {
    console.log('[Toast] 显示提示:', message, '类型:', type);

    const toast = $('toast');
    const toastIcon = $('toastIcon');
    const toastMessage = $('toastMessage');

    if (!toast || !toastIcon || !toastMessage) {
        console.error('[Toast] DOM元素未找到!', { toast, toastIcon, toastMessage });
        return;
    }

    // 设置消息
    toastMessage.textContent = message;

    // 设置图标和颜色
    if (type === 'success') {
        toastIcon.className = 'fas fa-check-circle text-green-400';
    } else if (type === 'error') {
        toastIcon.className = 'fas fa-exclamation-circle text-red-400';
    } else if (type === 'info') {
        toastIcon.className = 'fas fa-info-circle text-blue-400';
    }

    // 移除隐藏状态
    toast.classList.remove('hidden');

    // 强制重绘以触发动画
    requestAnimationFrame(() => {
        toast.classList.remove('translate-y-20', 'opacity-0');
        toast.classList.add('translate-y-0', 'opacity-100');
    });

    // 3秒后隐藏
    setTimeout(() => {
        toast.classList.remove('translate-y-0', 'opacity-100');
        toast.classList.add('translate-y-20', 'opacity-0');

        // 动画结束后完全隐藏
        setTimeout(() => {
            toast.classList.add('hidden');
        }, 300); // 等待transition完成
    }, 3000);
}

// 检测变更
function detectChanges(original, current, origImgHashes, currImgHashes) {
    const changes = {
        hasChanges: false,
        globalChanged: false,
        pagesChanged: [],      // 变化的页面索引
        pagesUnchanged: [],    // 未变化的页面索引
        newPages: [],          // 新增的页面索引
        deletedPages: []       // 删除的页面索引
    };

    if (!original || !current) {
        changes.hasChanges = true;
        return changes;
    }

    // 对比全局设置
    const originalSettings = { ...(original.global || {}) };
    const currentSettings = { ...(current.global || {}) };
    delete originalSettings.projectName;
    delete currentSettings.projectName;
    if (JSON.stringify(originalSettings) !== JSON.stringify(currentSettings)) {
        changes.globalChanged = true;
        changes.hasChanges = true;
    }

    // 对比页面数量
    const origLen = original.pages.length;
    const currLen = current.pages.length;

    // 对比每个页面
    current.pages.forEach((page, i) => {
        if (i >= origLen) {
            // 新增的页面
            changes.newPages.push(i);
            changes.hasChanges = true;
        } else {
            const origPage = original.pages[i];
            const origImgHash = origImgHashes[i] || '';
            const currImgHash = currImgHashes[i] || '';

            // 对比页面内容和图片
            const pageContentSame = (
                origPage.name === page.name &&
                origPage.layout === page.layout &&
                origPage.features === page.features &&
                origPage.interaction === page.interaction &&
                origPage.similarity === page.similarity
            );
            const imagesSame = (origImgHash === currImgHash);

            if (pageContentSame && imagesSame) {
                changes.pagesUnchanged.push(i);
            } else {
                changes.pagesChanged.push(i);
                changes.hasChanges = true;
            }
        }
    });

    // 检查删除的页面
    for (let i = currLen; i < origLen; i++) {
        changes.deletedPages.push(i);
        changes.hasChanges = true;
    }

    return changes;
}

async function generateWithAI() {
    // 验证是否有任何输入
    const hasInput = hasAnyInput();
    console.log('[验证] hasAnyInput 返回:', hasInput);

    if (!hasInput) {
        console.log('[验证] 没有输入，显示提示');
        await showAppAlert({
            title: '还没有可生成的内容',
            message: '请先填写页面名称、布局描述、功能说明，或上传参考图/导入 PPT。',
            tone: 'warning'
        });
        return;
    }

    pages.forEach(id => sanitizePageImages(id));
    enforceRequestImageLimit();

    // 收集当前表单数据
    const projectName = fillProjectName();
    const formData = collectFormData();
    const currentImageHashes = computeAllImageHashes();

    // 检测变更（如果有来源项目）
    let changes = null;
    let useIncremental = false;

    console.log('[增量更新] 检测状态:', {
        hasSourceProjectId: !!sourceProjectId,
        hasOriginalFormData: !!originalFormData,
        sourceProjectId,
        currentFormData: formData,
        originalFormData,
        currentImageHashes,
        originalImageHashes
    });

    if (sourceProjectId && originalFormData) {
        changes = detectChanges(originalFormData, formData, originalImageHashes, currentImageHashes);
        console.log('[增量更新] 变更检测结果:', changes);

        if (!changes.hasChanges) {
            // 无变化，直接复制项目
            showToast('内容未变化，将复制原项目', 'info');
            useIncremental = true;
        } else if (changes.pagesUnchanged.length > 0) {
            // 部分页面未变化，使用增量更新
            console.log(`[增量更新] ${changes.pagesUnchanged.length}个页面未变化，将复用`);
            useIncremental = true;
        }
    } else {
        console.log('[增量更新] 非增量模式：sourceProjectId或originalFormData为空');
    }

    // 生成prompt
    const prompt = generatePrompt();
    console.log('=== Prompt ===');
    console.log(prompt);

    // 收集所有图片：PPT 配图在前，额外参考图在后，保证 prompt 里的页归属顺序可对应。
    const allImages = [];
    pages.forEach(id => {
        (pagePptImages[id] || []).forEach(f => {
            if (allImages.length < MAX_AI_IMAGES_PER_REQUEST) {
                allImages.push(f.base64);
            }
        });
        (pageFiles[id] || []).forEach(f => {
            if (allImages.length < MAX_AI_IMAGES_PER_REQUEST) {
                allImages.push(f.base64);
            }
        });
    });
    const totalImages = pages.reduce((sum, id) => sum + (pagePptImages[id]?.length || 0) + (pageFiles[id]?.length || 0), 0);
    if (totalImages > MAX_AI_IMAGES_PER_REQUEST) {
        showToast(`图片超过模型网关上限，本次仅发送前 ${MAX_AI_IMAGES_PER_REQUEST} 张`, 'warning');
    }

    try {
        // 构建请求数据
        const requestData = {
            prompt: prompt,
            images: allImages,
            projectName: projectName,
            formData: formData,
            designSystemId: formData.global.designSystemId,
            skillId: formData.global.skillId
        };

        // 如果使用增量更新，添加额外信息
        if (useIncremental && changes) {
            requestData.incremental = true;
            requestData.sourceProjectId = sourceProjectId;
            requestData.changes = changes;
        }

        // ==================== 异步生成模式 ====================
        showToast('🚀 开始生成，请稍候...', 'info');

        const response = await fetch('/generate-async', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });

        const result = await response.json();

        if (result.error) {
            showToast('生成失败: ' + result.error, 'error');
            return;
        }

        if (result.success && result.project) {
            // 立即添加带 generating 状态的项目到列表
            allProjects.unshift(result.project);
            renderProjectList();
            showGeneratedProjects();
            showToast('已开始生成「' + result.project.name + '」，进度显示在项目列表中');

            // 开始轮询状态
            pollGenerationStatus(result.project.id);

            // 重置增量更新状态
            sourceProjectId = null;
            originalFormData = null;
            originalImageHashes = {};
        }

    } catch (error) {
        showToast('请求失败: ' + error.message, 'error');
        console.error(error);
    }
}

// ==================== 异步状态轮询 ====================
function pollGenerationStatus(projectId) {
    const POLL_INTERVAL = 3000; // 每3秒轮询一次
    const MAX_POLLS = 120; // 最多轮询120次（6分钟超时）
    let pollCount = 0;

    const poll = async () => {
        pollCount++;
        console.log(`[轮询] 第${pollCount}次检查项目状态: ${projectId}`);

        try {
            const response = await fetch(`/api/generation-status?id=${encodeURIComponent(projectId)}`);
            const data = await response.json();

            console.log('[轮询] 状态:', data);

            // 更新列表中的项目状态
            const projectIndex = allProjects.findIndex(p => p.id === projectId);
            if (projectIndex !== -1) {
                if (data.status === 'completed') {
                    // 生成完成
                    allProjects[projectIndex].status = null; // 清除 generating 状态
                    renderProjectList();
                    showToast('✅ "' + allProjects[projectIndex].name + '" 生成完成！');

                    // 自动打开预览
                    setTimeout(() => {
                        window.open(`/projects/${projectId}/index.html`, '_blank');
                    }, 500);
                    return; // 停止轮询

                } else if (data.status === 'failed') {
                    // 生成失败
                    allProjects[projectIndex].status = 'failed';
                    renderProjectList();
                    showToast('❌ "' + allProjects[projectIndex].name + '" 生成失败: ' + (data.error || '未知错误'), 'error');
                    return; // 停止轮询
                }
            }

            // 继续轮询
            if (pollCount < MAX_POLLS) {
                setTimeout(poll, POLL_INTERVAL);
            } else {
                showToast('⚠️ 生成超时，请刷新页面查看状态', 'error');
            }

        } catch (error) {
            console.error('[轮询错误]', error);
            // 网络错误时继续轮询
            if (pollCount < MAX_POLLS) {
                setTimeout(poll, POLL_INTERVAL);
            }
        }
    };

    // 首次轮询延迟3秒开始（给后端一点启动时间）
    setTimeout(poll, POLL_INTERVAL);
}

// ==================== 外部 AI 生成 ====================
function openExternalAiModal() {
    const modal = $('externalAiModal');
    if (!modal) return;
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

function closeExternalAiModal() {
    const modal = $('externalAiModal');
    if (!modal) return;
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

async function runExternalAiMode(mode) {
    closeExternalAiModal();
    if (mode === 'prompt') {
        await copyPromptToClipboard();
        return;
    }
    if (mode === 'package') {
        await createAiIdePackage();
    }
}

// ==================== 复制Prompt功能 ====================
async function copyPromptToClipboard() {
    // 验证是否有任何输入
    const hasInput = hasAnyInput();
    console.log('[复制Prompt验证] hasAnyInput 返回:', hasInput);

    if (!hasInput) {
        console.log('[复制Prompt验证] 没有输入，显示提示');
        await showAppAlert({
            title: '还没有可复制的 Prompt',
            message: '请先填写页面名称、布局描述、功能说明，或上传参考图/导入 PPT。',
            tone: 'warning'
        });
        return;
    }

    const projectName = fillProjectName();
    const prompt = generatePrompt();
    const formData = collectFormData();

    // 先生成项目ID（文件夹名），这样可以包含在prompt中
    const projectId = generateProjectIdFromName(projectName);

    // 构建完整说明 - 包含实际的项目文件夹名
    let fullPrompt = `# 原型生成任务

## 项目ID
${projectId}

## 设计要求
${prompt}
`;

    // 添加参考图片信息
    const hasImages = pages.some(id => pageFiles[id] && pageFiles[id].length > 0);
    const hasPptImages = pages.some(id => pagePptImages[id] && pagePptImages[id].length > 0);
    if (hasImages || hasPptImages) {
        fullPrompt += `\n## 图片资源\n`;
        pages.forEach((id, index) => {
            const pptImages = pagePptImages[id] || [];
            const images = pageFiles[id] || [];
            if (pptImages.length > 0) {
                fullPrompt += `页面${index + 1}: ${pptImages.length}张 PPT 原始配图\n`;
            }
            if (images.length > 0) {
                fullPrompt += `页面${index + 1}: ${images.length}张参考图\n`;
            }
        });
        fullPrompt += `\n注意：图片已保存在项目文件夹 \`${projectId}\` 中\n`;
    }

    fullPrompt += `\n## 输出要求\n生成完整的HTML文件，保存到项目文件夹 \`${projectId}\` 的 index.html。`;

    // 收集图片数据（按页面索引组织）
    const imageFiles = {};
    pages.forEach((id, index) => {
        const images = [...(pagePptImages[id] || []), ...(pageFiles[id] || [])];
        if (images.length > 0) {
            imageFiles[index] = images.map(f => f.base64);
        }
    });

    // 先创建占位项目
    try {
        const response = await fetch('/create-placeholder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                projectId,
                projectName,
                formData,
                imageFiles,
                prompt: fullPrompt
            })
        });

        const result = await response.json();
        if (result.success && result.project) {
            // 添加到列表
            allProjects.unshift(result.project);
            renderProjectList();

            showGeneratedProjects();

            // 占位项目创建成功后，再复制prompt
            await navigator.clipboard.writeText(result.instruction || fullPrompt);
            showToast('✅ Prompt已复制！粘贴到Antigravity/Cursor等工具中使用');
        } else {
            showToast('占位项目创建失败', 'error');
        }
    } catch (err) {
        console.error('操作失败:', err);
        showToast('操作失败: ' + err.message, 'error');
    }
}

// ==================== AI IDE 项目包 ====================
async function createAiIdePackage() {
    const hasInput = hasAnyInput();
    if (!hasInput) {
        await showAppAlert({
            title: '还没有可打包的需求',
            message: '请先填写页面名称、布局描述、功能说明，或上传参考图/导入 PPT。',
            tone: 'warning'
        });
        return;
    }

    const btn = $('externalAiBtn');
    const originalText = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 打包中...';
    }

    const pageLayout = (document.querySelector('input[name="pageLayout"]:checked') || {}).value || 'auto';
    const projectName = fillProjectName();
    const prompt = generatePrompt({ packageLayout: pageLayout });
    const formData = collectFormData();
    const projectId = generateProjectIdFromName(projectName);

    const imageAssets = {};
    pages.forEach((id, index) => {
        const similarity = (document.querySelector(`input[name="similarity_${id}"]:checked`) || {}).value || 'layout';
        const assets = [];

        (pagePptImages[id] || []).forEach((img, imgIndex) => {
            assets.push({
                kind: 'ppt',
                name: img.name || `ppt-${index + 1}-${imgIndex + 1}`,
                base64: img.base64,
                slideIndex: img.slideIndex || index + 1,
                slideTitle: img.slideTitle || '',
                similarity: 'source'
            });
        });

        (pageFiles[id] || []).forEach((img, imgIndex) => {
            assets.push({
                kind: 'reference',
                name: img.name || `reference-${index + 1}-${imgIndex + 1}`,
                base64: img.base64,
                similarity
            });
        });

        if (assets.length > 0) {
            imageAssets[index] = assets;
        }
    });

    try {
        const response = await fetch('/create-ai-ide-package', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                projectId,
                projectName,
                formData,
                imageAssets,
                prompt,
                pageLayout
            })
        });

        const result = await response.json();
        if (result.success && result.project) {
            allProjects.unshift(result.project);
            renderProjectList();

            showGeneratedProjects();

            const instruction = `${result.instruction}\n\n项目目录：${result.projectDir}`;
            try {
                await navigator.clipboard.writeText(instruction);
                showToast('✅ AI IDE 项目包已创建，启动指令已复制');
            } catch (e) {
                showToast('✅ AI IDE 项目包已创建');
            }

            await showAppAlert({
                title: 'AI IDE 项目包已创建',
                message: `项目目录：${result.projectDir}\n\n已生成 AGENTS.md、TASK.md、DESIGN.md、pages/ 和 reference/manifest.json。用 Cursor/Codex 打开该目录后，粘贴已复制的启动指令即可。`,
                tone: 'success',
                confirmText: '知道了'
            });
        } else {
            showToast('打包失败: ' + (result.error || '未知错误'), 'error');
        }
    } catch (err) {
        console.error('创建 AI IDE 项目包失败:', err);
        showToast('打包失败: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    }
}

function generateProjectIdFromName(name) {
    const now = new Date();
    const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '');

    // 使用与服务端一致的12小时制格式: {H}-{MM}-{SS}{am/pm}
    let hour = now.getHours();
    const amPm = hour < 12 ? 'am' : 'pm';
    hour = hour <= 12 ? hour : hour - 12;
    if (hour === 0) hour = 12;

    const minutes = String(now.getMinutes()).padStart(2, '0');
    const seconds = String(now.getSeconds()).padStart(2, '0');
    const timeStr = `${hour}-${minutes}-${seconds}${amPm}`;

    // 处理不安全字符（与服务端一致）
    let safeName = name.replace(/[\\\/:*?"<>|]/g, '').replace(/ /g, '_');
    if (safeName.length > 30) safeName = safeName.slice(0, 30);

    return `${safeName}_${dateStr}_${timeStr}`;
}

// ==================== 工具函数 ====================
function showToast(msg, type = 'success') {
    const toast = $('toast');
    $('toastMessage').textContent = msg;
    if (type === 'error') {
        $('toastIcon').className = 'fas fa-exclamation-circle text-red-400';
    } else if (type === 'warning') {
        $('toastIcon').className = 'fas fa-exclamation-triangle text-amber-400';
    } else if (type === 'info') {
        $('toastIcon').className = 'fas fa-info-circle text-blue-400';
    } else {
        $('toastIcon').className = 'fas fa-check-circle text-green-400';
    }

    toast.classList.remove('translate-y-20', 'opacity-0');
    setTimeout(() => toast.classList.add('translate-y-20', 'opacity-0'), 3000);
}

// ==================== 应用内弹窗（替代浏览器默认弹窗） ====================
function setDialogTone(tone = 'info') {
    const iconBox = $('appDialogIcon');
    const confirmBtn = $('appDialogConfirm');
    if (!iconBox || !confirmBtn) return;

    const tones = {
        info: {
            icon: 'fas fa-info-circle',
            box: 'w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center flex-none',
            button: 'px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium transition'
        },
        warning: {
            icon: 'fas fa-exclamation-triangle',
            box: 'w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center flex-none',
            button: 'px-4 py-2.5 bg-amber-500 hover:bg-amber-600 text-white rounded-lg text-sm font-medium transition'
        },
        danger: {
            icon: 'fas fa-trash-alt',
            box: 'w-10 h-10 rounded-xl bg-red-50 text-red-500 flex items-center justify-center flex-none',
            button: 'px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium transition'
        },
        success: {
            icon: 'fas fa-check-circle',
            box: 'w-10 h-10 rounded-xl bg-green-50 text-green-600 flex items-center justify-center flex-none',
            button: 'px-4 py-2.5 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-medium transition'
        }
    };

    const selected = tones[tone] || tones.info;
    iconBox.className = selected.box;
    iconBox.innerHTML = `<i class="${selected.icon}"></i>`;
    confirmBtn.className = selected.button;
}

function showAppDialog(options = {}) {
    const dialog = $('appDialog');
    const titleEl = $('appDialogTitle');
    const messageEl = $('appDialogMessage');
    const inputEl = $('appDialogInput');
    const cancelBtn = $('appDialogCancel');
    const confirmBtn = $('appDialogConfirm');
    const overlay = $('appDialogOverlay');

    if (!dialog || !titleEl || !messageEl || !inputEl || !cancelBtn || !confirmBtn) {
        showToast(options.message || options.title || '请确认操作', options.tone === 'danger' ? 'error' : 'info');
        return Promise.resolve(options.type === 'confirm' ? false : null);
    }

    return new Promise(resolve => {
        titleEl.textContent = options.title || '提示';
        messageEl.textContent = options.message || '';
        confirmBtn.textContent = options.confirmText || '确定';
        cancelBtn.textContent = options.cancelText || '取消';
        cancelBtn.classList.toggle('hidden', options.type === 'alert');
        inputEl.classList.toggle('hidden', options.type !== 'prompt');
        inputEl.value = options.defaultValue || '';
        inputEl.placeholder = options.placeholder || '';
        setDialogTone(options.tone || 'info');

        const cleanup = result => {
            dialog.classList.add('hidden');
            dialog.classList.remove('flex');
            confirmBtn.onclick = null;
            cancelBtn.onclick = null;
            overlay.onclick = null;
            document.removeEventListener('keydown', onKeydown);
            resolve(result);
        };

        const onKeydown = event => {
            if (event.key === 'Escape') cleanup(options.type === 'alert' ? true : null);
            if (event.key === 'Enter' && options.type === 'prompt') cleanup(inputEl.value);
        };

        confirmBtn.onclick = () => {
            if (options.type === 'prompt') cleanup(inputEl.value);
            else cleanup(true);
        };
        cancelBtn.onclick = () => cleanup(options.type === 'confirm' ? false : null);
        overlay.onclick = () => cleanup(options.type === 'confirm' ? false : null);
        document.addEventListener('keydown', onKeydown);

        dialog.classList.remove('hidden');
        dialog.classList.add('flex');
        if (options.type === 'prompt') {
            setTimeout(() => {
                inputEl.focus();
                inputEl.select();
            }, 50);
        }
    });
}

function showAppAlert(options = {}) {
    return showAppDialog({ ...options, type: 'alert' });
}

function showAppConfirm(options = {}) {
    return showAppDialog({ ...options, type: 'confirm' });
}

function showAppPrompt(options = {}) {
    return showAppDialog({ ...options, type: 'prompt' });
}

// ==================== 模型管理 ====================

async function loadModels() {
    try {
        const res = await fetch('/api/models?t=' + Date.now());
        const data = await res.json();
        modelsList = data.models || [];
        selectedModelId = data.selected_model_id || '';

        // 找到当前选中的模型
        currentModel = modelsList.find(m => m.id === selectedModelId) || modelsList[0] || null;

        // 更新顶栏显示
        $('currentModelName').textContent = currentModel ? currentModel.name : '未配置';

        // 渲染下拉列表
        renderModelDropdown();
    } catch (e) {
        console.error('加载模型列表失败:', e);
        $('currentModelName').textContent = '加载失败';
    }
}

function renderModelDropdown() {
    const container = $('modelDropdownList');
    if (!modelsList.length) {
        container.innerHTML = '<div class="px-4 py-3 text-sm text-gray-400 text-center">暂无模型</div>';
        return;
    }
    container.innerHTML = modelsList.map(m => `
        <div class="model-dropdown-item ${m.id === selectedModelId ? 'active' : ''}" onclick="selectModel('${m.id}')">
            <span class="check">${m.id === selectedModelId ? '<i class="fas fa-check"></i>' : ''}</span>
            <div class="flex-1 min-w-0">
                <div class="font-medium truncate flex items-center gap-1.5">
                    ${m.name}
                    ${m.multimodal ? '<span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-purple-50 text-purple-600 leading-none">多模态</span>' : ''}
                </div>
                <div class="text-xs text-gray-400 truncate">${m.provider || ''} · ${m.model}</div>
            </div>
        </div>
    `).join('');
}

function toggleModelDropdown(e) {
    e.stopPropagation();
    const dropdown = $('modelDropdown');
    dropdown.classList.toggle('show');
}

// 点击外部关闭下拉
document.addEventListener('click', (e) => {
    const dropdown = $('modelDropdown');
    if (dropdown && !e.target.closest('#modelSelector')) {
        dropdown.classList.remove('show');
    }
});

async function selectModel(id) {
    try {
        const res = await fetch('/api/models/select', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id })
        });
        const data = await res.json();
        if (data.success) {
            selectedModelId = id;
            currentModel = modelsList.find(m => m.id === id);
            $('currentModelName').textContent = currentModel ? currentModel.name : id;
            renderModelDropdown();
            $('modelDropdown').classList.remove('show');
            // 如果模型管理弹窗打开中，刷新列表以更新"当前"标签
            if ($('modelManagerModal') && !$('modelManagerModal').classList.contains('hidden')) {
                renderModelManagerList();
            }
            showToast('已切换到: ' + (currentModel?.name || id));
        }
    } catch (e) {
        showToast('切换失败', 'error');
    }
}

function openModelManager() {
    $('modelDropdown').classList.remove('show');
    $('modelManagerModal').classList.remove('hidden');
    $('modelManagerModal').classList.add('flex');
    renderModelManagerList();
    resetModelForm();
}

function closeModelManager() {
    $('modelManagerModal').classList.add('hidden');
    $('modelManagerModal').classList.remove('flex');
}

function renderModelManagerList() {
    const container = $('modelManagerList');
    const editingId = $('editModelId').value;
    if (!modelsList.length) {
        container.innerHTML = '<div class="text-center py-6 text-gray-400 text-sm">暂无模型配置</div>';
        return;
    }
    container.innerHTML = modelsList.map(m => `
        <div class="model-manager-item${m.id === editingId ? ' is-editing' : ''}${m.id === selectedModelId ? ' is-current' : ''} flex items-center gap-3 p-3 rounded-lg border transition cursor-pointer"
             onclick="editModel('${m.id}')">
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                    <span class="font-medium text-sm text-gray-900 truncate">${m.name}</span>
                    ${m.id === selectedModelId ? '<span class="model-current-badge text-xs px-1.5 py-0.5 rounded">当前</span>' : ''}
                    ${m.multimodal ? '<span class="model-capability-badge text-xs px-1.5 py-0.5 rounded">多模态</span>' : ''}
                </div>
                <div class="text-xs text-gray-400 mt-0.5 truncate">${m.provider || '—'} · ${m.model}</div>
            </div>
            <div class="flex items-center gap-1 flex-shrink-0" onclick="event.stopPropagation()">
                ${m.id !== selectedModelId ? `<button onclick="selectModel('${m.id}')" class="p-1.5 text-gray-400 hover:text-indigo-600 rounded hover:bg-indigo-50" title="选用"><i class="fas fa-check-circle"></i></button>` : ''}
                <button onclick="duplicateModel('${m.id}')" class="p-1.5 text-gray-400 hover:text-teal-600 rounded hover:bg-teal-50" title="复制"><i class="fas fa-copy"></i></button>
                <button onclick="editModel('${m.id}')" class="p-1.5 text-gray-400 hover:text-blue-600 rounded hover:bg-blue-50" title="编辑"><i class="fas fa-edit"></i></button>
                <button onclick="deleteModel('${m.id}')" class="p-1.5 text-gray-400 hover:text-red-500 rounded hover:bg-red-50" title="删除"><i class="fas fa-trash-alt"></i></button>
            </div>
        </div>
    `).join('');
}

function editModel(id) {
    const m = modelsList.find(x => x.id === id);
    if (!m) return;
    $('editModelId').value = m.id;
    $('modelFormName').value = m.name || '';
    $('modelFormProvider').value = m.provider || '';
    $('modelFormModel').value = m.model || '';
    $('modelFormBaseUrl').value = m.base_url || '';
    $('modelFormApiKey').value = m.api_key || '';
    $('modelFormMultimodal').checked = !!m.multimodal;
    $('modelFormTitle').textContent = '编辑模型: ' + m.name;
    // 刷新列表以高亮当前编辑项
    renderModelManagerList();
}

async function duplicateModel(id) {
    const m = modelsList.find(x => x.id === id);
    if (!m) return;

    const newId = m.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') + '-' + Date.now().toString(36);
    const newModel = {
        id: newId,
        name: m.name + ' (副本)',
        provider: m.provider || '',
        model: m.model || '',
        base_url: m.base_url || '',
        api_key: m.api_key || '',
        multimodal: !!m.multimodal
    };

    try {
        const res = await fetch('/api/models/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newModel)
        });
        const data = await res.json();
        if (data.success) {
            showToast('模型已复制: ' + newModel.name);
            await loadModels();
            renderModelManagerList();
        } else {
            showToast('复制失败: ' + (data.error || ''), 'error');
        }
    } catch (e) {
        showToast('复制失败', 'error');
    }
}

async function saveModelForm() {
    const existingId = $('editModelId').value;
    const name = $('modelFormName').value.trim();
    const provider = $('modelFormProvider').value.trim();
    const model = $('modelFormModel').value.trim();
    const baseUrl = $('modelFormBaseUrl').value.trim();
    const apiKey = $('modelFormApiKey').value.trim();
    const multimodal = $('modelFormMultimodal').checked;

    if (!name || !model || !baseUrl || !apiKey) {
        showToast('请填写所有必填字段', 'error');
        return;
    }

    // 生成 ID：编辑时沿用，新增时自动生成
    const id = existingId || name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') + '-' + Date.now().toString(36);

    const modelData = { id, name, provider, model, base_url: baseUrl, api_key: apiKey, multimodal };

    try {
        const res = await fetch('/api/models/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(modelData)
        });
        const data = await res.json();
        if (data.success) {
            showToast(existingId ? '模型已更新' : '模型已添加');
            await loadModels();
            renderModelManagerList();
            resetModelForm();
        } else {
            showToast('保存失败: ' + (data.error || ''), 'error');
        }
    } catch (e) {
        showToast('保存失败', 'error');
    }
}

async function deleteModel(id) {
    const m = modelsList.find(x => x.id === id);
    const confirmed = await showAppConfirm({
        title: '删除模型',
        message: `确定要删除模型「${m?.name || id}」吗？`,
        confirmText: '删除',
        tone: 'danger'
    });
    if (!confirmed) return;

    try {
        const res = await fetch('/api/models/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id })
        });
        const data = await res.json();
        if (data.success) {
            showToast('模型已删除');
            await loadModels();
            renderModelManagerList();
            // 如果删除的是当前编辑的，重置表单
            if ($('editModelId').value === id) {
                resetModelForm();
            }
        } else {
            showToast(data.error || '删除失败', 'error');
        }
    } catch (e) {
        showToast('删除失败', 'error');
    }
}

function resetModelForm() {
    $('editModelId').value = '';
    $('modelFormName').value = '';
    $('modelFormProvider').value = '';
    $('modelFormModel').value = '';
    $('modelFormBaseUrl').value = '';
    $('modelFormApiKey').value = '';
    $('modelFormMultimodal').checked = false;
    $('modelFormTitle').textContent = '添加新模型';
    // 刷新列表取消高亮
    if ($('modelManagerModal') && !$('modelManagerModal').classList.contains('hidden')) {
        renderModelManagerList();
    }
}


// ==================== 项目导出与分享 ====================

async function openExportModal(id, name) {
    try {
        const response = await fetch('/api/projects/workbench', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ projectId: id })
        });
        const data = await response.json();
        if (!response.ok || !data.ok || !data.projectId) {
            throw new Error(data.error || '项目工作台加载失败');
        }
        await openExtPublishModal({ projectId: data.projectId, name: data.name || name });
    } catch (error) {
        showToast('打开导出与分享失败：' + error.message, 'error');
    }
}

function closeUnpublishConfirmModal() {
    $('unpublishConfirmModal').classList.add('hidden');
    $('unpublishConfirmModal').classList.remove('flex');
}

async function executeGitHubUnpublish() {
    await executeExtGithubUnpublish();
}


// ==================== 统一发布与导出弹窗 ====================

let currentExtPubId = '';
let currentExtPubName = '';
let currentExtPubMode = 'pure';

async function openExtPublishModal(item) {
    currentExtPubId = item.projectId;
    currentExtPubName = item.name;
    currentExtPubMode = 'pure';

    // 重置 UI
    const pureRadio = document.querySelector('input[name="extPubMode"][value="pure"]');
    if (pureRadio) pureRadio.checked = true;
    selectExtPubMode('pure');
    $('extPubProjectName').textContent = item.name;
    $('extPubPublishedInfo').classList.add('hidden');
    $('extPubNotConfigured').classList.add('hidden');
    $('extPubConfigured').classList.add('hidden');
    $('extPubUnpublishBtn').classList.add('hidden');
    $('extPubPublishBtnText').textContent = '立即发布';

    $('extPublishModal').classList.remove('hidden');
    $('extPublishModal').classList.add('flex');

    await loadExtPubStatus();
}

function closeExtPublishModal() {
    $('extPublishModal').classList.add('hidden');
    $('extPublishModal').classList.remove('flex');
}

function selectExtPubMode(mode) {
    currentExtPubMode = mode;
    $('extLocalExportBtnText').textContent = mode === 'pure' ? '导出纯净版' : '导出研发版（ZIP）';
}

function doExtLocalExport() {
    if (!currentExtPubId) return;
    const url = `/api/ext/export?extId=${encodeURIComponent(currentExtPubId)}&mode=${currentExtPubMode}`;
    window.open(url, '_blank');
    showToast('开始导出下载，请查看浏览器下载记录');
}

async function loadExtPubStatus() {
    try {
        const resp = await fetch('/api/github/config');
        const data = await resp.json();
        if (!data.success || !data.hasToken || !data.username) {
            $('extPubNotConfigured').classList.remove('hidden');
            return;
        }
        $('extPubConfigured').classList.remove('hidden');
        $('extPubRepoDisplay').textContent = `${data.username}/${data.repo}`;
    } catch (e) {
        $('extPubNotConfigured').classList.remove('hidden');
        return;
    }
    // 查询该项目是否已发布（登记表）
    try {
        const resp = await fetch(`/api/ext/publish-status?projectId=${encodeURIComponent(currentExtPubId)}`);
        const data = await resp.json();
        if (data.ok && data.published && data.url) {
            $('extPubPublishedUrl').value = data.url;
            $('extPubPublishedAt').textContent = data.publishedAt || '';
            $('extPubPublishedInfo').classList.remove('hidden');
            $('extPubPublishBtnText').textContent = '重新发布 / 更新';
            $('extPubUnpublishBtn').classList.remove('hidden');
        }
    } catch (_) { }
}

async function doExtGithubPublish() {
    const btn = $('extPubPublishBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> <span>发布中，请稍候...</span>';
    let finalText = '立即发布';

    try {
        const resp = await fetch('/api/ext/publish', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ extId: currentExtPubId, mode: currentExtPubMode })
        });
        const data = await resp.json();
        if (data.ok) {
            $('extPubPublishedUrl').value = data.url;
            $('extPubPublishedAt').textContent = data.publishedAt || '刚刚';
            $('extPubPublishedInfo').classList.remove('hidden');
            $('extPubUnpublishBtn').classList.remove('hidden');
            finalText = '重新发布 / 更新';
            showToast('🚀 发布成功！约 1-3 分钟后链接生效');
        } else {
            showToast('发布失败: ' + (data.error || '未知错误'), 'error');
            finalText = $('extPubPublishedInfo').classList.contains('hidden') ? '立即发布' : '重新发布 / 更新';
        }
    } catch (e) {
        showToast('发布失败: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fab fa-github"></i> <span id="extPubPublishBtnText">${finalText}</span>`;
    }
}

function doExtGithubUnpublish() {
    $('unpublishConfirmModal').classList.remove('hidden');
    $('unpublishConfirmModal').classList.add('flex');
}

async function executeExtGithubUnpublish() {
    const confirmBtn = $('confirmUnpublishBtn');
    const originalConfirmText = confirmBtn.innerHTML;
    confirmBtn.disabled = true;
    confirmBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 取消中...';

    try {
        const resp = await fetch('/api/ext/unpublish', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ extId: currentExtPubId })
        });
        const data = await resp.json();
        if (data.ok) {
            showToast('✅ 已取消发布并删除 GitHub 上的文件');
            $('extPubPublishedInfo').classList.add('hidden');
            $('extPubPublishBtnText').textContent = '立即发布';
            $('extPubUnpublishBtn').classList.add('hidden');
            closeUnpublishConfirmModal();
        } else {
            showToast('取消发布失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        showToast('请求失败: ' + e.message, 'error');
    } finally {
        confirmBtn.disabled = false;
        confirmBtn.innerHTML = originalConfirmText;
    }
}

function copyExtPubUrl() {
    const url = $('extPubPublishedUrl').value;
    if (!url) return;
    navigator.clipboard.writeText(url).then(() => {
        showToast('✅ 链接已复制到剪贴板');
    }).catch(() => {
        $('extPubPublishedUrl').select();
        document.execCommand('copy');
        showToast('✅ 链接已复制');
    });
}

function openExtPubUrl() {
    const url = $('extPubPublishedUrl').value;
    if (url) window.open(url, '_blank');
}


// ==================== 协作功能 ====================

async function checkAuth() {
    try {
        const res = await fetch('/api/auth/me');
        const data = await res.json();
        if (data.user) {
            currentUser = data.user;
            userTeams = data.teams || [];
        } else {
            currentUser = null;
            userTeams = [];
        }
    } catch (e) {
        // 未登录或网络错误，静默处理
        currentUser = null;
        userTeams = [];
    }
    updateUserUI();
}

function updateUserUI() {
    const btn = $('userMenuBtn');
    if (currentUser && btn) {
        const initial = (currentUser.displayName || currentUser.username).charAt(0).toUpperCase();
        btn.textContent = initial;
    } else if (btn) {
        btn.innerHTML = HomeUI.icon('user');
    }
    if ($('userDisplayName')) $('userDisplayName').textContent = currentUser ? currentUser.displayName : '离线个人版';
    if ($('userUsername')) $('userUsername').textContent = currentUser ? '@' + currentUser.username : '本地项目无需登录';
    if ($('loginMenuBtn')) $('loginMenuBtn').classList.toggle('hidden', !!currentUser);
    if ($('teamManagerMenuBtn')) $('teamManagerMenuBtn').classList.toggle('hidden', !currentUser);
    if ($('logoutMenuBtn')) $('logoutMenuBtn').classList.toggle('hidden', !currentUser);
    updateTeamSelector();
}

function updateTeamSelector() {
    const sel = $('teamSelect');
    if (!sel) return;
    sel.innerHTML = '<option value="">请选择团队</option>' +
        userTeams.map(t => `<option value="${t.id}" ${t.id == selectedTeamId ? 'selected' : ''}>${t.name}</option>`).join('');
}

function toggleUserMenu() {
    const dd = $('userDropdown');
    dd.classList.toggle('hidden');
    // 点击外部关闭
    setTimeout(() => {
        const handler = (e) => {
            if (!$('userMenuContainer').contains(e.target)) {
                dd.classList.add('hidden');
                document.removeEventListener('click', handler);
            }
        };
        document.addEventListener('click', handler);
    }, 0);
}

async function handleLogout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.href = '/src/';
}

function redirectToLoginForTeam() {
    window.location.href = '/src/login.html?next=' + encodeURIComponent('/src/?tab=team');
}

async function requireTeamLogin(actionText = '使用团队版') {
    if (currentUser) return true;
    const shouldLogin = await showAppConfirm({
        title: '登录团队版',
        message: `${actionText}需要先登录。\n登录后会自动把当前本地个人项目导入账号，并与离线个人版保持同步。`,
        confirmText: '去登录',
        cancelText: '继续离线使用',
        tone: 'info'
    });
    if (shouldLogin) {
        redirectToLoginForTeam();
    }
    return false;
}

// ==================== 项目来源切换（本地原型 / AI 项目） ====================
const SOURCE_TAB_ACTIVE = 'source-tab is-active';
const SOURCE_TAB_IDLE = 'source-tab';

function switchProjectSource(source) {
    if (source !== 'ai') source = 'local';
    try { localStorage.setItem('prototype-home-source', source); } catch (_) { /* 忽略存储异常 */ }
    const isLocal = source === 'local';
    const tabLocal = $('tabSourceLocal'), tabAi = $('tabSourceAi');
    HomeUI.closeMenu();
    tabLocal.className = (isLocal ? SOURCE_TAB_ACTIVE : SOURCE_TAB_IDLE);
    tabAi.className = (isLocal ? SOURCE_TAB_IDLE : SOURCE_TAB_ACTIVE);
    tabLocal.setAttribute('aria-selected', String(isLocal));
    tabAi.setAttribute('aria-selected', String(!isLocal));
    tabLocal.tabIndex = isLocal ? 0 : -1; tabAi.tabIndex = isLocal ? -1 : 0;
    $('sourceLocalPane').classList.toggle('hidden', !isLocal);
    const aiPane = $('sourceAiPane');
    aiPane.classList.toggle('hidden', isLocal);
    HomeUI.updateCounts(isLocal ? 'local' : 'ai', null, null);
    if (isLocal) loadExternalProjects(); else loadProjects();
}

async function switchProjectTab(tab) {
    if (tab === 'team' && !(await requireTeamLogin('切换到团队版'))) {
        return;
    }

    currentTab = tab;
    const tabMy = $('tabMy');
    const tabTeam = $('tabTeam');
    const teamSel = $('teamSelector');

    if (tab === 'my') {
        tabMy.className = 'scope-tab is-active';
        tabTeam.className = 'scope-tab';
        teamSel.classList.add('hidden');
    } else {
        tabTeam.className = 'scope-tab is-active';
        tabMy.className = 'scope-tab';
        teamSel.classList.remove('hidden');
    }
    loadProjects();
}

async function loadTeamProjects() {
    selectedTeamId = $('teamSelect')?.value || null;
    if (!selectedTeamId) {
        allProjects = []; HomeUI.updateCounts('ai', 0);
        HomeUI.empty($('projectList'), '选择一个团队', '选择团队后查看共享项目。', null, null, 'share');
        return;
    }
    try {
        const response = await fetch(`/api/projects/team?teamId=${encodeURIComponent(selectedTeamId)}&t=${Date.now()}`);
        if (!response.ok) throw new Error('无法读取团队项目。');
        const data = await response.json(); allProjects = data.projects || []; renderProjectList();
    } catch (error) { HomeUI.empty($('projectList'), '项目读取失败', error.message, '重试', loadTeamProjects, 'error'); }
}

// ==================== 团队管理 ====================

async function openTeamManager() {
    if (!(await requireTeamLogin('管理团队'))) return;
    $('userDropdown').classList.add('hidden');
    $('teamManagerModal').classList.remove('hidden');
    $('teamManagerModal').classList.add('flex');
    $('createTeamForm').classList.add('hidden');
    $('joinTeamForm').classList.add('hidden');
    renderTeamList();
}

function closeTeamManager() {
    $('teamManagerModal').classList.add('hidden');
    $('teamManagerModal').classList.remove('flex');
}

function showCreateTeam() {
    $('createTeamForm').classList.toggle('hidden');
    $('joinTeamForm').classList.add('hidden');
}

function showJoinTeam() {
    $('joinTeamForm').classList.toggle('hidden');
    $('createTeamForm').classList.add('hidden');
}

async function createTeam() {
    const name = $('newTeamName').value.trim();
    if (!name) return;
    try {
        const res = await fetch('/api/teams/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        const data = await res.json();
        if (data.success) {
            showToast('团队创建成功！邀请码: ' + data.team.inviteCode);
            $('newTeamName').value = '';
            $('createTeamForm').classList.add('hidden');
            await refreshTeams();
            renderTeamList();
        } else {
            showToast(data.error || '创建失败', 'error');
        }
    } catch (e) {
        showToast('网络错误', 'error');
    }
}

async function joinTeam() {
    const code = $('inviteCodeInput').value.trim();
    if (!code) return;
    try {
        const res = await fetch('/api/teams/join', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ inviteCode: code })
        });
        const data = await res.json();
        if (data.success) {
            showToast('成功加入团队: ' + data.team.name);
            $('inviteCodeInput').value = '';
            $('joinTeamForm').classList.add('hidden');
            await refreshTeams();
            renderTeamList();
        } else {
            showToast(data.error || '加入失败', 'error');
        }
    } catch (e) {
        showToast('网络错误', 'error');
    }
}

async function refreshTeams() {
    try {
        const res = await fetch('/api/teams');
        const data = await res.json();
        userTeams = data.teams || [];
        updateTeamSelector();
    } catch (e) { /* ignore */ }
}

async function renderTeamList() {
    const container = $('teamList');
    if (userTeams.length === 0) {
        container.innerHTML = '<div class="text-center text-sm text-gray-400 py-4">你还没有加入任何团队</div>';
        return;
    }
    container.innerHTML = userTeams.map(t => `
        <div class="bg-gray-50 rounded-xl p-4">
            <div class="flex items-center justify-between mb-2">
                <div>
                    <h4 class="text-sm font-semibold text-gray-800">${t.name}</h4>
                    <span class="text-[11px] px-1.5 py-0.5 rounded ${t.role === 'admin' ? 'bg-indigo-100 text-indigo-600' : 'bg-gray-200 text-gray-600'}">${t.role === 'admin' ? '管理员' : '成员'}</span>
                </div>
                <button onclick="leaveTeam(${t.id}, '${t.name.replace(/'/g, "\\'")}')" class="text-xs text-red-400 hover:text-red-600 transition">退出</button>
            </div>
            <div class="flex items-center gap-2 mt-2">
                <span class="text-xs text-gray-400">邀请码:</span>
                <code class="text-xs bg-white px-2 py-1 rounded border border-gray-200 font-mono tracking-widest">${t.inviteCode}</code>
                <button onclick="navigator.clipboard.writeText('${t.inviteCode}');showToast('邀请码已复制')" class="text-xs text-indigo-500 hover:text-indigo-700">
                    <i class="fas fa-copy"></i>
                </button>
            </div>
            <button onclick="viewTeamMembers(${t.id})" class="mt-2 text-xs text-gray-500 hover:text-indigo-600 flex items-center gap-1">
                <i class="fas fa-users"></i> 查看成员
            </button>
            <div id="teamMembers_${t.id}" class="hidden mt-2"></div>
        </div>
    `).join('');
}

async function viewTeamMembers(teamId) {
    const container = $('teamMembers_' + teamId);
    if (!container.classList.contains('hidden')) {
        container.classList.add('hidden');
        return;
    }
    container.innerHTML = '<div class="text-xs text-gray-400">加载中...</div>';
    container.classList.remove('hidden');
    try {
        const res = await fetch(`/api/teams/${teamId}/members`);
        const data = await res.json();
        const members = data.members || [];
        container.innerHTML = members.map(m => `
            <div class="flex items-center justify-between py-1.5 text-xs">
                <span class="text-gray-700">${m.display_name} <span class="text-gray-400">@${m.username}</span></span>
                <span class="${m.role === 'admin' ? 'text-indigo-500' : 'text-gray-400'}">${m.role === 'admin' ? '管理员' : '成员'}</span>
            </div>
        `).join('');
    } catch (e) {
        container.innerHTML = '<div class="text-xs text-red-400">加载失败</div>';
    }
}

async function leaveTeam(teamId, name) {
    const confirmed = await showAppConfirm({
        title: '退出团队',
        message: `确定要退出团队「${name}」吗？`,
        confirmText: '退出团队',
        tone: 'danger'
    });
    if (!confirmed) return;
    try {
        const res = await fetch(`/api/teams/${teamId}/leave`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast('已退出团队');
            await refreshTeams();
            renderTeamList();
        } else {
            showToast(data.error || '操作失败', 'error');
        }
    } catch (e) {
        showToast('网络错误', 'error');
    }
}

// ==================== 项目分享 ====================

async function openShareModal(projectId) {
    if (!(await requireTeamLogin('分享项目到团队'))) return;
    $('shareProjectId').value = projectId;
    $('shareProjectModal').classList.remove('hidden');
    $('shareProjectModal').classList.add('flex');

    const container = $('shareTeamList');
    container.innerHTML = '<div class="text-center text-sm text-gray-400 py-4">加载中...</div>';

    try {
        // 获取已分享的团队
        const sharedRes = await fetch(`/api/projects/${encodeURIComponent(projectId)}/shared-teams`, { method: 'POST' });
        const sharedData = await sharedRes.json();
        const sharedTeamIds = new Set((sharedData.teams || []).map(t => t.id));

        if (userTeams.length === 0) {
            container.innerHTML = '<div class="text-center text-sm text-gray-400 py-4">你还没有加入任何团队</div>';
            return;
        }

        container.innerHTML = userTeams.map(t => {
            const isShared = sharedTeamIds.has(t.id);
            return `
                <div class="flex items-center justify-between py-2.5 px-3 rounded-lg ${isShared ? 'bg-green-50' : 'bg-gray-50'}">
                    <span class="text-sm text-gray-700">${t.name}</span>
                    ${isShared ?
                        `<button onclick="unshareProject('${projectId}', ${t.id}, this)" class="text-xs px-3 py-1.5 bg-red-50 text-red-500 rounded-lg hover:bg-red-100 transition">取消分享</button>` :
                        `<button onclick="shareProject('${projectId}', ${t.id}, this)" class="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition">分享</button>`
                    }
                </div>
            `;
        }).join('');
    } catch (e) {
        container.innerHTML = '<div class="text-center text-sm text-red-400 py-4">加载失败</div>';
    }
}

function closeShareModal() {
    $('shareProjectModal').classList.add('hidden');
    $('shareProjectModal').classList.remove('flex');
}

async function shareProject(projectId, teamId, btn) {
    btn.disabled = true;
    btn.textContent = '分享中...';
    try {
        const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/share`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ teamId })
        });
        const data = await res.json();
        if (data.success) {
            showToast('已分享到团队');
            openShareModal(projectId); // 刷新
        } else {
            showToast(data.error || '分享失败', 'error');
            btn.disabled = false;
            btn.textContent = '分享';
        }
    } catch (e) {
        showToast('网络错误', 'error');
        btn.disabled = false;
        btn.textContent = '分享';
    }
}

async function unshareProject(projectId, teamId, btn) {
    btn.disabled = true;
    btn.textContent = '取消中...';
    try {
        const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/unshare`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ teamId })
        });
        const data = await res.json();
        if (data.success) {
            showToast('已取消分享');
            openShareModal(projectId); // 刷新
        } else {
            showToast(data.error || '取消失败', 'error');
            btn.disabled = false;
            btn.textContent = '取消分享';
        }
    } catch (e) {
        showToast('网络错误', 'error');
        btn.disabled = false;
        btn.textContent = '取消分享';
    }
}

// ==================== GitHub 配置引导 ====================

function openGithubSetup() {
    // 预加载已有配置
    fetch('/api/github/config').then(r => r.json()).then(data => {
        if (data.success) {
            $('setupUsername').value = data.username || '';
            $('setupRepo').value = data.repo || 'my-prototypes';
            $('setupToken').value = ''; // Token 不回显，保持空
            if (data.tokenMasked) {
                $('setupToken').placeholder = data.tokenMasked + ' （不修改则留空）';
            }
        }
    }).catch(() => { });

    $('githubTestResult').classList.add('hidden');
    $('githubSetupModal').classList.remove('hidden');
    $('githubSetupModal').classList.add('flex');
}

function closeGithubSetup() {
    $('githubSetupModal').classList.add('hidden');
    $('githubSetupModal').classList.remove('flex');
}

async function testGithubConnection() {
    const token = $('setupToken').value.trim();
    const btn = $('testConnBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 验证中...';

    try {
        const resp = await fetch('/api/github/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token })
        });
        const data = await resp.json();
        const resultEl = $('githubTestResult');
        resultEl.classList.remove('hidden', 'bg-green-50', 'text-green-700', 'bg-red-50', 'text-red-700');

        if (data.success) {
            resultEl.classList.add('bg-green-50', 'text-green-700');
            resultEl.textContent = data.message;
            // 自动填充用户名
            if (data.username && !$('setupUsername').value) {
                $('setupUsername').value = data.username;
            }
        } else {
            resultEl.classList.add('bg-red-50', 'text-red-700');
            resultEl.textContent = data.message || data.error || '验证失败';
        }
    } catch (e) {
        const resultEl = $('githubTestResult');
        resultEl.classList.remove('hidden');
        resultEl.classList.add('bg-red-50', 'text-red-700');
        resultEl.textContent = '连接失败: ' + e.message;
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-plug"></i> 测试连接';
    }
}

async function saveGithubConfig() {
    const token = $('setupToken').value.trim();
    const username = $('setupUsername').value.trim();
    const repo = ($('setupRepo').value.trim()) || 'my-prototypes';

    if (!username) {
        showToast('请填写 GitHub 用户名', 'error');
        return;
    }

    const btn = $('saveGithubBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 保存中...';

    try {
        const resp = await fetch('/api/github/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token, username, repo })
        });
        const data = await resp.json();

        if (data.success) {
            showToast('✅ GitHub 配置已保存');
            closeGithubSetup();
            // 刷新导出弹窗的 GitHub 状态
            if (currentExtPubId && !$('extPublishModal').classList.contains('hidden')) {
                await loadExtPubStatus();
            }
        } else {
            showToast('保存失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-save"></i> 保存配置';
    }
}
