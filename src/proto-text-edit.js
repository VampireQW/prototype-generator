/* 文案微调：静态文字精确改源码，脚本生成文字按稳定控件键保存。 */
(() => {
    'use strict';
    const blocked = new Set('SCRIPT STYLE TEMPLATE NOSCRIPT SVG MATH CANVAS IFRAME OBJECT TEXTAREA'.split(' '));
    const allowed = new Set('BUTTON A LABEL SPAN P H1 H2 H3 H4 H5 H6 TD TH OPTION LEGEND SMALL STRONG EM B I LI DT DD SUMMARY DIV'.split(' '));
    const textNodes = element => {
        const out = [];
        const visit = node => {
            if (node.nodeType === 3) { if (node.nodeValue.trim()) out.push({ node, before: node.nodeValue }); return; }
            if (blocked.has(node.tagName?.toUpperCase())) return;
            for (const child of node.childNodes || []) visit(child);
        };
        visit(element); return out;
    };
    function describe(element) {
        if (element?.ownerDocument?.documentElement?.dataset.protoScreenshot === 'true') throw Error('截图内的文字请通过更换截图修改');
        if (!element) throw Error('请选择一个元素');
        let nodes = textNodes(element);
        if (!nodes.length) {
            const parent = element.parentElement?.closest('button,a,label,td,th');
            if (parent) { element = parent; nodes = textNodes(parent); }
        }
        if (!allowed.has(element.tagName) || !nodes.length || nodes.length > 8) throw Error('请选择具体文字或单元格，复杂调整请使用 AI 修改');
        for (let node = element; node; node = node.parentElement) {
            if (node.__vue__ || node.__vueParentComponent || Object.keys(node).some(k => k.startsWith('__reactFiber$'))) throw Error('这个内容由程序生成，请使用 AI 修改');
        }
        const path = [];
        for (let node = element; node?.nodeType === 1; node = node.parentElement) {
            let index = 1;
            for (let sibling = node.previousElementSibling; sibling; sibling = sibling.previousElementSibling) if (sibling.tagName === node.tagName) index++;
            path.unshift({ tag: node.tagName.toLowerCase(), index });
        }
        return { nodes, target: { tag: element.tagName.toLowerCase(), protoId: element.getAttribute('data-proto-id') || '', id: element.getAttribute('id') || '', path,
            texts: nodes.map(item => item.before.trim()), bindings: (element.ownerDocument?.defaultView?.ProtoTextRuntime || window.ProtoTextRuntime)?.bindings(element) || [] } };
    }

    function create(config) {
        const host = config.container, doc = host.ownerDocument;
        let model = null, sequence = 0, busy = false;
        const el = (tag, role, text) => { const node = doc.createElement(tag); if (role) node.dataset.role = role; if (text) node.textContent = text; return node; };
        const pickerLabel = el('label', '', '选择文案'), picker = el('select', 'field'); pickerLabel.append(picker);
        const original = el('p', 'original'); original.className = 'inspector-text-original';
        const inputLabel = el('label', '', '新文案'), input = el('textarea', 'text'); input.rows = 3; input.maxLength = 4096; input.placeholder = '输入新的文案'; inputLabel.append(input);
        const status = el('p', 'status'); status.className = 'inspector-text-status'; status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
        const actions = el('div'); actions.className = 'inspector-text-actions';
        const save = el('button', 'save', '保存修改'), cancel = el('button', 'cancel', '取消修改'), undo = el('button', 'undo', '撤销上次修改');
        for (const button of [save, cancel, undo]) button.type = 'button';
        save.className = 'inspector-text-save'; actions.append(save, cancel, undo); host.replaceChildren(pickerLabel, original, inputLabel, status, actions);
        const message = (text, error = false) => { status.textContent = text; status.dataset.tone = error ? 'error' : 'normal'; };
        const scopeKey = value => JSON.stringify(value);
        const dirty = () => !!model && model.fields.some((field, i) => model.values[i] !== field.text);
        const valid = value => value && scopeKey(config.scope()) === value.key && value.nodes.every(item => item.node.isConnected !== false);
        const restore = value => { for (const item of value?.nodes || []) if (item.node.isConnected !== false) item.node.nodeValue = item.before; };
        function controls() {
            const ready = !!model?.fields;
            input.disabled = picker.disabled = !ready || busy;
            save.disabled = !ready || !dirty() || busy;
            cancel.disabled = !ready || !dirty() || busy;
            undo.disabled = !ready || !model.undoId || dirty() || busy;
            undo.title = dirty() ? '先保存或取消当前修改' : '撤销后刷新原型';
            save.textContent = busy ? '处理中…' : '保存修改';
        }
        function field() {
            const index = Number(picker.value || 0);
            if (!model?.fields[index]) return;
            input.value = model.values[index]; original.textContent = '当前文案：' + model.fields[index].text;
        }
        function fill() {
            picker.replaceChildren();
            if (!model?.fields) { input.value = ''; original.textContent = ''; pickerLabel.hidden = true; controls(); return; }
            model.fields.forEach((value, i) => { const option = el('option', '', `${i+1}. ${value.text.slice(0, 36)}`); option.value = String(i); picker.append(option); });
            picker.value = '0'; pickerLabel.hidden = model.fields.length < 2; field(); controls();
        }
        function close() {
            sequence++;
            if (!busy) restore(model);
            model = null; fill();
        }
        async function select(elements) {
            if (busy) return false;
            close(); const ticket = sequence, scope = config.scope();
            try {
                if (!scope?.projectId || !scope.pageId) throw Error('请从项目工作台打开原型后再手动修改');
                if (elements.length !== 1) throw Error('手动修改请选择一个元素；批量调整请使用 AI 修改');
                const described = describe(elements[0]); message('正在核对源文件…');
                const result = await config.request('inspect', { ...scope, target: described.target });
                if (ticket !== sequence || scopeKey(config.scope()) !== scopeKey(scope)) return false;
                if (!result.ok) throw Error(result.error || '源文件读取失败');
                if (result.fields.length !== described.nodes.length) throw Error('文案结构已变化，请重新选择');
                model = { ...described, scope, key: scopeKey(scope), hash: result.hash, file: result.file, fields: result.fields,
                    values: result.fields.map(f => f.text), undoId: result.undoId };
                fill(); message('保存到 ' + result.file); return true;
            } catch (error) { if (ticket === sequence) { message(error.message || '暂不支持手动修改，请使用 AI 修改', true); controls(); } return false; }
        }
        picker.onchange = field;
        input.oninput = () => {
            if (!valid(model)) { message('页面已变化，请重新选择', true); return; }
            const index = Number(picker.value || 0), item = model.nodes[index]; model.values[index] = input.value;
            const prefix = item.before.match(/^\s*/)[0], suffix = item.before.match(/\s*$/)[0];
            item.node.nodeValue = prefix + input.value + suffix;
            message('预览中，尚未保存'); controls();
        };
        cancel.onclick = () => {
            if (busy || !model) return;
            restore(model); model.values = model.fields.map(f => f.text); field(); controls(); message('已取消未保存的修改');
        };
        save.onclick = async () => {
            if (!model || busy) return;
            const current = model;
            try {
                if (!valid(current)) throw Error('页面已变化，请重新选择后再保存');
                const edits = current.fields.flatMap((f, i) => current.values[i] === f.text ? [] : [{ slot: f.slot, text: current.values[i] }]);
                if (!edits.length) return;
                busy = true; controls();
                const result = await config.request('save', { ...current.scope, target: { ...current.target, texts: [...current.target.texts] }, expectedHash: current.hash, edits });
                if (!result.ok) throw Error(result.error || '保存失败');
                current.hash = result.hash; current.undoId = result.undoId; current.fields = result.fields;
                current.target.texts = result.fields.map(f => f.text); current.values = result.fields.map(f => f.text);
                for (const item of current.nodes) item.before = item.node.nodeValue;
                if (result.runtimeEdits) {
                    const doc = current.nodes[0].node.ownerDocument;
                    (doc.defaultView?.ProtoTextRuntime || window.ProtoTextRuntime)?.install(doc, result.runtimeEdits);
                }
                if (model === current) { field(); message('已保存到 ' + current.file); }
                config.onSaved?.(result);
            } catch (error) {
                if (model === current) message(error.message || '保存失败，预览仍保留', true);
                else restore(current);
            } finally { busy = false; controls(); }
        };
        undo.onclick = async () => {
            if (!model?.undoId || dirty() || busy) return;
            const current = model;
            try {
                if (!valid(current)) throw Error('页面已变化，请重新选择');
                busy = true; controls();
                const result = await config.request('undo', { ...current.scope, undoId: current.undoId, expectedHash: current.hash });
                if (!result.ok) throw Error(result.error || '撤销失败');
                busy = false; close(); config.onUndo?.(result);
            } catch (error) { if (model === current) message(error.message || '撤销失败', true); }
            finally { busy = false; controls(); }
        };
        input.onkeydown = event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); save.onclick(); } };
        controls();
        return { select, close, isBusy: () => busy, hasChanges: dirty };
    }
    window.ProtoTextEdit = { describe, create };
})();
