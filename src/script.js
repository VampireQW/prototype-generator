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
    // 检查登录状态
    await checkAuth();
    setupEventListeners();
    await Promise.all([loadModels(), loadDesignSystems(), loadSkills()]);
    addPage(); // 默认添加一个页面

    const params = new URLSearchParams(window.location.search);
    if (params.get('tab') === 'team' && currentUser) {
        await switchProjectTab('team');
    } else {
        loadProjects();
    }
});

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

    // 复制Prompt
    $('copyPromptBtn').onclick = copyPromptToClipboard;

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
        $('primaryColorValue').textContent = e.target.value;
        if (!$('designSystemSelect')?.value) updateDesignSystemHint();
    };
    $('secondaryColor').oninput = (e) => {
        $('secondaryColorValue').textContent = e.target.value;
        if (!$('designSystemSelect')?.value) updateDesignSystemHint();
    };
    if ($('backgroundMode')) {
        $('backgroundMode').onchange = () => {
            if (!$('designSystemSelect')?.value) updateDesignSystemHint();
        };
    }

    // 搜索
    $('projectSearch').oninput = (e) => {
        searchQuery = e.target.value.toLowerCase();
        renderProjectList();
    };

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
    $('primaryColor').value = '#004fff';
    $('primaryColorValue').textContent = '#004fff';
    $('secondaryColor').value = '#10B981';
    $('secondaryColorValue').textContent = '#10B981';
    $('backgroundMode').value = 'light';
    $('componentStyle').value = 'Ant Design';
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

    $('headerTitle').textContent = '请输入您的设计灵感';
    currentRecordProject = null;

    // 清空增量更新状态
    sourceProjectId = null;
    originalFormData = null;
    originalImageHashes = {};
}

function loadProjects() {
    if (!currentUser) {
        // 未登录，用原始接口
        fetch('/data/projects.json?t=' + Date.now())
            .then(res => res.json())
            .then(data => {
                allProjects = data || [];
                renderProjectList();
            })
            .catch(() => {
                $('projectList').innerHTML = '<div class="text-center py-8 text-gray-400 text-sm">暂无项目</div>';
            });
        return;
    }

    if (currentTab === 'my') {
        fetch('/api/projects/my?t=' + Date.now())
            .then(res => res.json())
            .then(data => {
                allProjects = data.projects || [];
                renderProjectList();
            })
            .catch(() => {
                $('projectList').innerHTML = '<div class="text-center py-8 text-gray-400 text-sm">暂无项目</div>';
            });
    } else if (currentTab === 'team' && selectedTeamId) {
        loadTeamProjects();
    } else {
        $('projectList').innerHTML = '<div class="text-center py-8 text-gray-400 text-sm">请选择团队</div>';
    }
}

