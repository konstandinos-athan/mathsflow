// Unit tests for settings behavior; no browser or network access.
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = readFileSync(require('node:path').join(__dirname, '../static/js/script.js'), 'utf8');
function fixture(blocked) {
    const handlers = {};
    let writes = 0;
    function element(id) {
        const classes = new Set();
        return {id, hidden:true, attributes:{}, focused:false,
            classList:{add:(...xs)=>xs.forEach(x=>classes.add(x)),remove:(...xs)=>xs.forEach(x=>classes.delete(x)),
                toggle:(x,on)=>on ? classes.add(x) : classes.delete(x),contains:x=>classes.has(x)},
            setAttribute(k,v){this.attributes[k]=v;},focus(){this.focused=true;}};
    }
    const ids = ['menu','settings-toggle',...['dark','light','auto'].map(x=>`theme-${x}-btn`),
        ...['small','normal','large'].map(x=>`font-${x}-btn`)];
    const nodes = Object.fromEntries(ids.map(id=>[id,element(id)]));
    const body = element('body');
    const context = {document:{body,readyState:'loading',getElementById:id=>nodes[id],
        addEventListener:(name,fn)=>handlers[name]=fn,
        querySelectorAll:selector=>Object.values(nodes).filter(n=>n.id.startsWith(selector.includes('theme')?'theme-':'font-'))},
        localStorage:{getItem(){if(blocked)throw Error('disabled');return 'invalid';},setItem(){writes++;if(blocked)throw Error('disabled');}},
        matchMedia:()=>({matches:false,addEventListener(){}})};
    vm.createContext(context); vm.runInContext(source,context);
    assert.equal(writes, 0, 'Initial page load must not persist default preferences');
    return {context,nodes,handlers,body};
}
for (const blocked of [true,false]) {
    const {context:c,nodes:n,handlers:h,body} = fixture(blocked);
    assert(body.classList.contains('light'));
    assert(body.classList.contains('font-normal'));
    c.toggleMenu(); assert.equal(n.menu.hidden,false);
    assert.equal(n['settings-toggle'].attributes['aria-expanded'],'true');
    c.setMode('dark'); assert(body.classList.contains('dark'));
    assert.equal(n['theme-dark-btn'].attributes['aria-pressed'],'true');
    c.setFont('large'); assert(body.classList.contains('font-large'));
    h.keydown({key:'Escape'}); assert(n.menu.hidden); assert(n['settings-toggle'].focused);
    c.toggleMenu(); h.focusin({target:{closest:()=>null}}); assert(n.menu.hidden);
    c.toggleMenu(); h.click({target:{closest:()=>null}}); assert(n.menu.hidden);
    c.setMode('invalid'); assert(body.classList.contains('dark'));
}
console.log('Settings behavior PASS: blocked storage, invalid preferences, state, Escape, focus and outside click.');
