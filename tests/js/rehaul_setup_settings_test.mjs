// The three tools moved out of setup must work at their Settings destination.
// Execute real DOM handlers and authFetch against endpoint fixtures only.
import assert from 'node:assert/strict';
import { setup, tick, deferred, page, authLogic } from './rehaul_settings_test.mjs';

const pricing = {display_model:'Fixture model <text>',est_per_video:{ci:0.012,hook:0.003,both:0.015}};
const prompt = 'You are the Uoink operator.\n\nUse the local library.\n<instructions>Preserve exact text.</instructions>\n';
const corrections = [
  {title:'Opening <img src=x>',original_hook_type:'story_open',corrected_hook_type:'curiosity_gap',corrected_at:'2026-10-15T12:00:00Z',folder:'C:/Fixture/One & two'},
  {video_title:'Second',previous_hook_type:'question',hook_type:'list',session_folder:'C:/Fixture/Second'},
  {slug:'third',from_hook_type:'question',to_hook_type:'story_open',output_folder:'C:/Fixture/Third'},
  {title:'No path',original_hook_type:'question',hook_type:'list'},
];

function fixture() {
  const p=setup(), requests=[], copies=[];
  let transport=async path=>{
    if(path==='/settings/pricing') return {ok:true,pricing};
    if(path==='/search/status') return {ok:true,state:'not_installed',enabled:false,accepted:false};
    if(path==='/taxonomy/corrections?limit=20') return {ok:true,total:4,corrections};
    if(path==='/skill/system-prompt') return prompt;
    if(path.startsWith('/open-folder?path=')) return {ok:true};
    if(path==='/settings') return {ok:true,settings:{anthropic_key_set:true,comment_intelligence_enabled:true,hook_type_enabled:true}};
    throw new Error('Unexpected fixture request: '+path);
  };
  p.c.getToken=async()=>p.state.token || (p.state.token='refreshed-token');
  p.c.fetch=async(path,opts={})=>{
    assert.ok(opts.signal,'requests are bounded and cancellable');
    assert.ok(opts.headers['X-Uoink-Token'],'real authenticated transport');
    assert.equal(opts.responseType,undefined,'responseType is not a fetch option');
    requests.push({path,token:opts.headers['X-Uoink-Token']});
    const result=await transport(path,opts);
    return result?.http || {ok:true,status:200,text:async()=>typeof result==='string'?result:JSON.stringify(result)};
  };
  p.c.navigator={clipboard:{writeText:async text=>copies.push(text)}};
  p.run(authLogic);
  return {...p,requests,copies,el:id=>p.nodes.get(id),transport:fn=>{transport=fn;}};
}
const httpError=(status,message)=>({http:{ok:false,status,text:async()=>JSON.stringify({ok:false,error:message})}});
const content = el => [el.textContent,...el.children.map(content)].join(' ');
const buttons = el => el.children.filter(child=>child.tagName==='BUTTON');
function sectionContains(section,id) {
  const start=page.indexOf(`id="settings-${section}"`),end=page.indexOf('</section>',start);
  assert.ok(page.slice(start,end).includes(`id="${id}"`),`${id} is reachable in Settings ${section}`);
}

