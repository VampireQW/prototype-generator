/* 工作台手动管理点击热区与标注展开路径；只保存元数据，不改原型 HTML。 */
(() => {
    'use strict';
    const clone = value => JSON.parse(JSON.stringify(value));
    const same = (a, b) => a?.protoId && b?.protoId ? a.protoId === b.protoId : !!a?.selector && a.selector === b?.selector;
    const model = {
        addTarget(scope, target) {
            const next = clone(scope || { mode: 'targets', protoIds: [] });
            next.manualTargets = (next.manualTargets || []).filter(item => !same(item.anchor, target.anchor));
            next.manualTargets.push(clone(target));
            next.excludedTargets = (next.excludedTargets || []).filter(item => !same(item.anchor, target.anchor));
            return next;
        },
        removeTarget(scope, target) {
            const next = clone(scope || { mode: 'targets', protoIds: [] });
            next.protoIds = (next.protoIds || []).filter(id => id !== target.anchor?.protoId);
            next.manualTargets = (next.manualTargets || []).filter(item => item.id !== target.id && !same(item.anchor, target.anchor));
            if (target.anchor?.protoId || target.anchor?.selector) {
                next.excludedTargets = (next.excludedTargets || []).filter(item => !same(item.anchor, target.anchor));
                const hash = JSON.stringify(target.anchor).split('').reduce((value, char) => Math.imul(value ^ char.charCodeAt(0), 16777619) >>> 0, 2166136261);
                next.excludedTargets.push({ id: target.id || 'excluded-' + hash.toString(16), anchor: clone(target.anchor) });
            }
            return next;
        },
        rebindTarget(scope, target, replacement) { return this.addTarget(this.removeTarget(scope, target), replacement); },
        setReveal(note, steps) {
            if (!note || note.confirmed) throw new Error('标注已确认，请先取消确认再编辑关联');
            const next = clone(note); next.anchor = { ...(next.anchor || {}) };
            if (steps.length) next.anchor.revealSteps = clone(steps); else delete next.anchor.revealSteps;
            return next;
        },
    };
    const STATUS = { ready: '可提示', missing: '目标丢失', duplicate: 'ID 重复', 'no-action': '未识别交互', container: '请选择具体控件', oversized: '范围过大', excluded: '已排除', disabled: '当前禁用', hidden: '当前隐藏', offscreen: '屏幕外', occluded: '被遮挡', unsupported: '不支持的节点', 'contains-target': '已使用内部控件', limit: '超出显示数量' };
    const safeAnchor = (A, el) => {
        const value = A.serialize(el), out = {};
        for (const key of ['protoId', 'selector', 'tag', 'text', 'parentText']) if (value[key] !== undefined) out[key] = value[key];
        return out;
    };
    function create(config) {
        const { container, trigger, frame } = config, doc = container.ownerDocument;
        let opened = false, tab = 'hotspots', edit = null, picking = null, busy = false, context = config.scopeKey();
        const element = (tag, className, text) => { const node = doc.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; };
        const button = (label, action, className = '') => { const node = element('button', className, label); node.type = 'button'; node.onclick = action; node.disabled = busy; return node; };
        const api = () => frame.contentWindow.ProtoHotspots;
        const anchors = () => { try { return frame.contentWindow.ProtoAnchors; } catch (_) { return null; } };
        const currentNote = () => config.notes().find(note => note.id === edit?.noteId);
        const say = (message, tone = 'info') => config.notice?.(message, tone);
        const guard = () => { if (context !== config.scopeKey()) { context = config.scopeKey(); cancelPick(); edit = null; } };
        async function saveScope(next) {
            if (busy) return false;
            const key = context; busy = true; render();
            try { return await config.saveScope(next, key); }
            catch (error) { say(error.message || '保存失败', 'warning'); return false; }
            finally { busy = false; guard(); render(); }
        }
        async function commitReveal(steps) {
            guard(); if (busy || !edit || currentNote()?.confirmed) return false;
            const draft = edit, key = context;
            draft.steps = clone(steps); draft.pending = null; draft.dirty = true; draft.error = ''; draft.testResult = null;
            draft.mode = steps.length ? draft.mode || 'manual' : '';
            busy = true; render();
            try {
                if (!await config.saveReveal(draft.noteId, clone(steps), key)) throw new Error('保存失败');
                draft.dirty = false; draft.saved = true; return true;
            } catch (error) { draft.error = (error.message || '保存失败') + '，本次修改尚未生效'; return false; }
            finally { busy = false; guard(); render(); }
        }
        function automaticReveal(note) {
            try {
                const A = anchors(), anchor = { ...note.anchor }; delete anchor.revealSteps;
                if (A?.inspectReveal) return A.inspectReveal(anchor);
                const target = A?.resolveHidden(anchor);
                if (!target) return { state: 'missing', reason: '目标暂未找到，请先检查标注绑定', steps: [] };
                if (!A.hidden(target)) return { state: 'visible', reason: '目标当前直接可见，无需添加展开入口', steps: [] };
                const hint = A.revealHint?.(anchor, target);
                if (hint?.sourceNoteIds?.length) {
                    const sources = hint.sourceNoteIds.map(id => config.notes().find(n => n.id === id)).filter(Boolean);
                    return { state: 'automatic', reason: '自动共用标注 ' + sources.map(n => n.displayNumber ?? n.number).join('、') + ' 的展开路径', steps: hint.target.revealSteps, sourceNoteIds: hint.sourceNoteIds };
                }
                return { state: hint ? 'automatic' : 'needed', reason: hint ? '已识别展开入口' : '未识别展开入口，可选择复用或手动添加', steps: hint ? [{ label: hint.label }] : [] };
            } catch (_) { return { state: 'waiting', reason: '等待原型页面加载后识别入口', steps: [] }; }
        }
        const REVEAL_STATE = { needed: '需补充入口', missing: '目标未找到', automatic: '自动识别', manual: '手动配置', visible: '当前无需展开', waiting: '等待识别' };
        const STEP_STATE = { ready: '当前可用', hidden: '入口当前隐藏', disabled: '入口禁用', missing: '入口未找到', duplicate: '入口定位不唯一' };
        function revealStatus(note) {
            if (!note.anchor?.revealSteps?.length) return automaticReveal(note);
            try { if (anchors()?.inspectReveal) return anchors().inspectReveal(note.anchor); } catch (_) { /* 页面加载期间保留配置 */ }
            return { state: 'manual', reason: '按手动配置的顺序展开', steps: note.anchor.revealSteps };
        }
        function badge(state) { const node = element('span', 'ei-badge', REVEAL_STATE[state] || state); node.dataset.state = state; return node; }
        function pathLabel(info) { return (info.steps || []).map(s => s.label || '展开').join(' → '); }
        function sourceLabel(info) {
            return info.sourceNoteIds?.length ? '共用标注 ' + info.sourceNoteIds.map(id => config.notes().find(n => n.id === id)).filter(Boolean).map(n => n.displayNumber ?? n.number).join('、') + ' 的路径' : info.source || '';
        }
        function resolve(anchor) { try { return anchors()?.resolveHidden(anchor); } catch (_) { return null; } }
        function locate(item) {
            const target = resolve(item.anchor);
            if (!target) { say('目标不存在，请重新绑定', 'warning'); return; }
            target.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
            const d = target.ownerDocument, overlay = d.createElement('div');
            overlay.dataset.prototypeOwned = ''; overlay.className = 'ei-target-preview';
            const r = target.getBoundingClientRect();
            overlay.style.cssText = `position:fixed;pointer-events:none;z-index:2147483000;left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px;background:#ff9f294d;border:2px solid #f59e0b;border-radius:5px;box-sizing:border-box`;
            d.documentElement.append(overlay); setTimeout(() => overlay.remove(), 1400);
        }
        function cancelPick() {
            if (!picking) return;
            picking.cleanup(); picking = null; config.picking?.(false); render();
        }
        function beginPick(kind, replaced = null) {
            guard(); cancelPick(); config.preparePick?.();
            let w, d, A;
            try { w = frame.contentWindow; d = w.document; A = w.ProtoAnchors; } catch (_) { /* frame navigating */ }
            if (!A || !w.ProtoHotspots) { say('页面尚未准备好，请稍后重试', 'warning'); return; }
            // 已有展开引导会覆盖业务按钮；点选期间让平台自有图层穿透，仍由窗口捕获拦截业务动作。
            const passthrough = d.createElement('style'); passthrough.dataset.prototypeOwned = '';
            passthrough.textContent = '[data-prototype-owned],[data-prototype-owned] *{pointer-events:none!important;}';
            d.documentElement.append(passthrough);
            const key = context, outline = d.createElement('div'); outline.dataset.prototypeOwned = '';
            outline.style.cssText = 'position:fixed;pointer-events:none;z-index:2147483000;border:2px solid #f59e0b;background:#ff9f2926;border-radius:5px;box-sizing:border-box;display:none';
            d.documentElement.append(outline); let hovered = null;
            const choose = raw => {
                if (!(raw instanceof w.Element) || A.owned(raw)) return null;
                return raw.closest('button,a[href],input,select,summary,[role="button"],[role="tab"],[role="switch"],[role="checkbox"],[data-proto-hotspot="true"],[onclick]') || raw;
            };
            const point = e => {
                hovered = choose(e.target); if (!hovered) { outline.style.display = 'none'; return; }
                const r = hovered.getBoundingClientRect(); outline.style.display = 'block';
                Object.assign(outline.style, { left: r.left + 'px', top: r.top + 'px', width: r.width + 'px', height: r.height + 'px' });
            };
            const block = e => { if (A.owned(e.target)) return; e.preventDefault(); e.stopImmediatePropagation(); };
            const pick = async e => {
                if (A.owned(e.target)) return;
                block(e); const target = choose(e.target);
                if (!target || key !== config.scopeKey()) { cancelPick(); return; }
                const check = w.ProtoHotspots.candidate(target);
                if (check.status !== 'ready') { say(STATUS[check.status] || '请选择可操作的具体控件', 'warning'); return; }
                if (kind === 'reveal' && /删除|清空|提交|支付|发布|导出|确定|保存|下单/.test(check.label)) { say('请选择用于展开或切换视图的入口', 'warning'); return; }
                const anchor = safeAnchor(A, target);
                cancelPick();
                if (kind === 'reveal') {
                    if (!edit) return;
                    const type = target.tagName === 'SELECT' ? 'select' : /^(checkbox|radio)$/.test(target.type) ? target.type : 'click';
                    const step = { ...anchor, kind: type, value: type === 'select' ? target.value : type === 'click' ? 'true' : true, label: check.label || '展开' };
                    edit.pending = { step, options: type === 'select' ? [...target.options].filter(o => !o.disabled).map(o => ({ value: o.value, text: o.textContent })) : null };
                    render(); return;
                }
                const entry = { id: replaced?.source === 'manual' ? replaced.id : crypto.randomUUID(), label: check.label || '交互控件', anchor };
                const next = replaced ? model.rebindTarget(config.scope(), replaced, entry) : model.addTarget(config.scope(), entry);
                if (await saveScope(next)) say(replaced ? '热区已重新绑定' : '热区已添加');
            };
            const escape = e => { if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); cancelPick(); } };
            d.addEventListener('pointermove', point, true);
            for (const event of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'touchend']) w.addEventListener(event, block, true);
            w.addEventListener('click', pick, true); w.addEventListener('keydown', escape, true); doc.addEventListener('keydown', escape, true);
            const unload = () => cancelPick(); w.addEventListener('pagehide', unload, { once: true });
            picking = { kind, cleanup() {
                d.removeEventListener('pointermove', point, true);
                for (const event of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'touchend']) w.removeEventListener(event, block, true);
                w.removeEventListener('click', pick, true); w.removeEventListener('keydown', escape, true); doc.removeEventListener('keydown', escape, true);
                w.removeEventListener('pagehide', unload); outline.remove(); passthrough.remove();
            } };
            config.picking?.(true); render();
        }
        function startReveal(noteId) {
            if (busy) return;
            guard(); cancelPick(); const note = config.notes().find(n => n.id === noteId);
            if (!note) return;
            opened = true; tab = 'reveal'; edit = { noteId, steps: clone(note.anchor?.revealSteps || []), dirty: false }; render();
        }
        function renderHotspots(body) {
            if (config.screenshot?.enabled()) {config.screenshot.render(body);return;}
            const actions = element('div', 'ei-actions');
            actions.append(button('＋ 添加热区', () => beginPick('hotspot'), 'ei-pick-action'), button('预览提示', () => { cancelPick(); config.preparePick?.(); api()?.hide(); api()?.show(); render(); })); body.append(actions);
            const info = element('p', 'ei-description', config.scope()?.mode === 'all' ? '当前提示全部交互。删除会单独排除该控件。' : '点击页面空白时，短暂高亮这些操作控件。'); body.append(info);
            let report;
            try { report = api()?.inspect(); } catch (_) { /* loading */ }
            const items = (report?.items || []).filter(item => item.status !== 'excluded');
            if (!items.length) body.append(element('div', 'ei-empty', report ? '暂无点击热区' : '等待原型页面加载…'));
            for (const item of items) {
                const row = element('div', 'ei-row'), text = element('div', 'ei-row-text'), title = element('strong', '', item.label || item.protoId || '交互控件');
                const status = element('span', 'ei-status', (item.source === 'manual' ? '手动 · ' : '') + (STATUS[item.status] || item.status)); status.dataset.status = item.status;
                text.append(title, status); row.append(text);
                row.append(button('定位', () => locate(item)), button('重绑', () => beginPick('hotspot', item)), button('删除', async () => {
                    if (await saveScope(model.removeTarget(config.scope(), item))) say('热区已删除');
                }, 'ei-danger')); body.append(row);
            }
        }
        function renderPending(body) {
            const pending = edit.pending, form = element('form', 'ei-step-form');
            const label = element('label', '', '引导文案'), input = element('input'); input.value = pending.step.label; input.maxLength = 120; input.required = true; label.append(input); form.append(label);
            let value = null;
            if (pending.step.kind !== 'click') {
                const valueLabel = element('label', '', pending.step.kind === 'select' ? '目标选项' : '目标状态'); value = element('select');
                for (const option of pending.options || [{ value: 'true', text: '开启 / 选中' }, { value: 'false', text: '关闭 / 取消' }]) {
                    const node = element('option', '', option.text); node.value = option.value; value.append(node);
                }
                value.value = String(pending.step.value); valueLabel.append(value); form.append(valueLabel);
            }
            const actions = element('div', 'ei-actions'), add = button('添加此步骤', null, 'ei-primary'); add.type = 'submit';
            actions.append(add, button('取消', () => { edit.pending = null; render(); })); form.append(actions);
            form.onsubmit = async e => { e.preventDefault(); if (busy || !edit || !input.value.trim()) return;
                const step = { ...pending.step, label: input.value.trim() };
                if (value) step.value = step.kind === 'select' ? value.value : value.value === 'true';
                if (edit.steps.some(s => same(s, step))) { say('该入口已在路径中', 'warning'); return; }
                await commitReveal([...edit.steps, step]);
            }; body.append(form);
        }
        function renderReveal(body) {
            anchors()?.setRevealNotes?.(config.notes());
            if (!edit) {
                const notes = config.notes(), reports = notes.map(revealStatus);
                const summary = element('div', 'ei-reveal-summary');
                for (const [state, label] of [['needed', '需处理'], ['automatic', '自动'], ['manual', '手动'], ['visible', '当前无需']]) {
                    const count = reports.filter(r => state === 'needed' ? ['needed', 'missing'].includes(r.state) : r.state === state).length;
                    const item = element('span', '', `${label} ${count}`); item.dataset.state = state; summary.append(item);
                }
                if (notes.length) body.append(summary, element('p', 'ei-description', '仅“需补充入口”需手动配置；自动识别的路径可直接使用。'));
                if (!notes.length) body.append(element('div', 'ei-empty', '添加标注后可设置展开联动'));
                for (const note of notes) {
                    const info = reports[notes.indexOf(note)], row = element('div', 'ei-row ei-reveal-row'), text = element('div', 'ei-row-text'); row.dataset.noteId = note.id;
                    const title = element('div', 'ei-note-title'); title.append(element('strong', '', '标注 ' + (note.displayNumber ?? note.number)), badge(info.state));
                    if (note.confirmed) title.append(element('span', 'ei-status', '已确认'));
                    text.append(title);
                    if (info.steps?.length) text.append(element('span', 'ei-path-preview', pathLabel(info)));
                    text.append(element('span', 'ei-status', info.sourceNoteIds?.length ? sourceLabel(info) : info.reason));
                    const label = info.state === 'manual' ? '编辑' : ['automatic', 'visible'].includes(info.state) ? '查看' : '设置';
                    const open = button(label, () => startReveal(note.id)); open.setAttribute('aria-label', `${label}标注 ${note.displayNumber ?? note.number} 的展开路径`);
                    row.append(text, open); body.append(row);
                } return;
            }
            const note = currentNote(); if (!note) { edit = null; render(); return; }
            const heading = element('div', 'ei-reveal-heading');
            const back = button('←', () => { cancelPick(); edit = null; render(); }, 'ei-back');
            back.setAttribute('aria-label', '返回标注列表'); back.title = '返回标注列表';
            heading.append(back, element('h3', '', `标注 ${note.displayNumber ?? note.number} · 展开路径`));
            body.append(heading);
            if (note.confirmed) body.append(element('p', 'ei-description', '标注已确认，可查看路径；取消确认后可修改。'));
            const sources = config.notes().filter(n => n.id !== note.id && n.anchor?.revealSteps?.length);
            {
                const modes = element('fieldset', 'ei-reveal-modes'); modes.append(element('legend', '', '展开方式'));
                const matched = sources.find(n => JSON.stringify(n.anchor.revealSteps) === JSON.stringify(edit.steps));
                const selected = edit.mode ?? matched?.id ?? (edit.steps.length ? 'manual' : '');
                const choices = [['', '自动识别'], ['manual', '手动路径']];
                for (const source of sources) {
                    choices.push([source.id, `复用标注 ${source.displayNumber ?? source.number}`, source.anchor.revealSteps.map(s => s.label || '展开').join(' → ')]);
                }
                for (const [value, text, path] of choices) {
                    const label = element('label', 'ei-radio-option'), input = element('input');
                    input.type = 'radio'; input.name = 'ei-reveal-mode'; input.value = value; input.checked = selected === value;
                    input.disabled = busy || !!note.confirmed || !!edit.pending; label.append(input, element('span', '', text));
                    if (path) label.title = path;
                    input.onchange = async () => {
                        guard(); if (!edit || busy || currentNote()?.confirmed || !input.checked) return;
                        const source = config.notes().find(n => n.id === value);
                        if (value && value !== 'manual' && !source?.anchor?.revealSteps?.length) { say('来源路径已变化，请重新选择', 'warning'); render(); return; }
                        cancelPick(); edit.mode = value;
                        if (value === 'manual' || !value && !edit.steps.length && !edit.dirty) { render(); return; }
                        await commitReveal(source?.anchor.revealSteps || []);
                    };
                    modes.append(label);
                }
                body.append(modes);
            }
            const automatic = !edit.steps.length && edit.mode !== 'manual' && automaticReveal(note);
            const result = automatic || (edit.steps.length ? revealStatus({ ...note, anchor: { ...note.anchor, revealSteps: edit.steps } }) : { state: 'needed', reason: '点选展开入口，添加后自动生效', steps: [] });
            const card = element('div', 'ei-reveal-result'); card.dataset.state = result.state; card.setAttribute('role', 'status');
            const resultTitle = element('div', 'ei-result-title'); resultTitle.append(element('strong', '', automatic ? '自动识别结果' : '手动展开路径'), badge(result.state));
            if (result.visible !== undefined) resultTitle.append(element('span', 'ei-status', result.visible ? '目标已显示' : result.rendered === false ? '目标未渲染' : '目标已隐藏'));
            card.append(resultTitle);
            const explanation = ['needed', 'missing', 'waiting'].includes(result.state) ? result.reason : result.sourceNoteIds?.length ? sourceLabel(result) : '';
            if (explanation) card.append(element('p', 'ei-description', explanation));
            body.append(card);
            const stepsList = element('div', 'ei-step-list'); (automatic ? card : body).append(stepsList);
            (automatic?.steps || edit.steps).forEach((step, index) => {
                const row = element('div', 'ei-row'), text = element('div', 'ei-row-text');
                const operation = step.kind === 'click' ? '点击展开' : `设置为 ${String(step.value)}`;
                text.append(element('strong', '', `${index + 1}. ${step.label}`), element('span', 'ei-status', [automatic ? '自动' : '手动', STEP_STATE[(automatic ? step : result.steps?.[index])?.status] || operation].join(' · '))); row.append(text);
                if (automatic) { stepsList.append(row); return; }
                const up = button('↑', () => { const steps = clone(edit.steps); [steps[index - 1], steps[index]] = [steps[index], steps[index - 1]]; return commitReveal(steps); }); up.disabled = busy || !!note.confirmed || index === 0; up.setAttribute('aria-label', '上移步骤');
                const down = button('↓', () => { const steps = clone(edit.steps); [steps[index + 1], steps[index]] = [steps[index], steps[index + 1]]; return commitReveal(steps); }); down.disabled = busy || !!note.confirmed || index === edit.steps.length - 1; down.setAttribute('aria-label', '下移步骤');
                const remove = button('删除', () => commitReveal(edit.steps.filter((_, i) => i !== index)), 'ei-danger'); remove.disabled = busy || !!note.confirmed;
                row.append(up, down, remove); stepsList.append(row);
            });
            if (edit.pending) renderPending(body);
            const footer = element('div', 'ei-actions ei-reveal-actions');
            if (!edit.pending) {
                const add = button('＋ 点选展开入口', () => beginPick('reveal'), 'ei-pick-action'); add.disabled = busy || !!note.confirmed || edit.steps.length >= 12; footer.append(add);
            }
            const test = button(edit.testing ? '测试中…' : '测试展开', async () => {
                const draft = edit, noteId = edit.noteId, steps = clone(edit.steps), key = context;
                draft.testing = true; draft.testResult = null; busy = true; render();
                try {
                    const result = await config.testReveal(noteId, steps, key);
                    if (edit === draft && key === config.scopeKey()) draft.testResult = {
                        ok: !!result?.ok,
                        message: result?.ok ? result.alreadyVisible ? '标注目标当前已显示' : '已展开并定位标注' : result?.message || '未能展开，请检查入口和目标绑定',
                    };
                } catch (error) {
                    if (edit === draft && key === config.scopeKey()) draft.testResult = { ok: false, message: error.message || '测试失败，请重试' };
                } finally { draft.testing = false; busy = false; guard(); render(); }
            }); test.disabled = busy || !!edit.pending || !!edit.dirty;
            footer.append(test);
            const saved = element('span', 'ei-status', busy && !edit.testing ? '正在保存…' : edit.error ? '' : edit.mode === 'manual' && !edit.steps.length ? '添加后生效' : edit.saved ? '已生效' : '自动保存'); saved.setAttribute('role', 'status'); footer.append(saved); body.append(footer);
            if (!edit.pending) body.append(element('p', 'ei-description ei-reveal-hint', automatic ? '手动添加会替代自动识别。' : '删空步骤后恢复自动识别。'));
            if (edit.testResult) {
                const status = element('p', 'ei-test-result', edit.testResult.message); status.setAttribute('role', 'status'); status.dataset.success = String(edit.testResult.ok); body.append(status);
            }
            if (edit.error) {
                const error = element('p', 'ei-test-result', edit.error); error.dataset.success = 'false'; error.setAttribute('role', 'alert'); body.append(error);
                const recovery = element('div', 'ei-actions'); recovery.append(button('重试', () => commitReveal(edit.steps)), button('放弃修改', () => { edit.steps = clone(currentNote()?.anchor?.revealSteps || []); delete edit.mode; edit.dirty = false; edit.error = ''; render(); })); body.append(recovery);
            }
        }
        let renderedKey = '', renderedView = '', pressed = false, deferredRefresh = false, gesture = 0;
        function viewKey() { return [context, opened, tab, edit?.noteId || '', !!edit?.pending].join('|'); }
        function snapshot() {
            if (!opened) return JSON.stringify([context, false]);
            const notes = config.notes(); let report = null;
            try { anchors()?.setRevealNotes?.(notes); report = tab === 'reveal' ? notes.map(revealStatus) : api()?.inspect(); } catch (_) { /* 加载期间 */ }
            return JSON.stringify([context, opened, tab, busy, picking?.kind, edit, notes, config.scope(), report]);
        }
        function render() {
            if(config.screenshot?.enabled() && tab === 'reveal') tab = 'hotspots';
            config.screenshot?.setActive(opened && tab === 'hotspots');
            guard(); container.hidden = !opened; trigger.setAttribute('aria-pressed', String(opened)); trigger.setAttribute('aria-expanded', String(opened));
            const view = viewKey(), previousScroll = view === renderedView ? container.querySelector?.('.ei-body')?.scrollTop || 0 : 0;
            deferredRefresh = false; container.replaceChildren(); renderedView = view;
            if (!opened) { renderedKey = snapshot(); return; }
            const header = element('div', 'ei-header'); header.append(element('strong', '', '交互提示'), button('关闭', () => close())); container.append(header);
            const tabs = element('div', 'ei-tabs'); tabs.setAttribute('role', 'tablist');
            for (const [id, label] of [['hotspots', '点击热区'], ['reveal', '展开联动']]) {
                if(id === 'reveal' && config.screenshot?.enabled()) continue;
                const node = button(label, () => { cancelPick(); tab = id; render(); }); node.setAttribute('role', 'tab'); node.setAttribute('aria-selected', String(tab === id)); tabs.append(node);
            } container.append(tabs);
            if (picking) { const banner = element('div', 'ei-picking'); banner.setAttribute('role', 'status'); banner.append(element('span', '', picking.kind === 'reveal' ? '在原型中点选展开入口' : '在原型中点选具体操作控件'), button('取消 · Esc', cancelPick)); container.append(banner); }
            const body = element('div', 'ei-body'); container.append(body); tab === 'hotspots' ? renderHotspots(body) : renderReveal(body);
            body.scrollTop = previousScroll; renderedKey = snapshot();
        }
        // 后台刷新不撤换正在操作的控件；无语义变化时不重建 DOM，避免吞掉 pointerdown 与 click 之间的点击。
        function refresh() {
            guard();
            if (pressed || picking || edit?.pending || busy || (['INPUT', 'SELECT', 'TEXTAREA'].includes(doc.activeElement?.tagName) && container.contains(doc.activeElement))) { deferredRefresh = true; return; }
            if (!config.screenshot?.enabled() && renderedKey === snapshot()) return;
            render();
        }
        const afterGesture = () => {
            if (!pressed && !deferredRefresh) return;
            const released = gesture;
            requestAnimationFrame(() => { if (released !== gesture) return; pressed = false; if (deferredRefresh) refresh(); });
        };
        doc.addEventListener('pointerdown', event => { if (container.contains(event.target)) { pressed = true; gesture++; } }, true);
        doc.addEventListener('pointerup', afterGesture, true);
        doc.addEventListener('pointercancel', afterGesture, true);
        doc.addEventListener('keydown', event => { if (container.contains(event.target) && ['Enter', ' '].includes(event.key)) { pressed = true; gesture++; } }, true);
        doc.addEventListener('keyup', afterGesture, true);
        container.addEventListener('focusout', () => { if (deferredRefresh) requestAnimationFrame(refresh); });
        doc.defaultView?.addEventListener('blur', afterGesture);
        function close() { if (busy) return; cancelPick(); opened = false; render(); }
        trigger.onclick = () => { if (opened) close(); else { context = config.scopeKey(); opened = true; render(); } };
        let visibilityObserver = null, visibilityFrame = 0;
        function watchVisibility() {
            visibilityObserver?.disconnect();
            if (typeof MutationObserver === 'undefined') return;
            try {
                visibilityObserver = new MutationObserver(records => {
                    if (visibilityFrame || !records.some(r => !r.target.closest?.('[data-prototype-owned]'))) return;
                    visibilityFrame = requestAnimationFrame(() => {
                        visibilityFrame = 0;
                        if (opened && tab === 'reveal') refresh();
                    });
                });
                visibilityObserver.observe(frame.contentWindow.document.documentElement, { subtree: true, childList: true, attributes: true,
                    attributeFilter: ['class', 'style', 'hidden', 'open', 'aria-expanded', 'aria-hidden', 'disabled', 'aria-disabled', 'aria-controls', 'role', 'data-proto-reveal-by', 'data-proto-reveal-label', 'data-proto-reveal-value'] });
            } catch (_) { /* 原型正在导航或已离开同源页面 */ }
        }
        frame.addEventListener('load', () => { cancelPick(); edit = null; context = config.scopeKey(); watchVisibility(); if (opened) render(); });
        watchVisibility();
        render();
        return { refresh, close, openReveal: startReveal, cancelPick, isPicking: () => !!picking || !!config.screenshot?.isDrawing() };
    }
    window.ProtoInteractions = { model, create };
})();
