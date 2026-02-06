/**
 * 原型生成器前端脚本
 * 简化版：AI调用在后端完成
 */

// ==================== 状态管理 ====================
let pages = [];
let pageFiles = {};
let allProjects = [];
let searchQuery = '';
let currentRecordProject = null; // 当前查看的记录项目

// ==================== 增量更新相关 ====================
let sourceProjectId = null;       // 来源项目ID（用于增量更新）
let originalFormData = null;      // 原始表单数据快照
let originalImageHashes = {};     // 原始图片哈希 { pageIndex: hash }

// ==================== DOM 元素 ====================
const $ = (id) => document.getElementById(id);

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    loadProjects();
    addPage(); // 默认添加一个页面
});

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

    // 颜色选择器
    $('primaryColor').oninput = (e) => $('primaryColorValue').textContent = e.target.value;
    $('secondaryColor').oninput = (e) => $('secondaryColorValue').textContent = e.target.value;

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

    // 清空页面
    pages = [];
    pageFiles = {};
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
    fetch('/data/projects.json?t=' + Date.now())
        .then(res => res.json())
        .then(data => {
            allProjects = data || [];
            renderProjectList();
        })
        .catch(() => {
            $('projectList').innerHTML = '<div class="text-center py-8 text-gray-400 text-sm">暂无项目</div>';
        });
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
        // 状态显示
        let statusHTML = '';
        if (p.status === 'generating') {
            statusHTML = `
                <div class="flex items-center gap-2 text-blue-600 text-xs mt-1 animate-pulse">
                    <i class="fas fa-spinner fa-spin"></i>
                    <span>生成中...</span>
                </div>
            `;
        } else if (p.status === 'failed') {
            statusHTML = `
                <div class="flex items-center gap-2 text-red-500 text-xs mt-1">
                    <i class="fas fa-exclamation-circle"></i>
                    <span>生成失败</span>
                </div>
            `;
        } else if (p.status === 'pending_external') {
            statusHTML = `
                <div class="flex items-center gap-2 text-amber-600 text-xs mt-1">
                    <i class="fas fa-clock"></i>
                    <span>待外部生成</span>
                </div>
            `;
        }

        return `
        <div class="group p-3 rounded-lg hover:bg-gray-50 transition-all">
            <div class="cursor-pointer" onclick="window.open('viewer.html?project=${encodeURIComponent(p.id)}', '_blank')">
                <p class="text-sm font-medium text-gray-900 line-clamp-2" title="${p.name}">${p.name}</p>
                <p class="text-xs text-gray-400 mt-1">${p.date}</p>
                ${statusHTML}
            </div>
            <div class="flex items-center gap-1 mt-2">
                <button onclick="event.stopPropagation(); editProjectTitle('${p.id}', '${p.name.replace(/'/g, "\\'").replace(/"/g, '&quot;')}')" 
                        class="p-1.5 text-gray-400 hover:text-blue-600 rounded hover:bg-blue-50" title="编辑标题">
                    <i class="fas fa-edit"></i>
                </button>
                <button onclick="event.stopPropagation(); copyProject('${p.id}', '${p.name.replace(/'/g, "\\'").replace(/"/g, '&quot;')}')" 
                        class="p-1.5 text-gray-400 hover:text-purple-600 rounded hover:bg-purple-50" title="复制项目">
                    <i class="fas fa-copy"></i>
                </button>
                <button onclick="event.stopPropagation(); window.open('viewer.html?project=${encodeURIComponent(p.id)}', '_blank')" 
                        class="p-1.5 text-gray-400 hover:text-indigo-600 rounded hover:bg-indigo-50" title="预览">
                    <i class="fas fa-eye"></i>
                </button>
                <button onclick="event.stopPropagation(); viewRecord('${p.id}')" 
                        class="p-1.5 text-gray-400 hover:text-green-600 rounded hover:bg-green-50" title="查看记录">
                    <i class="fas fa-history"></i>
                </button>
                <button onclick="event.stopPropagation(); deleteProject('${p.id}', '${p.name.replace(/'/g, "\\'").replace(/"/g, '&quot;')}')" 
                        class="p-1.5 text-gray-400 hover:text-red-500 rounded hover:bg-red-50" title="删除">
                    <i class="fas fa-trash-alt"></i>
                </button>
            </div>
        </div>
    `;
    }).join('');
}

