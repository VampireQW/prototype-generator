/* 标注交互层：注入原型 iframe 内运行（同源）。
   父层通过 window.ProtoAnnotate 调用；交互结果经 window.parent.ProtoExtHost 回传。
   所有注入元素带 data-prototype-owned，锚点库会将其排除在点选之外。 */
(() => {
    'use strict';
    if (window.ProtoAnnotate) return;

    let active = false;
    let selectedId = null;
    let drag = null;
    let suppressedClick = null;
    let saving = false;
    const motion = () => matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth';
    /* 卡片与视口边缘的最小间距：12px（曾 8px，用户反馈靠边缘输入时太挤）——CSS 侧对应 calc(100% - 24px)。 */
    const CARD_EDGE = 12;
    const viewWidth = () => document.documentElement.clientWidth;
    const viewHeight = () => document.documentElement.clientHeight;
    /* 气泡卡挂在父页（工作台）文档里，而不是原型 iframe 内：手机 / 平板壳只有 393px 宽，卡挤在壳里看不清，
       挂到父页后能拖出壳外、按父页视口钳位，工具条（proto-markdown 同样挂 region.ownerDocument）跟着出来。
       父页不可达（原型单独打开、跨源、测试桩）时退回本文档，几何按本视口算。 */
    let cardLayer = null;
    function cardDoc() {
        try { const d = window.parent?.document; if (d && d !== document && d.documentElement) return d; } catch (_) { /* 跨源父页 */ }
        return document;
    }
    const cardWidth = () => cardDoc().documentElement.clientWidth;
    const cardHeight = () => cardDoc().documentElement.clientHeight;
    /* iframe 视口坐标 → 卡文档坐标：卡在父页时加上本 iframe 在父页里的偏移 */
    function toCard(x, y) {
        if (cardDoc() === document) return { x, y };
        const r = window.frameElement?.getBoundingClientRect?.();
        return r ? { x: x + r.left, y: y + r.top } : { x, y };
    }
    const editable = el => !!el?.closest?.('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"]');
    let hoverBox = null;
    let pinLayer = null;
    let inputCard = null;
    let cardObserver = null;
    let cardPoint = null;
    let cardResizing = null;   // 拖宽进行中：抑制 ResizeObserver 锚点重排
    let cardManual = false;    // 用户手动拖过宽度：后续重排只钳进视口，不再对齐锚点
    let cardOffset = null;     // 用户拖动过卡片：相对锚点（序号 / 落点）的偏移，重排时按此偏移跟随而不回默认位
    let keptOffset = null;     // { id, offset }：关卡时留下的拖动偏移，同一条标注重开（双击转编辑会关再开）沿用，拖出手机壳的卡不被塞回去
    let pending = null;          // { anchor, placement, x, y, rebindId? }
    let notes = [];
    let composing = false;
    let mounted = false;
    const numberOf = note => note?.displayNumber ?? note?.number;
    const previewNumber = (x, y) => host()?.previewNumber?.(x, y) || notes.length + 1;

    const owned = (el) => !!el?.closest?.('[data-prototype-owned]');

    /* 联动展开期间放行原型点击：reveal 通过合成 trig.click() 点开折叠按钮，标注模式下会被 onClick 捕获拦截
       （preventDefault + stopImmediatePropagation 并弹新建输入卡），导致点引导框 / 序号定位都展不开。 */
    let revealing = false;
    function revealThrough(target) {
        revealing = true;
        try { return ProtoAnchors.reveal?.(target); } finally { revealing = false; }
    }

    function ensureStyle(doc = document) {
        if (doc.getElementById('proto-annotate-style')) return;
        const style = doc.createElement('style');
        style.id = 'proto-annotate-style';
        style.setAttribute('data-prototype-owned', '');
        style.textContent = `
.pa-layer{--pa-accent:#2563eb;--pa-accent-hover:#1d4ed8;--pa-ring:#7ba2ff;--pa-on-accent:#ffffff;--pa-surface:#212326;--pa-text:#f2f4f7;--pa-muted:#a8b0ba;--pa-border:#808790;--pa-control:#808790;--pa-hover:#363c44;--pa-stale:#626b78;--pa-scroll:#78828f;--pa-error:#ff8a8a;--pa-shadow:0 8px 24px rgba(16,24,40,.24);--pa-font:"PingFang SC","Microsoft YaHei UI","Microsoft YaHei",system-ui,sans-serif;position:fixed;inset:0;z-index:2147483000;pointer-events:none;}
/* 浅色系（由父页外观设置下发 data-theme=light）：与右栏 --ext-* 浅色 token 同源。正文 #1a1d23/#fff 16.9:1，次要 #626b78/#fff 5.4:1；
   卡边框与滚动条沟 #808790/#fff 3.6:1（浮卡盖在任意原型内容上，边界按控件“≥ 3:1”取）；焦点环改用主色 #2563eb/#fff 5.2:1。 */
/* 父页按模式收起整层（预览 / 微调）：序号、引导徽标、气泡卡一起不出现，不是逐个 visibility 藏 */
.pa-layer[data-hidden]{display:none;}
.pa-layer[data-theme="light"]{--pa-ring:#2563eb;--pa-surface:#ffffff;--pa-text:#1a1d23;--pa-muted:#626b78;--pa-border:#808790;--pa-control:#808790;--pa-hover:#f1f2f4;--pa-scroll:#808790;--pa-error:#b42318;--pa-shadow:0 8px 24px rgba(16,24,40,.16);}
.pa-layer *, .pa-layer *::before{box-sizing:border-box;}
.pa-pin{position:absolute;display:grid;place-items:center;min-width:36px;height:36px;margin:0;padding:0 8px;border:3px solid var(--pa-on-accent);border-radius:50% 50% 50% 2px;background:var(--pa-accent);color:var(--pa-on-accent);font:600 13px/1 var(--pa-font);font-variant-numeric:tabular-nums;box-shadow:var(--pa-shadow);transform:translateY(-100%);cursor:grab;touch-action:none;user-select:none;pointer-events:auto;}
.pa-pin::before{content:"";position:absolute;inset:-7px;}
.pa-layer .pa-pin:not(.pa-stale){background:var(--pin-fill,var(--pa-accent));color:var(--pin-ink,var(--pa-on-accent));border-color:var(--pin-stroke,var(--pa-on-accent));}
.pa-layer .pa-pin[data-note-id]:hover{background:var(--pin-fill,var(--pa-accent));filter:brightness(.96);}
.pa-pin.pa-cursor{pointer-events:none;z-index:2;}
.pa-pin.pa-stale{background:var(--pa-stale);}
.pa-pin.pa-selected,.pa-pin.pa-flash{outline:3px solid var(--pa-accent);outline-offset:3px;z-index:3;}
.pa-pin.pa-dragging{cursor:grabbing;z-index:4;}
.pa-pin:focus-visible,.pa-layer button:focus-visible,.pa-layer textarea:focus-visible{outline:2px solid var(--pa-ring);outline-offset:3px;}
.pa-layer .pa-pin:focus-visible{outline-color:var(--pa-accent);}
.pa-layer button:disabled{opacity:.5;cursor:not-allowed;}
/* 卡片 = 外壳（不裁剪，边框上挂拖拽热区）+ 内部滚动区 .pa-card-scroll。默认最多 60vh 高（曾撑满整屏），宽 420px；手动拖过高度后只受视口钳制。 */
.pa-card{position:absolute;z-index:5;display:flex;flex-direction:column;width:420px;max-width:calc(100% - 24px);max-height:min(60vh,calc(100% - 24px));overflow:visible;pointer-events:auto;background:var(--pa-surface);color:var(--pa-text);border:1px solid var(--pa-border);border-radius:10px;box-shadow:var(--pa-shadow);font:14px/1.7 var(--pa-font);letter-spacing:.02em;animation:paOpen 180ms ease-out;}
.pa-card.pa-sized{max-height:calc(100% - 24px);}
.pa-layer .pa-card-scroll{flex:1 1 auto;min-height:0;margin:0;padding:0;overflow-x:hidden;overflow-y:auto;border-radius:0 0 9px 9px;}
/* 边缘拖拽热区：骑在卡片真实边框上（外 6px + 边框 + 内 3px，不占滚动条的抓取宽），不画任何指示线——可拖只由光标表达（曾有一条蓝线，用户要求去掉）。
   左右缘调宽、下缘调高、下方两角同时调；上缘留给拖柄移动。 */
.pa-card-resize{position:absolute;touch-action:none;z-index:6;}
.pa-card-resize-e,.pa-card-resize-w{top:0;bottom:0;width:10px;cursor:ew-resize;}
.pa-card-resize-e{right:-6px;}
.pa-card-resize-w{left:-6px;}
.pa-card-resize-s{left:0;right:0;bottom:-6px;height:10px;cursor:ns-resize;}
.pa-card-resize-se,.pa-card-resize-sw{bottom:-6px;width:16px;height:16px;z-index:7;}
.pa-card-resize-se{right:-6px;cursor:nwse-resize;}
.pa-card-resize-sw{left:-6px;cursor:nesw-resize;}
@media(pointer:coarse){.pa-card-resize-e,.pa-card-resize-w{width:20px;}.pa-card-resize-e{right:-10px;}.pa-card-resize-w{left:-10px;}.pa-card-resize-s{height:20px;bottom:-10px;}.pa-card-resize-se,.pa-card-resize-sw{width:28px;height:28px;bottom:-10px;}.pa-card-resize-se{right:-10px;}.pa-card-resize-sw{left:-10px;}}
/* 顶部拖柄：按住拖动卡片（卡体内边距同样可拖）；在滚动区之外，长内容滚动时始终在顶。 */
.pa-layer .pa-card-grip{position:relative;flex:0 0 auto;z-index:2;display:grid;place-items:center;height:14px;margin:0;padding:0;background:var(--pa-surface);border-radius:9px 9px 0 0;cursor:grab;touch-action:none;user-select:none;}
.pa-card-grip::before{content:"";width:32px;height:4px;border-radius:2px;background:var(--pa-control);opacity:.75;}
.pa-card.pa-moving,.pa-card.pa-moving .pa-card-grip,.pa-card.pa-moving .pa-card-body{cursor:grabbing;}
.pa-card.pa-moving{user-select:none;}
.pa-card,.pa-card *{scrollbar-width:thin;scrollbar-color:var(--pa-scroll) transparent;}
.pa-card::-webkit-scrollbar,.pa-card *::-webkit-scrollbar{width:8px;height:8px;}
.pa-card::-webkit-scrollbar-track,.pa-card *::-webkit-scrollbar-track{background:transparent;}
.pa-card::-webkit-scrollbar-thumb,.pa-card *::-webkit-scrollbar-thumb{background:var(--pa-scroll);border-radius:4px;}
.pa-card::-webkit-scrollbar-thumb:hover,.pa-card *::-webkit-scrollbar-thumb:hover{background:var(--pa-muted);}
.pa-layer .pa-card-body{margin:0;padding:8px 20px 12px 12px;min-height:0;cursor:grab;} /* 右侧 20px：滚动条 + 边框都挤在这侧，文字不贴边（阅读 / 编辑共用此盒，接管对齐不受影响） */
.pa-layer .pa-card-solo{padding-top:2px;}
.pa-card-text{white-space:normal;overflow-wrap:anywhere;cursor:text;}
.pa-card-text img,.pa-card-text video,.pa-card-text canvas,.pa-card-text svg{max-width:100%;height:auto;}
.pa-card-foot{flex:0 0 auto;display:flex;justify-content:flex-end;align-items:center;gap:8px;padding:8px 12px 12px;}
.pa-card-error{color:var(--pa-error);font-size:12px;padding:0 16px;}
.pa-btn{min-height:32px;min-width:56px;margin:0;border:1px solid var(--pa-control);border-radius:6px;padding:4px 16px;background:transparent;color:var(--pa-text);font:inherit;white-space:nowrap;cursor:pointer;}
.pa-btn-primary{background:var(--pa-accent);border-color:var(--pa-accent);color:var(--pa-on-accent);}
.pa-btn:active{transform:translateY(1px);}
@media(hover:hover){.pa-pin:hover{background:var(--pa-accent-hover);}.pa-btn:not(:disabled):hover{background:var(--pa-hover);}.pa-btn-primary:not(:disabled):hover{background:var(--pa-accent-hover);}}
@keyframes paOpen{from{opacity:0;transform:translateY(4px);}to{opacity:1;transform:translateY(0);}}
@media(prefers-reduced-motion:reduce){.pa-card{animation:none;}}
@media(pointer:coarse){.pa-pin{min-width:44px;height:44px;}.pa-btn{min-height:44px;min-width:44px;}}
/* 点击引导：亮黄色系，与蓝色水滴序号在 色相 / 形状 / 动效 三方面区分。
   框 = 透明可点区：虚线、静态不呼吸，盖在折叠触发器上（原型内容透视可见）；悬停转实线 + 加深底色 + 外环。
   标签 = 与框左上角拼成一体的选区式标签（框该角直角、标签底角直角），只有标签呼吸（光晕起伏 + 箭头上下浮动）。
   偏离 DESIGN_MASTER --accent-amber #b45309（实看发褐）：框线 #d97706（白底 3.19:1，控件边界 ≥3:1），标签 #fbbf24 配深棕字 #5c3300（6.52:1）。
   固定浅色、不随 prefers-color-scheme 切换：引导叠在原型页面上，颜色跟随页面而非系统。 */
.pa-guide{--g-line:#d97706;--g-fill:#fbbf24;--g-ink:#5c3300;position:absolute;margin:0;padding:0;border:2px dashed var(--g-line);border-radius:0 8px 8px 8px;background:rgba(251,191,36,.10);cursor:pointer;pointer-events:auto;transition:background-color 150ms ease-out,box-shadow 150ms ease-out;}
.pa-guide:hover{border-style:solid;background:rgba(251,191,36,.30);box-shadow:0 0 0 3px rgba(251,191,36,.38);}
.pa-guide:active{background:rgba(251,191,36,.45);}
.pa-layer .pa-guide:focus-visible{outline:2px solid var(--g-line);outline-offset:2px;}
.pa-guide-tag{position:absolute;left:-2px;top:-2px;transform:translateY(-100%);display:inline-flex;align-items:center;gap:3px;height:18px;padding:0 7px 0 5px;border:1px solid var(--g-line);border-radius:6px 6px 6px 0;background:var(--g-fill);color:var(--g-ink);font:600 11px/1 var(--pa-font);white-space:nowrap;pointer-events:none;animation:paGuideTag 1.8s ease-in-out infinite;animation-delay:var(--g-delay,0s);}
.pa-guide-tag svg{width:10px;height:10px;animation:paGuideBob 1.8s ease-in-out infinite;animation-delay:var(--g-delay,0s);}
.pa-guide:hover .pa-guide-tag{animation:none;box-shadow:0 0 0 3px rgba(251,191,36,.38);}
.pa-guide.pa-guide-below{border-radius:8px 8px 8px 0;}
.pa-guide.pa-guide-below .pa-guide-tag{top:auto;bottom:-2px;transform:translateY(100%);border-radius:0 6px 6px 6px;}
.pa-guide.pa-guide-end{border-radius:8px 0 8px 8px;}
.pa-guide.pa-guide-end .pa-guide-tag{left:auto;right:-2px;border-radius:6px 6px 0 6px;}
.pa-guide.pa-guide-below.pa-guide-end{border-radius:8px 8px 0 8px;}
.pa-guide.pa-guide-below.pa-guide-end .pa-guide-tag{border-radius:6px 0 6px 6px;}
@keyframes paGuideTag{0%,100%{box-shadow:0 0 0 0 rgba(251,191,36,0),0 1px 2px rgba(92,51,0,.18);}50%{box-shadow:0 0 0 4px rgba(251,191,36,.42),0 1px 2px rgba(92,51,0,.18);}}
@keyframes paGuideBob{0%,100%{transform:translateY(-1px);}50%{transform:translateY(1px);}}
@media(prefers-reduced-motion:reduce){.pa-guide-tag,.pa-guide-tag svg{animation:none;}}
`;
        (doc.head || doc.documentElement).appendChild(style);
    }

    /* 卡层：父页文档里的 .pa-layer（与序号层同一套样式 / token，主题与显隐跟随序号层）。
       iframe 换页后旧脚本实例随页面销毁、父页里的层还在：复用并清掉残留节点。 */
    function ensureCardLayer() {
        const doc = cardDoc();
        if (doc === document) { ensureLayers(); return pinLayer; }
        ensureStyle(doc);
        if (!cardLayer || cardLayer.ownerDocument !== doc) {
            cardLayer = doc.getElementById('proto-annotate-cards');
            if (!cardLayer) {
                cardLayer = doc.createElement('div');
                cardLayer.id = 'proto-annotate-cards';
                cardLayer.className = 'pa-layer';
                cardLayer.setAttribute('data-prototype-owned', '');
                doc.documentElement.appendChild(cardLayer);
            }
            cardLayer.replaceChildren();
        }
        if (pinLayer?.dataset.theme) cardLayer.dataset.theme = pinLayer.dataset.theme;
        cardLayer.toggleAttribute('data-hidden', !!pinLayer?.hasAttribute('data-hidden'));
        return cardLayer;
    }

    function ensureLayers() {
        ensureStyle();
        if (!pinLayer) {
            pinLayer = document.createElement('div');
            pinLayer.setAttribute('data-prototype-owned', '');
            pinLayer.className = 'pa-layer';
            document.documentElement.appendChild(pinLayer);
        }
        if (!mounted) {
            mounted = true;
            document.addEventListener('mousemove', onMouseMove, true);
            document.addEventListener('click', onClick, true);
            document.addEventListener('keydown', onKeyDown, true);
            document.addEventListener('pointermove', moveDrag, { capture: true, passive: false });
            document.addEventListener('pointerup', endDrag, true);
            document.addEventListener('pointercancel', cancelDrag, true);
            document.addEventListener('mouseleave', hideHover);
        }
    }

    function host() { return window.parent?.ProtoExtHost || null; }

    // ---------- 点选交互 ----------

    function ensureHoverBox() {
        if (!hoverBox) {
            hoverBox = document.createElement('div');
            hoverBox.className = 'pa-pin pa-cursor';
            hoverBox.setAttribute('aria-hidden', 'true');
            hoverBox.setAttribute('data-prototype-owned', '');
            // 插入时冻结的预览序号是工具条自动摆位的障碍（proto-markdown placeToolbar 避让协议）
            hoverBox.setAttribute('data-proto-toolbar-avoid', '');
            pinLayer.appendChild(hoverBox);
        }
        return hoverBox;
    }

    function showPreviewNumber(x, y) {
        const box = ensureHoverBox();
        const rebindId = pending?.rebindId || window.__paRebindId;
        box.textContent = numberOf(notes.find(n => n.id === rebindId)) || previewNumber(x, y);
        box.style.left = Math.min(x, viewWidth() - 44) + 'px';
        box.style.top = Math.max(40, y) + 'px';
        box.style.display = '';
    }

    function onMouseMove(e) {
        if (!active || drag || saving) { hideHover(); return; }
        // 点击落点后序号冻结在落点旁，直到输入卡关闭；在输入卡上移动鼠标也不能把它藏掉。
        if (pending || inputCard) return;
        if (owned(e.target)) { hideHover(); return; }
        showPreviewNumber(e.clientX, e.clientY);
    }

    // 落点已冻结（pending）期间预览序号不可隐藏：鼠标移出 iframe 到父页的 PRD 栏 / 顶栏也会触发 document mouseleave，
    // 不能让它把用户正在对照输入的序号藏掉。只有 closeInputCard 清掉 pending 之后才允许隐藏。
    function hideHover() { if (hoverBox && !pending) hoverBox.style.display = 'none'; }

    function onClick(e) {
        if (revealing || owned(e.target)) return;
        if (!active) {
            if (selectedId) { selectNote(null); host()?.clearSelection?.(); }
            if (inputCard && !pending) closeInputCard();
            return;
        }
        e.preventDefault();
        e.stopImmediatePropagation();
        if (saving || host()?.markdown?.isBusy()) return;
        if (inputCard) { closeInputCard(true); selectNote(null); host()?.clearSelection?.(); return; }
        if (host()?.markdown?.current()) { host().markdown.focus(); return; }
        const el = ProtoAnchors.at(e.clientX, e.clientY);
        const anchor = el ? ProtoAnchors.serialize(el) : null;
        const placement = ProtoAnchors.placement(el, e.clientX, e.clientY);
        pending = { anchor, placement, x: e.clientX, y: e.clientY, scopeKey: host()?.scopeKey?.(), rebindId: window.__paRebindId || null };
        window.__paRebindId = null;
        hideHover();
        selectNote(null);
        host()?.clearSelection?.();
        openInputCard(pending.x, pending.y);
    }

    function onKeyDown(e) {
        if (e.isComposing || composing || e.keyCode === 229) return;
        const sc = host()?.pickShortcut?.() || { code: 'KeyA', alt: true, shift: true };
        if (e.code === sc.code && !!e.altKey === !!sc.alt && !!e.shiftKey === !!sc.shift && !!e.ctrlKey === !!sc.ctrl && !!e.metaKey === !!sc.meta && !e.repeat && !editable(e.target)) {
            e.preventDefault(); e.stopPropagation(); host()?.togglePick?.(); return;
        }
        if (e.key === 'Escape') {
            if (editable(e.target) && !owned(e.target)) return;
            if (!active && !inputCard && !drag) return;
            e.preventDefault(); e.stopPropagation();
            if (saving) return;
            if (drag) cancelDrag();
            if (editable(e.target) && inputCard) { closeInputCard(true); return; }
            if (inputCard) closeInputCard(true);
            window.__paRebindId = null;
            if (active) { deactivate(); host()?.exitAnnotate?.(); }
        }
        if (e.key === 'Backspace' && !e.repeat && !e.ctrlKey && !e.metaKey && !e.altKey && !editable(e.target) && selectedId && !saving && !drag) {
            e.preventDefault(); e.stopPropagation();
            host()?.deleteNote?.(selectedId);
        }
    }

    // ---------- 输入卡 ----------

    function openInputCard(x, y) {
        if (inputCard) closeInputCard(true);
        inputCard = makeCard();
        const card = inputCard, pick = pending;
        card.setAttribute('role', 'dialog');
        card.setAttribute('aria-label', pick.rebindId ? '重新绑定标注' : '添加标注');
        setCardBody(card, '<div class="pa-card-body pa-card-solo"><div class="pa-card-text"></div></div>');
        const region = card.querySelector('.pa-card-text');
        if (pick.rebindId) {
            const note = notes.find(n => n.id === pick.rebindId);
            host()?.renderNote?.(region, { ...note, confirmed: true });
            const cdoc = card.ownerDocument;
            const button = cdoc.createElement('button'); button.className = 'pa-btn pa-btn-primary'; button.textContent = '确认绑定';
            const foot = cdoc.createElement('div'); foot.className = 'pa-card-foot'; foot.appendChild(button);
            card.querySelector(':scope > .pa-card-scroll').after(foot);   // 底栏在滚动区之外，长文本滚动时按钮始终可见
            button.onclick = async () => {
                saving = true; button.disabled = true;
                try {
                    const ok = await host()?.rebindDone?.(pick.rebindId, pick.anchor, pick.placement);
                    if (ok && inputCard === card) closeInputCard();
                    else button.textContent = '未保存，重试';
                } finally { saving = false; button.disabled = false; }
            };
        } else {
            const started = host()?.beginPick?.(region, pick, id => {
                if (inputCard === card) closeInputCard();
                if (pick.scopeKey === host()?.scopeKey?.()) { selectNote(id); host()?.focusNote?.(id); }
            }, () => { if (inputCard === card) closeInputCard(true); });
            if (!started) { closeInputCard(); return; }
        }
        placeCard(x, y);
        // 即使用户没有先移动鼠标、hoverBox 尚未创建，点击后也必须在落点旁显示并冻结序号。
        showPreviewNumber(x, y);
        // beginPick 已同步摆过一次工具条，但那时卡片还没落位、序号还没显示；现在按真实几何重摆，避开序号
        host()?.markdown?.relayout?.();
    }

    function makeCard() {
        ensureLayers();
        const layer = ensureCardLayer(), doc = layer.ownerDocument;
        const card = doc.createElement('div');
        card.className = 'pa-card';
        card.setAttribute('data-prototype-owned', '');
        layer.appendChild(card);
        // 顶部拖柄：按住拖动卡片；卡体内边距也能拖（按下点不在正文 / 按钮 / 编辑器上即可）
        const grip = doc.createElement('div');
        grip.className = 'pa-card-grip';
        grip.setAttribute('data-prototype-owned', '');
        grip.setAttribute('aria-hidden', 'true');
        grip.title = '拖动移动';
        card.appendChild(grip);
        card.addEventListener('pointerdown', e => startCardMove(e, card));
        // 内部滚动区：正文在这里滚，外壳不裁剪，边框上的拖拽热区才能骑在真实边缘上、且不随内容滚走
        const scroll = doc.createElement('div');
        scroll.className = 'pa-card-scroll';
        scroll.setAttribute('data-prototype-owned', '');
        card.appendChild(scroll);
        // 边缘拖拽热区：左右缘调宽、下缘调高、下方两角同时调
        for (const side of ['w', 'e', 's', 'se', 'sw']) {
            const handle = doc.createElement('span');
            handle.className = `pa-card-resize pa-card-resize-${side}`;
            handle.setAttribute('data-prototype-owned', '');
            handle.setAttribute('aria-hidden', 'true');
            handle.title = side === 's' ? '拖动调节高度' : side.length > 1 ? '拖动调节大小' : '拖动调节宽度';
            handle.onpointerdown = e => startCardResize(e, card, handle, side);
            card.appendChild(handle);
        }
        cardObserver?.disconnect();
        // 卡在父页文档时用父页窗口的 ResizeObserver 观察（跨文档观察不可靠）
        const RO = doc.defaultView?.ResizeObserver || (typeof ResizeObserver !== 'undefined' ? ResizeObserver : null);
        if (RO) {
            cardObserver = new RO(() => {
                if (!cardPoint || !inputCard || cardResizing) return;
                placeCardAt(cardPoint);   // 拖过位按偏移跟随锚点；只调过尺寸原位钳进视口；都没动过回默认摆位（见 placeCardAt）
            });
            cardObserver.observe(card);
        }
        return card;
    }

    /* 重写卡内容时只动滚动区，拖柄、拖拽热区与底栏不受影响：统一走这里，不对卡片 innerHTML。 */
    function setCardBody(card, html) {
        card.querySelector(':scope > .pa-card-scroll').innerHTML = html;
    }

    function clampCardIntoView() {
        if (!inputCard) return;
        const w = inputCard.offsetWidth, h = inputCard.offsetHeight;
        const l = parseFloat(inputCard.style.left) || 8, t = parseFloat(inputCard.style.top) || 8;
        inputCard.style.left = Math.max(CARD_EDGE, Math.min(l, cardWidth() - w - CARD_EDGE)) + 'px';
        inputCard.style.top = Math.max(CARD_EDGE, Math.min(t, cardHeight() - h - CARD_EDGE)) + 'px';
    }

    /* 指针拖动期间由卡所在窗口全程接管：滑出卡外 / 越过编辑器 iframe 也不丢事件；元素级 pointer capture 只是增强（能失败，不依赖）。 */
    function trackPointer(e, target, onMove, onEnd, cursor) {
        try { target.setPointerCapture(e.pointerId); } catch (_) { /* 部分环境不支持，靠 window 监听即可 */ }
        const win = target.ownerDocument?.defaultView || window;
        const root = win.document.documentElement, cursor0 = root.style.cursor, select0 = root.style.userSelect;
        root.style.cursor = cursor; root.style.userSelect = 'none';
        const move = ev => { if (ev.pointerId === e.pointerId) onMove(ev); };
        const end = ev => {
            if (ev.pointerId !== e.pointerId) return;
            win.removeEventListener('pointermove', move, true);
            win.removeEventListener('pointerup', end, true);
            win.removeEventListener('pointercancel', end, true);
            root.style.cursor = cursor0; root.style.userSelect = select0;
            try { if (target.hasPointerCapture(e.pointerId)) target.releasePointerCapture(e.pointerId); } catch (_) { /* 同上 */ }
            onEnd(ev);
        };
        win.addEventListener('pointermove', move, true);
        win.addEventListener('pointerup', end, true);
        win.addEventListener('pointercancel', end, true);
    }

    /* 气泡卡边缘拖拽调尺寸：side 含 e / w 调宽（右缘只改宽；左缘右缘锚定，改宽 + left），含 s 调高（上缘锚定），se / sw 两者同时；
       宽 280-760px、高 ≥ 160px，都不推出视口；手动调过高度后挂 pa-sized 解除 60vh 默认上限；拖动中/后工具条（非手动位）实时跟随重定位。 */
    const RESIZE_CURSOR = { e: 'ew-resize', w: 'ew-resize', s: 'ns-resize', se: 'nwse-resize', sw: 'nesw-resize' };
    function startCardResize(e, card, handle, side) {
        if (e.button !== 0 || cardResizing) return;
        e.preventDefault(); e.stopPropagation();
        const rect = card.getBoundingClientRect();
        const startX = e.clientX, startY = e.clientY, startW = card.offsetWidth, startH = card.offsetHeight, startL = rect.left, startT = rect.top;
        const horizontal = side.includes('e') ? 'e' : side.includes('w') ? 'w' : null, vertical = side.includes('s');
        cardResizing = { card, side };
        // 调过尺寸的卡视为用户摆好了位：记下相对锚点的偏移，重排时跟随序号而不回默认摆位（默认摆位会因卡变高而翻到落点上方）
        if (!cardOffset && cardPoint) cardOffset = { x: startL - cardPoint.x, y: startT - cardPoint.y };
        trackPointer(e, handle, ev => {
            if (cardResizing?.card !== card) return;
            if (horizontal) {
                const dx = ev.clientX - startX;
                const maxW = Math.min(760, cardWidth() - CARD_EDGE * 2);
                const hi = horizontal === 'e' ? Math.min(maxW, cardWidth() - startL - CARD_EDGE) : Math.min(maxW, startL + startW - CARD_EDGE);
                const raw = horizontal === 'e' ? startW + dx : startW - dx;
                const w = Math.max(Math.min(280, hi), Math.min(Math.round(raw), hi));
                card.style.width = w + 'px';
                if (horizontal === 'w') {
                    const left = startL + startW - w;
                    card.style.left = left + 'px';
                    if (cardOffset && cardPoint) cardOffset.x = left - cardPoint.x;   // 拖过位的卡：左缘变了，相对锚点偏移同步
                }
            }
            if (vertical) {
                const hi = cardHeight() - startT - CARD_EDGE;
                const h = Math.max(Math.min(160, hi), Math.min(Math.round(startH + ev.clientY - startY), hi));
                card.style.height = h + 'px';
                card.classList.add('pa-sized');
            }
            cardManual = true;
            host()?.markdown?.relayout?.();
        }, () => {
            cardResizing = null;
            host()?.markdown?.relayout?.();
        }, RESIZE_CURSOR[side]);
    }

    /* 气泡卡按住拖动：按在拖柄或卡体内边距上拖，不抢正文选字 / 链接 / 按钮 / 编辑器；
       5px 阈值区分点击；松手后记下相对锚点的偏移，滚动 / 重排时卡片按该偏移跟着序号走，不再被拉回默认位。 */
    function startCardMove(e, card) {
        if (e.button !== 0 || cardResizing || inputCard !== card) return;
        if (e.target.closest('.pa-card-resize, .pa-card-text, .pa-card-foot, button, a, input, iframe')) return;
        e.preventDefault();
        const startX = e.clientX, startY = e.clientY;
        const rect = card.getBoundingClientRect(), baseL = rect.left, baseT = rect.top;
        let moving = false;
        trackPointer(e, card, ev => {
            if (inputCard !== card) return;
            const dx = ev.clientX - startX, dy = ev.clientY - startY;
            if (!moving) { if (Math.hypot(dx, dy) < 5) return; moving = true; card.classList.add('pa-moving'); }
            ev.preventDefault();
            const left = Math.max(CARD_EDGE, Math.min(baseL + dx, cardWidth() - card.offsetWidth - CARD_EDGE));
            const top = Math.max(CARD_EDGE, Math.min(baseT + dy, cardHeight() - card.offsetHeight - CARD_EDGE));
            card.style.left = left + 'px'; card.style.top = top + 'px';
            cardManual = true;
            cardOffset = cardPoint ? { x: left - cardPoint.x, y: top - cardPoint.y } : null;
            host()?.markdown?.relayout?.();
        }, () => {
            card.classList.remove('pa-moving');
            if (moving) host()?.markdown?.relayout?.();
        }, 'grabbing');
    }

    /* 锚点（序号 / 落点）按 iframe 视口坐标传入，换算到卡文档坐标后摆卡 */
    function placeCard(x, y) { placeCardAt(toCard(x, y)); }
    function placeCardAt(p) {
        if (!inputCard) return;
        const x = p.x, y = p.y;
        cardPoint = { x, y };
        const left0 = inputCard.style.left, top0 = inputCard.style.top;
        // 手动调过尺寸（未拖过位）：原位钳进视口即可——默认摆位会因卡变高而翻到落点上方，用户刚拖完卡就跳走
        if (cardManual && !cardOffset) clampCardIntoView();
        else placeCardDefault(x, y);
        // 卡在父页：原型 iframe 内滚动父页收不到 scroll，卡位置变了就让编辑工具条跟着重摆（右栏会话不受影响：位置没变不触发）
        if ((inputCard.style.left !== left0 || inputCard.style.top !== top0) && host()?.markdown?.owns?.(inputCard)) host().markdown.relayout?.();
    }
    function placeCardDefault(x, y) {
        const w = inputCard.offsetWidth, h = inputCard.offsetHeight;
        const width = cardWidth(), height = cardHeight();
        let left, top;
        if (cardOffset) { left = x + cardOffset.x; top = y + cardOffset.y; }   // 用户拖过：保持相对锚点的偏移
        else {
            left = x + 48; top = y - 8;
            if (left + w > width - CARD_EDGE) {
                if (x - w - 12 >= CARD_EDGE) left = x - w - 12;
                else { left = CARD_EDGE; top = y + 12; }
            }
            if (top + h > height - CARD_EDGE) top = y - 48 - h;
        }
        inputCard.style.left = Math.max(CARD_EDGE, Math.min(left, width - w - CARD_EDGE)) + 'px';
        inputCard.style.top = Math.max(CARD_EDGE, Math.min(top, height - h - CARD_EDGE)) + 'px';
    }

    function closeInputCard(preserve = false) {
        const card = inputCard;
        inputCard = null;
        pending = null;
        cardObserver?.disconnect();
        cardPoint = null;
        cardResizing = null;
        cardManual = false;
        if (card?.dataset?.noteId && cardOffset) keptOffset = { id: card.dataset.noteId, offset: cardOffset };
        cardOffset = null;
        if (card) { host()?.markdown?.suspend(card); card.remove(); }
        composing = false;
        hideHover();
    }

    function selectNote(id) {
        selectedId = id;
        pinLayer?.querySelectorAll('.pa-pin[data-note-id]').forEach(pin => {
            const selected = pin.dataset.noteId === id;
            pin.classList.toggle('pa-selected', selected);
            pin.toggleAttribute('data-proto-toolbar-avoid', selected);
            pin.setAttribute('aria-pressed', String(selected));
        });
    }

    function openNote(id, edit = false) {
        if (saving) return;
        const note = notes.find(n => n.id === id);
        if (!note) return;
        // 已打开同一标注：编辑态聚焦；阅读态双击就地转编辑（不重建卡，所见即所得衔接零跳变）；阅读态再次单击序号则关闭（开 / 关轮替）
        if (inputCard?.dataset.noteId === id) {
            if (host()?.markdown?.owns(inputCard)) { host().markdown.focus(); return; }
            if (edit) {
                Promise.resolve(host()?.editNote?.(id, inputCard.querySelector('.pa-card-text'))).then(started => {
                    if (!started && inputCard?.dataset.noteId === id) closeInputCard();
                });
                return;
            }
            closeInputCard();
            return;
        }
        closeInputCard(true);
        selectNote(id);
        inputCard = makeCard();
        inputCard.dataset.noteId = id;
        if (keptOffset?.id === id) cardOffset = keptOffset.offset;
        if (note.confirmed || !edit) {
            // 单击只开阅读卡：纯渲染不加载编辑器，打开即所见；双击序号或卡内容才进编辑
            inputCard.setAttribute('role', 'dialog');
            inputCard.setAttribute('aria-label', note.confirmed ? `标注 ${numberOf(note)}，已确认，只读` : `标注 ${numberOf(note)}，双击编辑`);
            setCardBody(inputCard, '<div class="pa-card-body pa-card-solo"><div class="pa-card-text"></div></div>');
            host()?.renderNote?.(inputCard.querySelector('.pa-card-text'), note);
        } else {
            inputCard.setAttribute('role', 'dialog');
            inputCard.setAttribute('aria-label', `编辑标注 ${numberOf(note)}`);
            setCardBody(inputCard, '<div class="pa-card-body pa-card-solo"><div class="pa-card-text"></div></div>');
            Promise.resolve(host()?.editNote?.(id, inputCard.querySelector('.pa-card-text'))).then(started => {
                if (!started && inputCard?.dataset.noteId === id) closeInputCard();
            });
        }
        const pin = [...pinLayer.querySelectorAll('.pa-pin[data-note-id]')].find(p => p.dataset.noteId === id);
        if (pin) { pin.focus({ preventScroll: true }); placeCard(parseFloat(pin.style.left), parseFloat(pin.style.top)); }
        // 注：收起态才走到这里（弹气泡卡），不再回调 focusNote——否则会把右栏 PRD 自动展开，破坏「收起只弹气泡」的意图。
    }

    // ---------- 编号气泡 ----------

    function renderPins(list) {
        notes = Array.isArray(list) ? list : [];
        ensureLayers();
        if (selectedId && !notes.some(n => n.id === selectedId)) { closeInputCard(); selectNote(null); }
        if (drag && !notes.some(n => n.id === drag.id)) cancelDrag();
        pinLayer.querySelectorAll('.pa-pin[data-note-id]').forEach(pin => {
            if (!notes.some(n => n.id === pin.dataset.noteId)) pin.remove();
        });
        if (inputCard?.dataset.noteId && !host()?.markdown?.owns?.(inputCard)) {
            const note = notes.find(n => n.id === inputCard.dataset.noteId);
            if (note) host()?.renderNote?.(inputCard.querySelector('.pa-card-text'), note);
        }
        layoutPins();
    }

    function layoutPins() {
        if (!pinLayer) return;
        notes.forEach((note) => {
            let pin = [...pinLayer.querySelectorAll('.pa-pin[data-note-id]')].find(p => p.dataset.noteId === note.id);
            if (drag?.id === note.id) return;
            const found = ProtoAnchors.point(note);
            if (!pin) {
                pin = document.createElement('button');
                pin.type = 'button';
                pin.className = 'pa-pin';
                pin.dataset.noteId = note.id;
                pin.setAttribute('data-prototype-owned', '');
                pin.onclick = e => {
                    e.stopPropagation();
                    if (suppressedClick === note.id) return;
                    // 双击的第二击（detail=2）不当单击：否则会先把刚开的卡关掉，再由 dblclick 重开编辑——一闪一重建；略过它，dblclick 就地转编辑
                    if (e.detail > 1) return;
                    // PRD 展开态：点序号不在原型上弹气泡，直接定位到右栏对应内容；收起态才弹气泡卡（再点一次关闭）。
                    if (host()?.prdExpanded?.()) { closeInputCard(true); host()?.focusNote?.(note.id); return; }
                    openNote(note.id);
                };
                pin.ondblclick = e => {
                    e.stopPropagation();
                    if (suppressedClick === note.id) return;
                    if (host()?.prdExpanded?.()) { closeInputCard(true); host()?.focusNote?.(note.id); return; }
                    openNote(note.id, true);
                };
                pin.onpointerdown = e => startDrag(e, note.id, pin);
                pin.oncontextmenu = e => { e.preventDefault(); e.stopPropagation(); host()?.openNoteMenu?.(note.id, pin); };
                pinLayer.appendChild(pin);
            }
            pin.classList.toggle('pa-stale', !found.point);
            host()?.appearance?.applyPin(pin, note);
            pin.classList.toggle('pa-selected', note.id === selectedId);
            pin.toggleAttribute('data-proto-toolbar-avoid', note.id === selectedId);
            pin.setAttribute('aria-pressed', String(note.id === selectedId));
            pin.setAttribute('aria-label', `标注 ${numberOf(note)}：${note.body}`);
            pin.textContent = numberOf(note);
            pin.title = found.point ? `标注 ${numberOf(note)}` : (found.reason || '目标待重新定位');
            // 定不到落点（目标被折叠/切页签隐藏、或已失锚）的序号一律隐藏，不再摆成左上角灰色网格——
            // 那堆灰序号在用户眼里是 bug；可展开的由引导徽标提示，失锚的在右栏标灰并可从「更多」重新绑定。
            if (!found.point) { pin.style.visibility = 'hidden'; return; }
            const x = found.point.x, y = found.point.y;
            pin.style.left = Math.max(4, Math.min(x, viewWidth() - pin.offsetWidth - 4)) + 'px';
            pin.style.top = Math.max(40, Math.min(y, viewHeight() - 4)) + 'px';
            pin.style.visibility = found.point.visible ? '' : 'hidden';
            // 落点不可见（折叠 / 过渡动画中量到屏外坐标）时不挪卡——曾因此把开着的卡甩到左上角
            if (inputCard?.dataset.noteId === note.id && found.point.visible) placeCard(x, y);
        });
        layoutGuides();
    }

    /* 点击引导（Feature 1）：为「锚点存在但被折叠隐藏」的标注，在其折叠触发器上盖一层透明可点的虚线框（原型内容透视可见），
       左上角拼接呼吸标签「展开 · N」；点击即联动展开。仅折叠隐藏（可展开）才提示，纯失锚不提示。
       按触发器复用节点、只更新几何：重排频繁（滚动 / 文档变动），整体重建会打断悬停态与呼吸动画，
       按下与抬起落在新旧两个节点上时 click 不触发。 */
    function layoutGuides() {
        if (!pinLayer) return;
        const groups = new Map();
        notes.forEach((note) => {
            if (drag?.id === note.id) return;
            if (ProtoAnchors.point(note).point) return;            // 已有可见气泡
            const el = ProtoAnchors.resolveHidden?.(note.anchor);
            // revealHint 统一覆盖：折叠/details/aria-controls，以及标注时记录的 select/checkbox/radio/ARIA 条件；目标被动态移出 DOM 也能引导。
            const hint = ProtoAnchors.revealHint?.(note.anchor, el) ||
                (el && ProtoAnchors.hidden(el) && ProtoAnchors.revealTrigger(el) ? { trigger: ProtoAnchors.revealTrigger(el), target: el, label: '展开', kind: 'disclosure' } : null);
            if (!hint?.trigger) return;
            let g = groups.get(hint.trigger);
            // 同一触发器若对应多个条件值，一次只引导显示编号最前的一组；点击后重排会接力显示下一组，避免多个框重叠。
            const actionKey = `${hint.kind}\n${hint.label}`;
            if (!g) groups.set(hint.trigger, (g = { target: hint.target, label: hint.label, actionKey, notes: [] }));
            if (g.actionKey === actionKey) g.notes.push(note);
        });
        const ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
        const existing = [...pinLayer.querySelectorAll('.pa-guide')];
        const alive = new Set();
        let gi = existing.length;   // 新建引导错峰呼吸：负 delay 让各标签立处不同相位，避免整屏同步闪烁
        groups.forEach((g, trig) => {
            const r = trig.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) return;
            // 描边框套在触发器外 4px，小图标至少 22px 保证可点；裁到视口内，完全出视口就不画
            const pad = 4, w = Math.max(r.width + pad * 2, 22), h = Math.max(r.height + pad * 2, 22);
            let left = r.left + r.width / 2 - w / 2, top = r.top + r.height / 2 - h / 2;
            const right = Math.min(viewWidth() - 2, left + w), bottom = Math.min(viewHeight() - 2, top + h);
            left = Math.max(2, left); top = Math.max(2, top);
            if (right - left < 8 || bottom - top < 8) return;
            let marker = existing.find((m) => m.__paTrig === trig);
            if (!marker) {
                marker = document.createElement('button');
                marker.type = 'button';
                marker.className = 'pa-guide';
                marker.setAttribute('data-prototype-owned', '');
                marker.__paTrig = trig;
                marker.style.setProperty('--g-delay', (-(gi++ % 4) * 0.45) + 's');
                marker.onclick = (e) => { e.stopPropagation(); revealThrough(marker.__paTarget); scheduleLayout(); };
                pinLayer.appendChild(marker);
            }
            marker.__paTarget = g.target;
            const html = `<span class="pa-guide-tag">${ICON}<span>${g.label} · ${g.notes.length}</span></span>`;
            if (marker.__paHtml !== html) { marker.innerHTML = html; marker.__paHtml = html; }
            const nums = g.notes.map(numberOf).join(' ');
            marker.title = `点击“${g.label}”以显示 ${g.notes.length} 处标注（${nums}）`;
            marker.setAttribute('aria-label', marker.title);
            marker.style.left = left + 'px'; marker.style.top = top + 'px';
            marker.style.width = (right - left) + 'px'; marker.style.height = (bottom - top) + 'px';
            marker.classList.toggle('pa-guide-below', top < 24);              // 贴顶时标签改挂底边，不被视口切掉
            marker.classList.toggle('pa-guide-end', left + 84 > viewWidth()); // 贴右时标签改挂右角
            alive.add(marker);
        });
        existing.forEach((m) => { if (!alive.has(m)) m.remove(); });
    }

    function startDrag(e, id, pin) {
        if (saving || e.button !== 0 || notes.find(n => n.id === id)?.confirmed) return;
        closeInputCard(true); hideHover(); selectNote(id);
        pin.focus({ preventScroll: true });
        drag = { id, pin, pointerId: e.pointerId, startX: e.clientX, startY: e.clientY,
            x: parseFloat(pin.style.left), y: parseFloat(pin.style.top), moved: false };
        pin.setPointerCapture(e.pointerId);
        e.stopPropagation();
    }

    function moveDrag(e) {
        if (!drag || drag.pointerId !== e.pointerId) return;
        const dx = e.clientX - drag.startX, dy = e.clientY - drag.startY;
        if (!drag.moved && Math.hypot(dx, dy) < 5) return;
        drag.moved = true;
        e.preventDefault();
        drag.pin.classList.add('pa-dragging');
        drag.pin.style.left = Math.max(4, Math.min(drag.x + dx, viewWidth() - drag.pin.offsetWidth - 4)) + 'px';
        drag.pin.style.top = Math.max(40, Math.min(drag.y + dy, viewHeight() - 4)) + 'px';
    }

    async function endDrag(e) {
        if (!drag || drag.pointerId !== e.pointerId) return;
        const d = drag;
        drag = null;
        d.pin.classList.remove('pa-dragging');
        if (d.pin.hasPointerCapture(d.pointerId)) d.pin.releasePointerCapture(d.pointerId);
        if (!d.moved) return;
        suppressedClick = d.id;
        setTimeout(() => { suppressedClick = null; }, 350);
        const x = parseFloat(d.pin.style.left), y = parseFloat(d.pin.style.top);
        const el = ProtoAnchors.at(x, y);
        saving = true;
        d.pin.setAttribute('aria-busy', 'true');
        try {
            await host()?.moveNote?.(d.id, el ? ProtoAnchors.serialize(el) : null, ProtoAnchors.placement(el, x, y));
        } finally {
            saving = false;
            d.pin.removeAttribute('aria-busy');
            layoutPins();
        }
    }

    function cancelDrag() {
        if (!drag) return;
        const d = drag;
        drag = null;
        suppressedClick = d.id;
        setTimeout(() => { suppressedClick = null; }, 350);
        d.pin.classList.remove('pa-dragging');
        if (d.pin.hasPointerCapture(d.pointerId)) d.pin.releasePointerCapture(d.pointerId);
        layoutPins();
    }

    function flashNote(id) {
        const note = notes.find((n) => n.id === id);
        if (!note) return false;
        let found = ProtoAnchors.point(note);
        let pendingReveal = false;
        if (!found.point) {
            // 目标被折叠/隐藏（Feature 2）：仅在确有显现路径时联动；无入口时把失败回传给右栏，不再静默假装定位成功。
            const hiddenEl = ProtoAnchors.resolveHidden?.(note.anchor);
            pendingReveal = !!ProtoAnchors.revealHint?.(note.anchor, hiddenEl);
            if (pendingReveal && revealThrough(note.anchor)) found = ProtoAnchors.point(note);
        }
        if (found.element) {
            found.element.scrollIntoView({ block: 'center', behavior: motion() });
        } else if (found.point) {
            window.scrollTo({ top: Math.max(0, found.point.y + window.scrollY - window.innerHeight / 2), behavior: motion() });
        }
        selectNote(id);
        layoutPins();
        setTimeout(layoutPins, 700);
        return !!found.point || pendingReveal;
    }

    // ---------- 生命周期 ----------

    function activate() {
        if (active) return;
        active = true;
        ensureLayers();
        const draft = host()?.getPickDraft?.();
        if (draft && !inputCard && !window.__paRebindId) {
            pending = { ...draft };
            openInputCard(pending.x, pending.y);
        }
        host()?.pickChanged?.(true);
        layoutPins();
    }

    function deactivate() {
        active = false;
        cancelDrag();
        if (pending) closeInputCard(true);
        window.__paRebindId = null;
        hideHover();
        host()?.pickChanged?.(false);
    }

    function startRebind(noteId) {
        closeInputCard(true);
        selectNote(noteId);
        window.__paRebindId = noteId;
        if (!active) activate();
    }

    /* 外观：父页设置（跟随系统 / 浅色 / 暗色）解析后下发 light|dark。只改气泡卡与序号层的 token；
       已打开的阅读卡重渲染以应用新主题，正在编辑的会话由父页 ProtoMarkdown.theme 统一切。 */
    function setTheme(theme) {
        ensureLayers();
        const value = theme === 'light' ? 'light' : 'dark';
        if (pinLayer.dataset.theme === value) return;
        pinLayer.dataset.theme = value;
        if (cardLayer?.dataset) cardLayer.dataset.theme = value;
        if (inputCard?.dataset.noteId && !host()?.markdown?.owns?.(inputCard)) {
            const note = notes.find(n => n.id === inputCard.dataset.noteId);
            if (note) host()?.renderNote?.(inputCard.querySelector('.pa-card-text'), note);
        }
    }

    /* 显隐：父页按当前模式下发。预览 / 微调看的是原型本身，序号层（含引导徽标与气泡卡）整层收起；
       切回带右栏的模式再显示，并立即重排一次——display:none 期间量不到 pin 宽度，靠 rAF 重排补不上。 */
    function setVisible(visible) {
        ensureLayers();
        const hidden = !visible;
        if (pinLayer.hasAttribute('data-hidden') === hidden) return;
        pinLayer.toggleAttribute('data-hidden', hidden);
        cardLayer?.toggleAttribute?.('data-hidden', hidden);
        if (!hidden) layoutPins();
    }

    let layoutTimer = null;
    function scheduleLayout() {
        // 重排只更新已保存序号的位置；不能隐藏正在跟随鼠标或已冻结在新落点旁的预览序号。
        // 原型 hover/动画引发 DOM 变化时 MutationObserver 会频繁进这里，旧逻辑无条件 hideHover 导致序号时有时无。
        if (layoutTimer) return;
        layoutTimer = requestAnimationFrame(() => { layoutTimer = null; layoutPins(); });
    }
    window.addEventListener('scroll', scheduleLayout, { passive: true, capture: true });
    window.addEventListener('resize', scheduleLayout, { passive: true });
    // 卡在父页文档：本页卸载（翻页 / 重载）时必须关掉，否则父页里留一张指向已销毁页面的孤卡
    window.addEventListener('pagehide', () => closeInputCard(true));
    document.addEventListener('proto-anchors:reveal-failed', () => {
        scheduleLayout();
        host()?.revealFailed?.();
    });
    /* 原型自身交互（点展开/收起、切页签、折叠侧栏）会改 DOM 但不触发 scroll/resize，以前序号与引导徽标就停在旧状态上：
       折回去后引导不重现、序号悬在空处直到下次滚动。现改为监听文档变动（过滤本层自有节点，否则自己重排自己死循环）与过渡/动画结束，
       rAF 节流重排，使引导与序号随原型状态即时增删。 */
    if (typeof MutationObserver !== 'undefined') {
        new MutationObserver((records) => { if (records.some((r) => !owned(r.target))) scheduleLayout(); })
            .observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ['class', 'style', 'hidden', 'open', 'aria-expanded', 'aria-hidden'] });
    }
    document.addEventListener('transitionend', (e) => { if (!owned(e.target)) scheduleLayout(); }, true);
    document.addEventListener('animationend', (e) => { if (!owned(e.target)) scheduleLayout(); }, true);

    window.ProtoAnnotate = { activate, deactivate, renderPins, layoutPins, flashNote, startRebind, selectNote, closeInputCard, setTheme, setVisible, openNoteId: () => inputCard?.dataset.noteId || null, cardOpen: () => !!inputCard, isActive: () => active, isBusy: () => saving || !!host()?.markdown?.isBusy() };
})();