function renderProjectList() {
    const container = $('projectList');
    let filtered = allProjects;

    if (searchQuery) {
        filtered = allProjects.filter(p => p.name.toLowerCase().includes(searchQuery));
    }

    if (filtered.length === 0) {
        container.innerHTML = '<div class="text-center py-8 text-gray-400 text-sm">暂无项目</div>';
        return;
    }

    container.innerHTML = filtered.map(p => {
        // 状态标签
        let statusHTML = '';
        if (p.status === 'generating') {
            statusHTML = `
                <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-600 animate-pulse">
                    <i class="fas fa-spinner fa-spin text-[10px]"></i>生成中
                </span>`;
        } else if (p.status === 'failed') {
            statusHTML = `
                <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-500">
                    <i class="fas fa-times-circle text-[10px]"></i>失败
                </span>`;
        } else if (p.status === 'pending_external') {
            statusHTML = `
                <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-600">
                    <i class="fas fa-clock text-[10px]"></i>待生成
                </span>`;
        } else {
            statusHTML = `
                <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-600">
                    <i class="fas fa-check-circle text-[10px]"></i>已完成
                </span>`;
        }

        const safeName = p.name.replace(/'/g, "\\'").replace(/"/g, '&quot;');
        const ownerHTML = p.ownerName ? `<p class="text-[11px] text-purple-400 mt-0.5 flex items-center gap-1"><i class="fas fa-user text-[9px]"></i>${p.ownerName}</p>` : '';

        return `
        <div class="project-card group bg-white border border-gray-200 rounded-xl overflow-hidden hover:shadow-md hover:border-indigo-200 transition-all duration-200 cursor-pointer"
             onclick="window.open('viewer.html?project=${encodeURIComponent(p.id)}', '_blank')">
            <div class="p-3.5">
                <div class="flex items-start justify-between gap-2 mb-2">
                    <p class="text-sm font-semibold text-gray-800 line-clamp-2 leading-snug flex-1" title="${p.name}">${p.name}</p>
                    ${statusHTML}
                </div>
                <p class="text-xs text-gray-400">${p.date}</p>
                ${p.model_name ? `<p class="text-[11px] text-indigo-400 mt-0.5 flex items-center gap-1"><i class="fas fa-robot text-[9px]"></i>${p.model_name}</p>` : ''}
                ${ownerHTML}
            </div>
            <div class="flex items-center border-t border-gray-100 bg-gray-50/50 px-2 py-1.5 transition-opacity duration-150"
                 onclick="event.stopPropagation()">
                <button onclick="editProjectTitle('${p.id}', '${safeName}')"
                        class="flex-1 flex items-center justify-center gap-1 py-1 text-xs text-gray-400 hover:text-blue-600 rounded hover:bg-blue-50 transition-colors" title="编辑">
                    <i class="fas fa-edit"></i>
                </button>
                <button onclick="copyProject('${p.id}', '${safeName}')"
                        class="flex-1 flex items-center justify-center gap-1 py-1 text-xs text-gray-400 hover:text-purple-600 rounded hover:bg-purple-50 transition-colors" title="复制">
                    <i class="fas fa-copy"></i>
                </button>
                <button onclick="window.open('viewer.html?project=${encodeURIComponent(p.id)}', '_blank')"
                        class="flex-1 flex items-center justify-center gap-1 py-1 text-xs text-gray-400 hover:text-indigo-600 rounded hover:bg-indigo-50 transition-colors" title="预览">
                    <i class="fas fa-eye"></i>
                </button>
                <button onclick="viewRecord('${p.id}')"
                        class="flex-1 flex items-center justify-center gap-1 py-1 text-xs text-gray-400 hover:text-green-600 rounded hover:bg-green-50 transition-colors" title="记录">
                    <i class="fas fa-history"></i>
                </button>
                <button onclick="openExportModal('${p.id}', '${safeName}')"
                        class="flex-1 flex items-center justify-center gap-1 py-1 text-xs text-gray-400 hover:text-orange-500 rounded hover:bg-orange-50 transition-colors" title="导出 & 分享">
                    <i class="fas fa-paper-plane"></i>
                </button>
                ${currentUser && currentTab === 'my' ? `<button onclick="openShareModal('${p.id}')"
                        class="flex-1 flex items-center justify-center gap-1 py-1 text-xs text-gray-400 hover:text-cyan-600 rounded hover:bg-cyan-50 transition-colors" title="分享到团队">
                    <i class="fas fa-share-alt"></i>
                </button>` : ''}
                <button onclick="deleteProject('${p.id}', '${safeName}')"
                        class="flex-1 flex items-center justify-center gap-1 py-1 text-xs text-gray-400 hover:text-red-500 rounded hover:bg-red-50 transition-colors" title="删除">
                    <i class="fas fa-trash-alt"></i>
                </button>
            </div>
        </div>
    `;
    }).join('');
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

    // 全局设置
    let html = `
        <div class="mb-6">
            <h4 class="font-bold text-gray-700 mb-3 flex items-center gap-2">
                <i class="fas fa-palette text-indigo-500"></i> 全局设置
            </h4>
            <div class="grid grid-cols-2 gap-3 text-sm">
                <div class="flex items-center gap-2">
                    <span class="text-gray-500">主色调:</span>
                    <span class="w-5 h-5 rounded" style="background:${record.global?.primaryColor || '#004fff'}"></span>
                    <span class="font-mono">${record.global?.primaryColor || '#004fff'}</span>
                </div>
                <div class="flex items-center gap-2">
                    <span class="text-gray-500">强调色:</span>
                    <span class="w-5 h-5 rounded" style="background:${record.global?.secondaryColor || '#10B981'}"></span>
                    <span class="font-mono">${record.global?.secondaryColor || '#10B981'}</span>
                </div>
                <div><span class="text-gray-500">背景模式:</span> ${record.global?.backgroundMode || 'light'}</div>
                <div><span class="text-gray-500">组件风格:</span> ${record.global?.componentStyle || 'Ant Design'}</div>
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
        $('primaryColor').value = record.global.primaryColor || '#004fff';
        $('primaryColorValue').textContent = record.global.primaryColor || '#004fff';
        $('secondaryColor').value = record.global.secondaryColor || '#10B981';
        $('secondaryColorValue').textContent = record.global.secondaryColor || '#10B981';
        $('backgroundMode').value = record.global.backgroundMode || 'light';
        $('componentStyle').value = record.global.componentStyle || 'Ant Design';
        if ($('designSystemSelect')) $('designSystemSelect').value = record.global.designSystemId || record.designSystemId || '';
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
            div.className = 'bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden';
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

    $('headerTitle').textContent = '已加载历史记录 - 可修改后重新生成（支持增量更新）';
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
    div.className = 'bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden';
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
    handleFiles(id, imageFiles);
    showToast(`已粘贴 ${imageFiles.length} 张参考图`);
    return true;
}

function handleGlobalReferencePaste(event) {
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
            categoryLabel: '使用当前主题色',
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
    return [
        $('primaryColor') ? $('primaryColor').value : '#004fff',
        $('secondaryColor') ? $('secondaryColor').value : '#10b981',
        $('backgroundMode') && $('backgroundMode').value === 'dark' ? '#111827' : '#f8fafc',
        '#ffffff',
        '#111827',
        '#e5e7eb'
    ];
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
    if (!id) {
        if (hint) hint.dataset.help = '未选择时使用表单里的主题色、辅助色和组件风格作为主要视觉约束。';
        renderDesignSystemSwatches({ colors: getDefaultSwatchColors() });
        updateDesignSystemPickerButton(null);
        return;
    }
    if (hint) hint.dataset.help = '已选择设计系统：品牌色彩、字体和组件语言优先；主题色/辅助色只作为微调偏好。';
    const ds = designSystemsList.find(item => item.id === id) || null;
    renderDesignSystemSwatches(ds);
    updateDesignSystemPickerButton(ds);
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
    if (label) label.textContent = getDesignSystemUiLabel(ds);
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
function generatePrompt() {
    const global = {
        primaryColor: $('primaryColor').value,
        secondaryColor: $('secondaryColor').value,
        backgroundMode: $('backgroundMode').value,
        componentStyle: $('componentStyle').value,
        designSystemId: $('designSystemSelect') ? $('designSystemSelect').value : '',
        designSystemName: getSelectedDesignSystemName(),
        skillId: $('skillSelect') ? $('skillSelect').value : 'web-prototype',
        skillName: getSelectedSkillName()
    };
    const mode = SKILL_INPUT_MODES[global.skillId] || SKILL_INPUT_MODES['web-prototype'];
    const isPpt = global.skillId === 'html-ppt';
    const compactPpt = isPpt && pptInputMode === 'import';
    const productNoun = isPpt ? 'HTML 演示文稿' : 'HTML 原型页面';

    let prompt = `你是专业的前端工程师和UI/UX设计师。
请生成一个高保真的${productNoun}。

# 技术栈
- Tailwind CSS (CDN)
- Vue 3 (CDN, 可选)
- FontAwesome (CDN)
- ECharts (如需图表)
- Google Fonts (Inter)

# 全局设计规范
- 主色: ${global.primaryColor}
- 强调色: ${global.secondaryColor}
- 背景模式: ${global.backgroundMode === 'light' ? '浅色' : '深色'}
- 组件风格: ${global.componentStyle}
- 设计系统: ${global.designSystemName}
- 产物类型: ${global.skillName}
- 约束优先级: 用户明确需求 > 设计系统 > 产物类型工作流 > craft 规则 > 主色/强调色/组件风格
- 如果选择了具体设计系统，主色和强调色只作为微调偏好，不要覆盖该设计系统的核心品牌色、字体和组件语言
- 圆角: 0.5rem
- 阴影: 使用柔和现代的阴影

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
            prompt += `**参考图**: 已附加${referenceImages.length}张额外参考图。`;
            if (isPpt) {
                prompt += `仅用于辅助整体视觉风格判断，不替代 PPT 原始配图，也不要按参考图相似度还原。\n`;
            } else {
                if (similarity === 'pixel') {
                    prompt += `请尽可能像素级还原。\n`;
                } else if (similarity === 'style') {
                    prompt += `请参考其视觉风格。\n`;
                } else {
                    prompt += `请参考其布局结构。\n`;
                }
            }
        }
    });

    prompt += `
# 输出要求（重要！）

请输出一个**完整的、独立的HTML文件**。

要求：
1. 所有CSS放在<style>标签中
2. 所有JS放在<script>标签中
3. 使用真实的示例数据（不要Lorem ipsum）
4. 响应式设计
5. 直接可在浏览器中打开使用

输出格式：
\`\`\`html
<!DOCTYPE html>
<html lang="zh-CN">
...完整代码...
</html>
\`\`\`
`;

    return prompt;
}

