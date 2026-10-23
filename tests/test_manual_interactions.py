"""Persisted manual hotspot edits and reveal paths, without touching private prototypes."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import proto_meta


def model_case(code):
    source = (ROOT / 'src/proto-interactions.js').read_text(encoding='utf-8')
    script = "const vm=require('node:vm'),assert=require('node:assert/strict'),ctx={};ctx.window=ctx;vm.createContext(ctx);vm.runInContext(" + json.dumps(source) + ",ctx);const M=ctx.ProtoInteractions.model;const normalize=x=>JSON.parse(JSON.stringify(x));" + code
    result = subprocess.run([shutil.which('node'), '-'], input=script, text=True, encoding='utf-8', capture_output=True)
    assert result.returncode == 0, result.stderr


def test_manual_hotspot_add_is_precise_idempotent_and_can_restore_exclusion():
    model_case("""
const scope={mode:'targets',protoIds:['old'],excludedTargets:[{id:'excluded',anchor:{protoId:'save',selector:'#save'}}]};
const target={id:'manual-save',label:'保存',anchor:{protoId:'save',selector:'#save',tag:'button'}};
const once=M.addTarget(scope,target),twice=M.addTarget(once,target);
assert.equal(twice.manualTargets.length,1);assert.equal(twice.excludedTargets.length,0);
assert.deepEqual(normalize(twice.protoIds),['old']);assert.equal(scope.manualTargets,undefined);
""")


def test_delete_in_all_mode_is_a_persistent_precise_exclusion():
    model_case("""
const target={id:'save',source:'automatic',protoId:'save',anchor:{protoId:'save',selector:'#save'}};
const result=M.removeTarget({mode:'all'},target);
assert.equal(result.mode,'all');assert.equal(result.excludedTargets[0].anchor.protoId,'save');
assert.equal(M.removeTarget(result,target).excludedTargets.length,1);
""")


def test_rebind_removes_old_mapping_and_keeps_unrelated_hotspots():
    model_case("""
const old={id:'old',source:'declared',protoId:'old',anchor:{protoId:'old',selector:'#old'}};
const replacement={id:'manual-new',label:'新入口',anchor:{protoId:'new',selector:'#new',tag:'button'}};
const result=M.rebindTarget({mode:'targets',protoIds:['old','other']},old,replacement);
assert.deepEqual(normalize(result.protoIds),['other']);assert.equal(result.manualTargets[0].anchor.protoId,'new');
assert.equal(result.excludedTargets[0].anchor.protoId,'old');
""")


def test_manual_reveal_changes_only_anchor_and_preserves_prd():
    model_case("""
const original={id:'note',body:'用户手写 PRD',number:3,anchor:{protoId:'target',conditions:[{selector:'#old'}]}};
const steps=[{selector:'#open',kind:'click',value:'true',label:'打开分组'}];
const result=M.setReveal(original,steps);
assert.equal(result.body,original.body);assert.equal(result.number,3);assert.equal(result.anchor.revealSteps[0].selector,'#open');
assert.equal(original.anchor.revealSteps,undefined);assert.equal(M.setReveal(result,[]).anchor.revealSteps,undefined);
assert.throws(()=>M.setReveal({...original,confirmed:true},steps));
""")


@pytest.fixture
def bundle(tmp_path):
    (tmp_path / 'index.html').write_text('<html><button>配置</button></html>', encoding='utf-8')
    data = proto_meta.ensure_bundle(tmp_path)
    proto_meta.ensure_pages_registered(tmp_path, data)
    return data


@pytest.mark.parametrize('target', [
    {'id': 'manual', 'label': '配置', 'anchor': {'selector': '#config', 'tag': 'button'}},
    {'id': 'manual', 'anchor': {'protoId': 'config'}},
])
def test_metadata_accepts_manual_targets_and_exclusions(bundle, target):
    bundle['project']['pages'][0]['states'][0]['interactionHints'] = {'mode': 'targets', 'protoIds': [], 'manualTargets': [target], 'excludedTargets': [target]}
    proto_meta.validate_bundle(bundle)


@pytest.mark.parametrize('field,value', [
    ('manualTargets', 'bad'), ('manualTargets', [{'id': 'x', 'anchor': {}}]),
    ('manualTargets', [{'id': 'x', 'anchor': {'selector': '#a'}}, {'id': 'x', 'anchor': {'selector': '#b'}}]),
    ('excludedTargets', [{'id': 'x', 'anchor': {'selector': 5}}]),
])
def test_metadata_rejects_invalid_manual_target_payloads(bundle, field, value):
    bundle['project']['pages'][0]['states'][0]['interactionHints'] = {'mode': 'targets', 'protoIds': [], field: value}
    with pytest.raises(ValueError, match='热区|定位'):
        proto_meta.validate_bundle(bundle)


@pytest.mark.parametrize('steps', [
    [{'selector': '#open', 'kind': 'unknown', 'value': 'true'}],
    [{'selector': '#check', 'kind': 'checkbox', 'value': 'true'}],
    [{'selector': '#open', 'kind': 'click', 'value': 'true'}] * 2,
])
def test_metadata_rejects_invalid_reveal_paths(bundle, steps):
    page = bundle['project']['pages'][0]
    bundle['prd']['annotations'] = [{'id': 'n', 'pageId': page['id'], 'stateId': 'default', 'number': 1,
                                     'anchor': {'protoId': 'target', 'revealSteps': steps}, 'body': '保持原文'}]
    with pytest.raises(ValueError, match='展开|入口'):
        proto_meta.validate_bundle(bundle)