const groups={
  async autosave() {
    const p=fixture(), saved=[];
    p.c.hydrateSettings({settings:{anthropic_key_set:true,comment_intelligence_enabled:true,hook_type_enabled:true,notifications_enabled:true}},{});
    await p.c.loadAIPricing();
    p.transport(async(path,opts)=>{
      assert.equal(path,'/settings');
      assert.equal(opts.method,'POST');
      const body=JSON.parse(opts.body);
      saved.push(body);
      return {ok:true,settings:body};
    });
    const estimate=p.el('aiCostEstimate').textContent;
    p.change('notificationsEnabled',false);await p.flush();
    assert.deepEqual(saved,[{notifications_enabled:false}]);
    assert.equal(p.el('notificationsEnabledSaveStatus').textContent,'Saved');
    assert.equal(p.el('aiCostEstimate').textContent,estimate);
    p.change('hookTypeToggle',false);await p.flush();
    assert.deepEqual(saved,[{notifications_enabled:false},{hook_type_enabled:false}]);
    assert.equal(p.el('hookTypeToggleSaveStatus').textContent,'Saved');
    assert.doesNotMatch(p.el('aiCostEstimate').textContent,/Hook Type/);
    assert.equal(p.el('notificationsEnabled').checked,false);
    assert.equal(p.requests.filter(r=>r.path==='/settings/pricing').length,1);
  },
  async pricing() {
    sectionContains('ai','aiCostEstimate');
    const p=fixture();await p.c.loadAIPricing();
    const estimate=p.el('aiCostEstimate');
    assert.ok(estimate.classList.contains('hidden'),'hidden without a key or feature');
    p.c.hydrateSettings({settings:{anthropic_key_set:true,comment_intelligence_enabled:true,hook_type_enabled:true}},{});
    assert.equal(estimate.classList.contains('hidden'),false);
    assert.match(estimate.textContent,/≈ \$0\.01 estimated per video/);
    assert.match(estimate.textContent,/Comment Intelligence \$0\.01 \+ Hook Type \$0\.003/);
    assert.ok(estimate.textContent.includes(pricing.display_model),'model text is literal');
    assert.equal(estimate.innerHTML,'','endpoint strings never become HTML');
    p.transport(async(path,opts)=>({ok:true,settings:JSON.parse(opts.body)}));
    p.change('commentIntelligenceToggle',false);await p.flush();
    assert.match(estimate.textContent,/≈ \$0\.003 estimated per video/);
    assert.doesNotMatch(estimate.textContent,/Comment Intelligence/);
    p.change('hookTypeToggle',false);await p.flush();
    assert.ok(estimate.classList.contains('hidden'));
    p.change('commentIntelligenceToggle',true);await p.flush();
    assert.match(estimate.textContent,/≈ \$0\.01 estimated per video/);
    p.transport(async()=>({ok:true,settings:{anthropic_key_set:false}}));
    p.el('clearKey').emit('click');await p.flush();
    assert.ok(estimate.classList.contains('hidden'),'removing the key hides the estimate');
    p.el('anthropicKey').value='sk-ant-fixture';p.el('anthropicKey').emit('input');
    assert.equal(estimate.classList.contains('hidden'),false,'preview for a newly typed key matches old setup');
    p.el('anthropicKey').value='';p.el('anthropicKey').emit('input');
    assert.ok(estimate.classList.contains('hidden'));
    assert.equal(p.requests.filter(r=>r.path==='/settings/pricing').length,1,'toggles do not repeatedly fetch pricing');
  },
  async corrections() {
    sectionContains('ai','hookCorrectionsList');
    const p=fixture();p.el('reloadHookCorrections').emit('click');await tick();
    const list=p.el('hookCorrectionsList');
    assert.equal(list.children.length,4);
    assert.match(p.el('hookCorrectionsStatus').textContent,/4 corrections/);
    assert.match(content(list.children[0]),/Opening <img src=x>.*story open → curiosity gap/);
    assert.equal(list.children[0].children[0].innerHTML,'','titles cannot inject markup');
    for(let i=0;i<3;i++) {
      const button=buttons(list.children[i])[0];assert.equal(button.textContent,'Open folder');
      button.emit('click');await tick();
      assert.equal(p.requests.at(-1).path,'/open-folder?path='+encodeURIComponent(['C:/Fixture/One & two','C:/Fixture/Second','C:/Fixture/Third'][i]));
      assert.match(content(list.children[i]),/Folder opened/);assert.equal(button.disabled,false);
    }
    assert.equal(buttons(list.children[3]).length,0,'missing paths never make dead actions');
    p.transport(async()=>httpError(500,'Folder no longer exists'));
    buttons(list.children[0])[0].emit('click');await tick();
    assert.match(content(list.children[0]),/Could not open folder: Folder no longer exists/);
    for(const key of ['corrections','items','results']) {
      p.transport(async()=>({ok:true,[key]:Array.from({length:25},()=>corrections[0]),total:25}));
      await p.c.loadHookCorrections();assert.equal(list.children.length,20);
    }
    p.transport(async()=>({ok:true,corrections:[]}));await p.c.loadHookCorrections();
    assert.equal(list.children.length,0);assert.match(p.el('hookCorrectionsStatus').textContent,/No corrections yet/);
  },
  async prompt() {
    sectionContains('agents','skillSystemPrompt');sectionContains('agents','copySkillPrompt');
    const p=fixture();p.el('reloadSkillPrompt').emit('click');await tick();
    assert.equal(p.el('skillSystemPrompt').value,prompt);
    assert.equal(p.el('copySkillPrompt').disabled,false);
    p.el('copySkillPrompt').emit('click');await tick();
    assert.deepEqual(p.copies,[prompt]);assert.equal(p.el('skillPromptStatus').textContent,'System prompt copied.');
    p.c.navigator.clipboard.writeText=async()=>{throw new Error('Clipboard blocked');};
    p.el('copySkillPrompt').emit('click');await tick();
    assert.match(p.el('skillPromptStatus').textContent,/Copy failed.*copy it manually/);
    assert.equal(p.el('copySkillPrompt').disabled,false);
    p.transport(async()=>httpError(503,'Prompt unavailable'));await p.c.loadSkillSystemPrompt();
    assert.equal(p.el('skillSystemPrompt').value,'');assert.equal(p.el('copySkillPrompt').disabled,true);
    p.el('copySkillPrompt').emit('click');await tick();assert.deepEqual(p.copies,[prompt],'never copy error text');
    assert.match(p.el('skillPromptStatus').textContent,/Prompt unavailable/);
    p.transport(async()=>'');await p.c.loadSkillSystemPrompt();
    assert.equal(p.el('copySkillPrompt').disabled,true);assert.match(p.el('skillPromptStatus').textContent,/Empty response from helper/);
  },
  async resources() {
    for(const [load,status] of [['loadAIPricing','aiCostEstimate'],['loadHookCorrections','hookCorrectionsStatus'],['loadSkillSystemPrompt','skillPromptStatus']]) {
      const p=fixture();p.c.hydrateSettings({settings:{anthropic_key_set:true,hook_type_enabled:true}},{});
      p.transport(async()=>httpError(403,'Authorization expired sk-ant-fixture-secret'));
      await p.c[load]();assert.equal(p.requests.length,2,'refresh token only once');
      assert.deepEqual(p.requests.map(r=>r.token),['fake-token','refreshed-token']);
      assert.match(p.el(status).textContent,/Authorization expired \[redacted key\]/);
      assert.doesNotMatch(p.el(status).textContent,/sk-ant-fixture/);
      p.transport(async()=>{throw Object.assign(new Error('Aborted'),{name:'AbortError'});});
      await p.c[load]();assert.match(p.el(status).textContent,/helper did not respond/);
    }
    const p=fixture();let tries=0;
    p.transport(async()=>++tries===1?httpError(403,'expired'):prompt);
    await p.c.loadSkillSystemPrompt();assert.equal(p.el('skillSystemPrompt').value,prompt);
  },
  async reload() {
    const p=fixture();
    for(const fn of ['loadSettingsMcp','loadTasteSettings','loadPlaylistSettings','loadPodcastFeedSettings','loadChannels','loadAllowedSites','loadAgentSetup']) p.c[fn]=async()=>{};
    await p.c.refreshSettings();
    assert.deepEqual(new Set(p.requests.map(r=>r.path)),new Set(['/settings','/settings/pricing','/taxonomy/corrections?limit=20','/skill/system-prompt','/search/status']));
    assert.equal(p.el('aiCostEstimate').classList.contains('hidden'),false);
    assert.equal(p.el('hookCorrectionsList').children.length,4);
    assert.equal(p.el('skillSystemPrompt').value,prompt);
    for(const [load,older,newer,read] of [
      ['loadAIPricing',{ok:true,pricing:{...pricing,display_model:'Old'}},{ok:true,pricing:{...pricing,display_model:'New'}},()=>p.el('aiCostEstimate').textContent],
      ['loadHookCorrections',{ok:true,corrections:[{title:'Old'}]},{ok:true,corrections:[{title:'New'}]},()=>content(p.el('hookCorrectionsList'))],
      ['loadSkillSystemPrompt','Old','New',()=>p.el('skillSystemPrompt').value],
    ]) {
      const pending=deferred();let first=true;
      p.transport(async()=>first?(first=false,pending.promise):newer);
      const old=p.c[load]();await tick();await p.c[load]();pending.resolve(older);await old;
      assert.match(read(),/New/);assert.doesNotMatch(read(),/Old/);
    }
  },
};
const group=process.argv[2];assert.ok(groups[group],group);await groups[group]();console.log('PASS '+group);