// 收集用户输入数据用于保存记录
function collectFormData() {
    const global = {
        primaryColor: $('primaryColor').value,
        secondaryColor: $('secondaryColor').value,
        backgroundMode: $('backgroundMode').value,
        componentStyle: $('componentStyle').value,
        designSystemId: $('designSystemSelect') ? $('designSystemSelect').value : '',
        designSystemName: getSelectedDesignSystemName(),
        skillId: $('skillSelect') ? $('skillSelect').value : 'web-prototype',
        skillName: getSelectedSkillName()
    };

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
    const explicitName = pages.map(id => $(`pageName_${id}`)?.value).filter(Boolean).join(' + ');
    if (explicitName) return explicitName;

    const skillId = $('skillSelect') ? $('skillSelect').value : 'web-prototype';
    if (skillId === 'html-ppt') {
        const firstLayout = pages.map(id => $(`layout_${id}`)?.value?.trim()).find(Boolean);
        if (firstLayout) {
            return firstLayout.split('\n')[0].slice(0, 24) || 'HTML PPT';
        }
        return 'HTML PPT';
    }

    return '未命名项目';
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

    // 检查全局配置是否被修改过（这些有默认值，检查是否与默认值不同）
    const globalChanged = (
        $('primaryColor').value !== '#004fff' ||
        $('secondaryColor').value !== '#10b981' ||
        $('backgroundMode').value !== 'light' ||
        $('componentStyle').value !== 'Ant Design'
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
    if (JSON.stringify(original.global) !== JSON.stringify(current.global)) {
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

    // 项目名称
    const projectName = getProjectNameFromForm();

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
            showToast('🔵 已开始生成 "' + result.project.name + '"，请查看左侧列表');

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

    const prompt = generatePrompt();
    const formData = collectFormData();
    const projectName = getProjectNameFromForm();

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
                imageFiles
            })
        });

        const result = await response.json();
        if (result.success && result.project) {
            // 添加到列表
            allProjects.unshift(result.project);
            renderProjectList();

            // 占位项目创建成功后，再复制prompt
            await navigator.clipboard.writeText(fullPrompt);
            showToast('✅ Prompt已复制！粘贴到Antigravity/Cursor等工具中使用');
        } else {
            showToast('占位项目创建失败', 'error');
        }
    } catch (err) {
        console.error('操作失败:', err);
        showToast('操作失败: ' + err.message, 'error');
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
        <div class="flex items-center gap-3 p-3 rounded-lg border ${m.id === editingId ? 'border-indigo-300 bg-indigo-50/70 ring-1 ring-indigo-200' : m.id === selectedModelId ? 'border-indigo-200 bg-indigo-50/50' : 'border-gray-100 bg-white'} hover:border-indigo-200 transition cursor-pointer"
             onclick="editModel('${m.id}')">
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                    <span class="font-medium text-sm text-gray-900 truncate">${m.name}</span>
                    ${m.id === selectedModelId ? '<span class="text-xs bg-indigo-100 text-indigo-600 px-1.5 py-0.5 rounded">当前</span>' : ''}
                    ${m.multimodal ? '<span class="text-xs bg-purple-50 text-purple-600 px-1.5 py-0.5 rounded">多模态</span>' : ''}
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


// ==================== 导出 & 分享弹窗 ====================

let currentExportProjectId = '';
let currentExportProjectName = '';
let currentExportMode = 'preview';

async function openExportModal(id, name) {
    currentExportProjectId = id;
    currentExportProjectName = name;
    currentExportMode = 'preview';

    // 重置 UI
    selectExportMode('preview');
    $('exportModalProjectName').textContent = name;
    $('githubPublishedInfo').classList.add('hidden');
    $('githubNotConfigured').classList.add('hidden');
    $('githubConfigured').classList.add('hidden');
    if ($('githubUnpublishBtn')) $('githubUnpublishBtn').classList.add('hidden');
    if ($('githubPublishBtnText')) $('githubPublishBtnText').textContent = '立即发布';

    // 显示弹窗
    $('exportModal').classList.remove('hidden');
    $('exportModal').classList.add('flex');

    // 加载 GitHub 配置状态
    await loadGithubStatus(id);
}

function closeExportModal() {
    $('exportModal').classList.add('hidden');
    $('exportModal').classList.remove('flex');
}

function selectExportMode(mode) {
    currentExportMode = mode;
    ['preview', 'dev', 'embedded'].forEach(m => {
        const btn = $(`exportMode${m.charAt(0).toUpperCase() + m.slice(1)}`);
        if (btn) btn.classList.toggle('active', m === mode);
    });
}

async function doLocalExport() {
    const btn = $('localExportBtn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 导出中...';
    btn.disabled = true;

    try {
        const resp = await fetch('/api/export', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ projectId: currentExportProjectId, mode: currentExportMode })
        });
        const data = await resp.json();
        if (data.success) {
            showToast(`✅ 导出完成，已打开文件夹`);
        } else {
            showToast('导出失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        showToast('导出失败: ' + e.message, 'error');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

async function loadGithubStatus(projectId) {
    try {
        const resp = await fetch('/api/github/config');
        const data = await resp.json();

        if (!data.success || !data.hasToken || !data.username) {
            $('githubNotConfigured').classList.remove('hidden');
            return;
        }

        $('githubConfigured').classList.remove('hidden');
        $('githubRepoDisplay').textContent = `${data.username}/${data.repo}`;

        // 检查项目是否已发布（从 record.json 读取）
        try {
            const recResp = await fetch(`/projects/${projectId}/record.json?t=${Date.now()}`);
            if (recResp.ok) {
                const record = await recResp.json();
                if (record.github_url) {
                    $('githubPublishedUrl').value = record.github_url;
                    $('githubPublishedAt').textContent = record.github_published_at || '';
                    $('githubPublishedInfo').classList.remove('hidden');
                    $('githubPublishBtnText').textContent = '重新发布 / 更新';
                    if ($('githubUnpublishBtn')) $('githubUnpublishBtn').classList.remove('hidden');

                    // 如果有记录的模式，尝试恢复选中状态
                    if (record.github_publish_mode) {
                        const radio = document.querySelector(`input[name="githubPublishMode"][value="${record.github_publish_mode}"]`);
                        if (radio) radio.checked = true;
                    }
                }
            }
        } catch (_) { }

    } catch (e) {
        $('githubNotConfigured').classList.remove('hidden');
    }
}

async function doGitHubPublish() {
    const btn = $('githubPublishBtn');
    const btnText = $('githubPublishBtnText');
    const originalText = btnText ? btnText.textContent : '立即发布';
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> <span>发布中，请稍候...</span>';

    let finalText = originalText;

    const modeRadio = document.querySelector('input[name="githubPublishMode"]:checked');
    const publishMode = modeRadio ? modeRadio.value : 'preview';

    try {
        const resp = await fetch('/api/github/publish', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ projectId: currentExportProjectId, mode: publishMode })
        });
        const data = await resp.json();

        if (data.success) {
            $('githubPublishedUrl').value = data.url;
            $('githubPublishedAt').textContent = '刚刚';
            $('githubPublishedInfo').classList.remove('hidden');
            finalText = '重新发布 / 更新';
            if ($('githubUnpublishBtn')) $('githubUnpublishBtn').classList.remove('hidden');
            showToast('🚀 发布成功！约 1-3 分钟后链接生效');
        } else {
            showToast('发布失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        showToast('发布失败: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fab fa-github"></i> <span id="githubPublishBtnText">${finalText}</span>`;
    }
}

function doGitHubUnpublish() {
    $('unpublishConfirmModal').classList.remove('hidden');
    $('unpublishConfirmModal').classList.add('flex');
}

function closeUnpublishConfirmModal() {
    $('unpublishConfirmModal').classList.add('hidden');
    $('unpublishConfirmModal').classList.remove('flex');
}

async function executeGitHubUnpublish() {
    const confirmBtn = $('confirmUnpublishBtn');
    const originalConfirmText = confirmBtn.innerHTML;
    confirmBtn.disabled = true;
    confirmBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 取消中...';

    const btn = $('githubUnpublishBtn');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 取消中...';

    try {
        const resp = await fetch('/api/github/unpublish', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ projectId: currentExportProjectId })
        });
        const data = await resp.json();

        if (data.success) {
            showToast('✅ 已取消发布并删除 GitHub 上的文件');
            // 更新 UI 状态
            $('githubPublishedInfo').classList.add('hidden');
            $('githubPublishBtnText').textContent = '立即发布';
            btn.classList.add('hidden');
            closeUnpublishConfirmModal(); // 成功后关闭确认弹窗
        } else {
            showToast('取消发布失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        showToast('请求失败: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
        confirmBtn.disabled = false;
        confirmBtn.innerHTML = originalConfirmText;
    }
}


function copyGithubUrl() {
    const url = $('githubPublishedUrl').value;
    if (!url) return;
    navigator.clipboard.writeText(url).then(() => {
        showToast('✅ 链接已复制到剪贴板');
    }).catch(() => {
        $('githubPublishedUrl').select();
        document.execCommand('copy');
        showToast('✅ 链接已复制');
    });
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
        btn.innerHTML = '<i class="fas fa-user"></i>';
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

async function switchProjectTab(tab) {
    if (tab === 'team' && !(await requireTeamLogin('切换到团队版'))) {
        return;
    }

    currentTab = tab;
    const tabMy = $('tabMy');
    const tabTeam = $('tabTeam');
    const teamSel = $('teamSelector');

    if (tab === 'my') {
        tabMy.className = 'flex-1 text-xs font-medium py-1.5 rounded-md transition-all bg-white text-gray-800 shadow-sm';
        tabTeam.className = 'flex-1 text-xs font-medium py-1.5 rounded-md transition-all text-gray-500 hover:text-gray-700';
        teamSel.classList.add('hidden');
    } else {
        tabTeam.className = 'flex-1 text-xs font-medium py-1.5 rounded-md transition-all bg-white text-gray-800 shadow-sm';
        tabMy.className = 'flex-1 text-xs font-medium py-1.5 rounded-md transition-all text-gray-500 hover:text-gray-700';
        teamSel.classList.remove('hidden');
    }
    loadProjects();
}

function loadTeamProjects() {
    const sel = $('teamSelect');
    selectedTeamId = sel ? sel.value : null;
    if (!selectedTeamId) {
        $('projectList').innerHTML = '<div class="text-center py-8 text-gray-400 text-sm">请选择团队</div>';
        return;
    }
    fetch(`/api/projects/team?teamId=${selectedTeamId}&t=${Date.now()}`)
        .then(res => res.json())
        .then(data => {
            allProjects = data.projects || [];
            renderProjectList();
        })
        .catch(() => {
            $('projectList').innerHTML = '<div class="text-center py-8 text-gray-400 text-sm">加载失败</div>';
        });
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

function openGithubUrl() {
    const url = $('githubPublishedUrl').value;
    if (url) window.open(url, '_blank');
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
            await loadGithubStatus(currentExportProjectId);
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