function deleteProject(id, name) {
    if (!confirm(`确定要将 "${name}" 移到回收站吗？`)) return;

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
    const newName = prompt('请输入新项目名称:', name + ' - 副本');
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
    $('pageCardsContainer').innerHTML = '';

    // 恢复全局设置
    if (record.global) {
        $('primaryColor').value = record.global.primaryColor || '#004fff';
        $('primaryColorValue').textContent = record.global.primaryColor || '#004fff';
        $('secondaryColor').value = record.global.secondaryColor || '#10B981';
        $('secondaryColorValue').textContent = record.global.secondaryColor || '#10B981';
        $('backgroundMode').value = record.global.backgroundMode || 'light';
        $('componentStyle').value = record.global.componentStyle || 'Ant Design';
    }

    // 恢复页面
    if (record.pages && record.pages.length > 0) {
        for (const pageRecord of record.pages) {
            const id = Date.now().toString() + Math.random().toString(36).substr(2, 5);
            pages.push(id);
            pageFiles[id] = [];

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
            if (pageRecord.similarity) $(`similarity_${id}`).value = pageRecord.similarity;

            // 加载参考图片（从服务器）- 使用Promise确保等待完成
            if (pageRecord.images && pageRecord.images.length > 0) {
                const imageLoadPromises = pageRecord.images.map(imgName => {
                    return new Promise(async (resolve) => {
                        try {
                            const imgUrl = `/projects/${currentRecordProject.id}/reference/${imgName}`;
                            const response = await fetch(imgUrl);
                            const blob = await response.blob();
                            const reader = new FileReader();
                            reader.onload = (e) => {
                                pageFiles[id].push({
                                    name: imgName,
                                    base64: e.target.result
                                });
                                renderPreviews(id);
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
                // 等待该页面所有图片加载完成
                await Promise.all(imageLoadPromises);
            }
        }
    } else {
        addPage();
    }

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

    const index = pages.length;
    const html = createPageCardHtml(id, index);

    const div = document.createElement('div');
    div.id = `page-${id}`;
    div.className = 'bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden';
    div.innerHTML = html;

    $('pageCardsContainer').appendChild(div);
    setupPageListeners(id);
}

function createPageCardHtml(id, index) {
    return `
        <div class="border-b border-gray-200 px-6 py-4 bg-gray-50 flex justify-between items-center">
            <div class="flex items-center gap-3 flex-1">
                <span class="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center text-sm font-bold">${index}</span>
                <input type="text" id="pageName_${id}" class="flex-1 bg-transparent border-none focus:ring-0 font-bold text-lg placeholder-gray-400" placeholder="页面名称（如：首页、用户列表）">
            </div>
            <button onclick="removePage('${id}')" class="text-gray-400 hover:text-red-500 p-2" title="删除页面">
                <i class="fas fa-trash-alt"></i>
            </button>
        </div>
        
        <div class="p-6 space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <!-- 布局描述 -->
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">布局描述</label>
                    <textarea id="layout_${id}" rows="4" class="w-full rounded-lg border-gray-200 border p-3 text-sm resize-none" placeholder="描述页面的布局结构...&#10;如：顶部导航、左侧菜单、右侧内容区"></textarea>
                </div>
                
                <!-- 参考图上传 -->
                <div>
                    <div class="flex justify-between items-center mb-1">
                        <label class="text-sm font-medium text-gray-700">参考图</label>
                        <select id="similarity_${id}" class="text-xs border-gray-200 rounded py-1 px-2">
                            <option value="layout">仅参考布局</option>
                            <option value="style">仅参考风格</option>
                            <option value="pixel">像素级还原</option>
                        </select>
                    </div>
                    <div id="dropZone_${id}" class="border-2 border-dashed border-gray-200 rounded-lg h-24 flex items-center justify-center text-center hover:border-indigo-500 hover:bg-indigo-50/50 transition-all cursor-pointer">
                        <div class="text-gray-400 text-sm">
                            <i class="fas fa-image mr-2"></i>点击或拖拽上传
                        </div>
                        <input type="file" id="fileInput_${id}" class="hidden" accept="image/*" multiple>
                    </div>
                    <div id="preview_${id}" class="grid grid-cols-5 gap-2 mt-2 hidden"></div>
                </div>
            </div>
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <!-- 核心功能 -->
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">核心功能</label>
                    <textarea id="features_${id}" rows="3" class="w-full rounded-lg border-gray-200 border p-3 text-sm resize-none" placeholder="- 表格排序筛选&#10;- 数据导出"></textarea>
                </div>
                
                <!-- 交互说明 -->
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">交互说明</label>
                    <textarea id="interaction_${id}" rows="3" class="w-full rounded-lg border-gray-200 border p-3 text-sm resize-none" placeholder="点击按钮 → 弹出模态框"></textarea>
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

    // 更新序号
    pages.forEach((pid, i) => {
        const badge = document.querySelector(`#page-${pid} .bg-indigo-600`);
        if (badge) badge.textContent = i + 1;
    });
}

function setupPageListeners(id) {
    const dropZone = $(`dropZone_${id}`);
    const fileInput = $(`fileInput_${id}`);

    dropZone.onclick = () => fileInput.click();

    dropZone.ondragover = (e) => {
        e.preventDefault();
        dropZone.classList.add('border-indigo-500', 'bg-indigo-50');
    };

    dropZone.ondragleave = () => {
        dropZone.classList.remove('border-indigo-500', 'bg-indigo-50');
    };

    dropZone.ondrop = (e) => {
        e.preventDefault();
        dropZone.classList.remove('border-indigo-500', 'bg-indigo-50');
        handleFiles(id, e.dataTransfer.files);
    };

    fileInput.onchange = (e) => {
        handleFiles(id, e.target.files);
        fileInput.value = '';
    };
}

function handleFiles(id, files) {
    Array.from(files).filter(f => f.type.startsWith('image/')).forEach(file => {
        const reader = new FileReader();
        reader.onload = (e) => {
            pageFiles[id].push({
                name: file.name,
                base64: e.target.result
            });
            renderPreviews(id);
        };
        reader.readAsDataURL(file);
    });
}

function renderPreviews(id) {
    const container = $(`preview_${id}`);
    const files = pageFiles[id];

    if (files.length === 0) {
        container.classList.add('hidden');
        return;
    }

    container.classList.remove('hidden');
    container.innerHTML = files.map((f, i) => `
        <div class="relative aspect-square bg-gray-100 rounded overflow-hidden group">
            <img src="${f.base64}" class="w-full h-full object-cover cursor-zoom-in" onclick="previewImage('${f.base64}')">
            <button onclick="removeFile('${id}', ${i})" class="absolute top-1 right-1 w-5 h-5 bg-black/60 text-white rounded-full text-xs opacity-0 group-hover:opacity-100 transition-opacity">×</button>
        </div>
    `).join('');
}

function removeFile(id, index) {
    pageFiles[id].splice(index, 1);
    renderPreviews(id);
}

function previewImage(src) {
    $('fullSizeImage').src = src;
    $('imagePreviewModal').classList.remove('hidden');
    $('imagePreviewModal').classList.add('flex');
}

// ==================== AI 生成 ====================
function generatePrompt() {
    const global = {
        primaryColor: $('primaryColor').value,
        secondaryColor: $('secondaryColor').value,
        backgroundMode: $('backgroundMode').value,
        componentStyle: $('componentStyle').value
    };

    let prompt = `你是专业的前端工程师和UI/UX设计师。
请生成一个高保真的HTML原型页面。

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
- 圆角: 0.5rem
- 阴影: 使用柔和现代的阴影

# 页面需求
`;

    pages.forEach((id, index) => {
        const name = $(`pageName_${id}`).value || `页面${index + 1}`;
        const layout = $(`layout_${id}`).value;
        const features = $(`features_${id}`).value;
        const interaction = $(`interaction_${id}`).value;
        const similarity = $(`similarity_${id}`).value;
        const hasImages = pageFiles[id].length > 0;

        prompt += `
## 页面${index + 1}: ${name}
`;
        if (layout) prompt += `**布局**: ${layout}\n`;
        if (features) prompt += `**功能**: ${features}\n`;
        if (interaction) prompt += `**交互**: ${interaction}\n`;
        if (hasImages) {
            prompt += `**参考图**: 已附加${pageFiles[id].length}张参考图。`;
            if (similarity === 'pixel') {
                prompt += `请尽可能像素级还原。\n`;
            } else if (similarity === 'style') {
                prompt += `请参考其视觉风格。\n`;
            } else {
                prompt += `请参考其布局结构。\n`;
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
        componentStyle: $('componentStyle').value
    };

    const pagesData = pages.map((id, index) => ({
        name: $(`pageName_${id}`).value || `页面${index + 1}`,
        layout: $(`layout_${id}`).value,
        features: $(`features_${id}`).value,
        interaction: $(`interaction_${id}`).value,
        similarity: $(`similarity_${id}`).value,
        imageCount: pageFiles[id].length
    }));

    return { global, pages: pagesData };
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
        const imageData = images.map(f => f.base64.substring(0, 100)).join('|');
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
        const layout = $(`pageLayout_${id}`);
        return layout && layout.value && layout.value.trim() !== '';
    });

    // 检查是否有功能点描述
    const hasFeatures = pages.some(id => {
        const features = $(`pageFeatures_${id}`);
        return features && features.value && features.value.trim() !== '';
    });

    // 检查是否有交互方式描述
    const hasInteraction = pages.some(id => {
        const interaction = $(`pageInteraction_${id}`);
        return interaction && interaction.value && interaction.value.trim() !== '';
    });

    // 检查是否有参考图片
    const hasImages = pages.some(id => pageFiles[id] && pageFiles[id].length > 0);

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
        alert('请先输入内容'); // 临时使用alert确保能看到
        showToast('请先输入内容', 'error');
        return;
    }

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

    // 显示加载
    $('loadingModal').classList.remove('hidden');
    $('loadingModal').classList.add('flex');

    // 生成prompt
    const prompt = generatePrompt();
    console.log('=== Prompt ===');
    console.log(prompt);

    // 收集所有图片
    const allImages = [];
    pages.forEach(id => {
        pageFiles[id].forEach(f => allImages.push(f.base64));
    });

    // 项目名称
    const projectName = pages.map(id => $(`pageName_${id}`).value).filter(Boolean).join(' + ');

    try {
        // 构建请求数据
        const requestData = {
            prompt: prompt,
            images: allImages,
            projectName: projectName,
            formData: formData
        };

        // 如果使用增量更新，添加额外信息
        if (useIncremental && changes) {
            requestData.incremental = true;
            requestData.sourceProjectId = sourceProjectId;
            requestData.changes = changes;
        }

        const response = await fetch('/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });

        const result = await response.json();

        $('loadingModal').classList.add('hidden');

        if (result.error) {
            showToast('生成失败: ' + result.error, 'error');
            return;
        }

        if (result.success) {
            // 显示是否使用了增量更新
            if (result.incremental) {
                if (result.reusedPages === 'all') {
                    showToast('✅ 内容无变化，已复制原项目（0 API调用）');
                } else {
                    showToast(`✅ 增量生成成功！复用了${result.reusedPages || 0}个页面`);
                }
            } else {
                showToast('✅ 生成成功！');
            }

            // 添加到列表
            allProjects.unshift(result.project);
            renderProjectList();

            // 打开预览
            window.open(result.project.url, '_blank');

            // 重置增量更新状态
            sourceProjectId = null;
            originalFormData = null;
            originalImageHashes = {};
        }

    } catch (error) {
        $('loadingModal').classList.add('hidden');
        showToast('请求失败: ' + error.message, 'error');
        console.error(error);
    }
}

// ==================== 复制Prompt功能 ====================
async function copyPromptToClipboard() {
    // 验证是否有任何输入
    const hasInput = hasAnyInput();
    console.log('[复制Prompt验证] hasAnyInput 返回:', hasInput);

    if (!hasInput) {
        console.log('[复制Prompt验证] 没有输入，显示提示');
        alert('请先输入内容'); // 临时使用alert确保能看到
        showToast('请先输入内容', 'error');
        return;
    }

    const prompt = generatePrompt();
    const formData = collectFormData();
    const projectName = pages.map(id => $(`pageName_${id}`).value).filter(Boolean).join(' + ') || '未命名项目';

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
    if (hasImages) {
        fullPrompt += `\n## 参考图片\n`;
        pages.forEach((id, index) => {
            const images = pageFiles[id] || [];
            if (images.length > 0) {
                fullPrompt += `页面${index + 1}: ${images.length}张参考图\n`;
            }
        });
        fullPrompt += `\n注意：参考图已保存在项目文件夹 \`${projectId}\` 中\n`;
    }

    fullPrompt += `\n## 输出要求\n生成完整的HTML文件，保存到项目文件夹 \`${projectId}\` 的 index.html。`;

    // 收集图片数据（按页面索引组织）
    const imageFiles = {};
    pages.forEach((id, index) => {
        if (pageFiles[id] && pageFiles[id].length > 0) {
            imageFiles[index] = pageFiles[id].map(f => f.base64);
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
    $('toastIcon').className = type === 'error'
        ? 'fas fa-exclamation-circle text-red-400'
        : 'fas fa-check-circle text-green-400';

    toast.classList.remove('translate-y-20', 'opacity-0');
    setTimeout(() => toast.classList.add('translate-y-20', 'opacity-0'), 3000);
}
