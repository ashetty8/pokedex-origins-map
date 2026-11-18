(function(){
  "use strict";
  var D=null, dbNS=null, userNS=null, canWrite=null, viewerId=null;
  var state={tab:"clusters",q:"",kinds:new Set(),sort:"species",onlymulti:false,onlyinf:false,sel:null,limit:120,path:[],flagview:"open",poke:null,
             types:new Set(),gens:new Set(),colours:new Set(),misc:new Set(),scope:true};
  var flags=[], flagsReady=false, flagsNote="";
  /* what has been flagged, by target, so the map can show it too */
  var FLAGIDX={};
  function buildFlagIndex(){
    FLAGIDX={};
    flags.forEach(function(f){
      var k=(f.d.targetType||"")+":"+(f.d.target||"");
      var e=FLAGIDX[k]||(FLAGIDX[k]={open:0,total:0});
      e.total++; if(f.d.status!=="done") e.open++;
    });
  }
  /* a family/kind/branch/region is selected as a "node", so a flag on it is
     filed under node:<name> — look under both spellings */
  function flagsOn(t,k){
    var a=FLAGIDX[t+":"+k], b=(t!=="node")?FLAGIDX["node:"+k]:null;
    if(!a&&!b) return null;
    return {open:(a?a.open:0)+(b?b.open:0), total:(a?a.total:0)+(b?b.total:0)};
  }
  var $=function(s){return document.querySelector(s)};
  var el=function(t,c,x){var e=document.createElement(t); if(c)e.className=c; if(x!=null)e.textContent=x; return e};
  var dex=function(n){return "#"+String(n).padStart(4,"0")};
  /* Referent keys are lowercase because everything looks them up by key; the
     spelling to SHOW is on the referent itself, taken from its source text.
     A cluster named after a referent is that referent, so it reads the same. */
  function disp(name){
    var r=D && D.referents[name];
    if(r && r.d) return r.d;
    var g=D && D.groups[name];
    if(g && (g.m||[]).length===1 && g.m[0]===name){
      var only=D.referents[name];
      if(only && only.d) return only.d;
    }
    return name;
  }
  var esc=function(s){return String(s)};

  /* the sticky columns hang off the header, whose height changes with the
     window width, the zoom level and the font — so measure it, never assume. */
  function topbar(){
    var h=$("header.top");
    if(h) document.documentElement.style.setProperty("--topbar", Math.round(h.getBoundingClientRect().height)+"px");
    /* the middle column carries a heading row that the side panel does not,
       so measure it and drop the panel by the same amount — otherwise the two
       boxes start on different lines */
    var rh=document.querySelector(".resulthead");
    if(rh){
      var st=getComputedStyle(rh);
      var drop=rh.getBoundingClientRect().height+parseFloat(st.marginBottom||0);
      document.documentElement.style.setProperty("--headrow", Math.round(drop)+"px");
      /* the rail leads with its own small CATEGORY label, so it needs the
         remainder of that drop for its first chips to meet the boxes */
      var rt=document.querySelector(".rail .railtitle");
      if(rt){
        var rs=getComputedStyle(rt);
        var lead=rt.getBoundingClientRect().height+parseFloat(rs.marginBottom||0);
        document.documentElement.style.setProperty("--raildrop", Math.max(0,Math.round(drop-lead))+"px");
      }
    }
  }
  topbar();
  addEventListener("resize",topbar);
  if(window.ResizeObserver){ try{ new ResizeObserver(topbar).observe($("header.top")) }catch(e){} }
  if(document.fonts && document.fonts.ready) document.fonts.ready.then(topbar);

  /* ---------- sprites ---------- */
  /* 1025 base64 PNGs, ~1.4 MB — fetched after the map so it never delays
     first paint, and the page is perfectly usable if it never arrives. */
  var SPR=null, FSPR=null;
  function sprite(id,cls){
    if(!SPR || !SPR[String(id)]) return null;
    var i=document.createElement("img");
    i.className="spr"+(cls?" "+cls:"");
    i.src="data:image/png;base64,"+SPR[String(id)];
    i.alt=""; i.loading="lazy"; i.decoding="async";
    return i;
  }
  function formSprite(slug){
    if(!FSPR || !FSPR[slug]) return null;
    var i=document.createElement("img");
    i.className="spr formspr"; i.src="data:image/png;base64,"+FSPR[slug];
    i.alt=""; i.loading="lazy"; i.decoding="async";
    return i;
  }
  function loadSprites(){
    fetch("sprites.json").then(function(r){return r.json()}).then(function(j){
      SPR=j; buildPokeFilters(); render(); if(state.sel) renderDetail();
      if(state.tab==="clusters" && D3) drawGraph();
    }).catch(function(){});
    fetch("form_sprites.json").then(function(r){return r.json()}).then(function(j){
      FSPR=j; if(state.sel) renderDetail();
      if(state.tab==="map" && D3 && D) drawGraph();
    }).catch(function(){});
  }

  /* ---------- data ---------- */
  fetch("map_data.json").then(function(r){return r.json()}).then(function(j){
    D=j;
    $("#counts").textContent=j.meta.species+" Pokémon · "+j.meta.referents+" referents · "+j.meta.clusters+" clusters · "+j.meta.families+" families";
    buildKinds(); buildPokeFilters(); buildParentList(); render(); loadSprites();
    /* the panel reports where a referent is from on every tab, so the
       geography loads with the dataset rather than with the Atlas tab */
    ensureGeo().then(function(){ if(state.sel) renderDetail() }).catch(function(){});
  }).catch(function(){
    $("#results").innerHTML='<p class="empty">The dataset could not be loaded. Reload the page to try again.</p>';
  });

  function buildParentList(){
    var dl=document.createElement("datalist"); dl.id="parentlist";
    var names=Object.keys(D.families).concat(
      Object.keys(D.groups).filter(function(g){return D.groups[g].m.length>1}));
    names.sort().forEach(function(n){ var op=document.createElement("option"); op.value=n; dl.appendChild(op) });
    document.body.appendChild(dl);
  }

  var TYPEHUE={normal:40,fire:18,water:205,electric:50,grass:110,ice:186,
    fighting:8,poison:290,ground:34,flying:225,psychic:330,bug:80,rock:40,
    ghost:265,dragon:250,dark:240,steel:210,fairy:320};
  /* the colours the games actually use, so a type reads at a glance */
  var TYPECOL={normal:"#9fa19f",fire:"#e8743a",water:"#5a8fe0",electric:"#f2cb55",
    grass:"#67bb6a",ice:"#7ed0d6",fighting:"#d0506a",poison:"#a964c8",
    ground:"#d1a05a",flying:"#8f9fe8",psychic:"#f06f9a",bug:"#a8bb3a",
    rock:"#bfae72",ghost:"#7b62b8",dragon:"#6a5fd0",dark:"#6b5a52",
    steel:"#8fa8b8",fairy:"#ef92c6"};
  /* Pokémon "colour" is a real PokeAPI field — show the colour itself */
  var BODYCOL={black:"#4a4a4a",blue:"#5a8fe0",brown:"#a9794f",gray:"#9a9a9a",
    green:"#67bb6a",pink:"#f0a0c0",purple:"#a964c8",red:"#df5a5a",
    white:"#e2e2e2",yellow:"#f2cb55"};
  /* one familiar face per generation, from the sprites already loaded */
  var GENFACE={1:1,2:152,3:252,4:387,5:494,6:650,7:722,8:810,9:906};
  function chipSet(hostId,items,bag,colour){
    var box=$(hostId); if(!box) return; box.innerHTML="";
    items.forEach(function(it){
      var key=it.key!=null?it.key:it, label=it.label!=null?it.label:it;
      var b=el("button","chip");
      if(it.sprite && SPR && SPR[String(it.sprite)]){
        var im=document.createElement("img");
        im.className="chipspr"; im.src="data:image/png;base64,"+SPR[String(it.sprite)];
        im.alt=""; im.loading="lazy";
        b.appendChild(im);
      } else if(it.swatch){
        b.classList.add("tinted");
        b.style.setProperty("--tc",it.swatch);
        var sw=el("span","dot"); sw.style.background=it.swatch; b.appendChild(sw);
      } else if(colour!=null){
        var d=el("span","dot");
        d.style.background="hsl("+colour(key)+" 60% 55%)";
        b.appendChild(d);
      }
      b.appendChild(document.createTextNode(label));
      if(it.n!=null) b.appendChild(el("span","n",it.n));
      b.setAttribute("aria-pressed",bag.has(key)?"true":"false");
      b.onclick=function(){
        if(bag.has(key)) bag.delete(key); else bag.add(key);
        b.setAttribute("aria-pressed",bag.has(key)?"true":"false");
        state.limit=120; render();
      };
      box.appendChild(b);
    });
  }
  function buildPokeFilters(){
    if(!D.attrs) return;
    var types={},gens={},cols={};
    Object.keys(D.attrs).forEach(function(id){
      var a=D.attrs[id];
      (a.t||[]).forEach(function(t){types[t]=(types[t]||0)+1});
      if(a.g) gens[a.g]=(gens[a.g]||0)+1;
      if(a.c) cols[a.c]=(cols[a.c]||0)+1;
    });
    chipSet("#ftypes",Object.keys(types).sort().map(function(t){
      return {key:t,label:t,n:types[t],swatch:TYPECOL[t]||"#888"}}),state.types);
    chipSet("#fgens",Object.keys(gens).sort(function(a,b){return a-b})
            .map(function(g){return {key:+g,label:"gen "+g,n:gens[g]}}),state.gens);
    chipSet("#fcolours",Object.keys(cols).sort().map(function(c){
      return {key:c,label:c,n:cols[c],swatch:BODYCOL[c]||"#888"}}),state.colours);
    chipSet("#fmisc",[{key:"legendary",label:"legendary"},{key:"mythical",label:"mythical"},
                      {key:"stage1",label:"base form"},{key:"fully",label:"final form"}],state.misc);
  }
  function markKindChips(){
    var st=stepsOf(), at=(st.length && st[0].t==="kind") ? st[0].k : null;
    [].forEach.call(document.querySelectorAll("#kinds .chip"),function(c){
      c.setAttribute("aria-pressed",c.dataset.kind===at?"true":"false");
    });
  }
  function buildKinds(){
    var tally={};
    Object.keys(D.groups).forEach(function(g){var k=D.groups[g].k||"unclassified"; tally[k]=(tally[k]||0)+1});
    var order=Object.keys(tally).sort(function(a,b){return tally[b]-tally[a]});
    var box=$("#kinds"); box.innerHTML="";
    order.forEach(function(k){
      var b=el("button","chip "+kindClass(k)); b.dataset.kind=k;
      b.setAttribute("aria-pressed","false");
      b.appendChild(el("span","dot"));
      b.appendChild(document.createTextNode(kindLabel(k)));
      var n=el("span","n",tally[k]); b.appendChild(n);
      b.onclick=function(){
        /* A category is a place, not a filter: clicking one moves all three
           views there. It also means the count is every Pokémon under it,
           not only those whose DESIGN is of that kind. */
        var st=stepsOf(), here=st.length && st[0].t==="kind" && st[0].k===k;
        goTo(here?[]:[{t:"kind",k:k}]);
      };
      box.appendChild(b);
    });
  }

  /* ---------- filtering ---------- */
  function groupRows(){
    var q=state.q, out=[];
    Object.keys(D.groups).forEach(function(name){
      var g=D.groups[name];
      if(state.onlymulti && g.m.length<2) return;
      if(!hasInferred({t:"group",k:name})) return;
      if(q){
        var hit=name.indexOf(q)>=0 || g.m.some(function(m){return m.indexOf(q)>=0});
        if(!hit) return;
      }
      out.push({name:name,g:g});
    });
    var s=state.sort;
    out.sort(function(a,b){
      if(s==="az") return a.name<b.name?-1:1;
      if(s==="members") return b.g.m.length-a.g.m.length || b.g.n-a.g.n;
      return b.g.n-a.g.n || b.g.m.length-a.g.m.length;
    });
    return out;
  }
  function familyRows(){
    var out=[];
    Object.keys(D.families).forEach(function(name){
      var f=D.families[name];
      out.push({name:name,f:f});
    });
    var s=state.sort;
    out.sort(function(a,b){
      if(s==="az") return a.name<b.name?-1:1;
      if(s==="members") return (b.f.c.length+b.f.l.length)-(a.f.c.length+a.f.l.length);
      return b.f.n-a.f.n;
    });
    return out;
  }
  /* children of whatever node the path currently points at: a family shows its
     top-level clusters, a cluster shows the clusters nested inside it. */
  var FAMGROUPS=null;
  function famGroups(fam){
    if(!FAMGROUPS){
      FAMGROUPS={};
      Object.keys(D.groups).forEach(function(g){
        var f=D.groups[g].f; if(!f) return;
        (FAMGROUPS[f]||(FAMGROUPS[f]=[])).push(g);
      });
    }
    return FAMGROUPS[fam]||[];
  }
  function speciesIn(fams){
    var sp={}, filter=attrsActive();
    fams.forEach(function(fam){
      famGroups(fam).forEach(function(g){
        (D.groups[g].m||[]).forEach(function(m){
          var r=D.referents[m];
          if(r) r.s.forEach(function(i){ if(!filter||passAttrs(i)) sp[i]=1 });
        });
      });
    });
    return Object.keys(sp).length;
  }
  function regionsOf(fam){ var f=D.families[fam]; return f && f.rg ? f.rg : null }
  /* Moving is one operation: set the path, point the panel at wherever we
     landed, redraw. The panel then always describes the place you are in,
     instead of the last thing you happened to click. */
  /* A level holding exactly one thing is not a level: it makes you click to
     see what you were already told. Walk straight through it. */
  function collapse(path){
    for(var i=0;i<6;i++){
      var st=path.map(function(p){return typeof p==="string"?{t:"family",k:p}:p});
      var last=st[st.length-1];
      if(!last || last.t==="referent") break;
      var kids;
      try{ kids=childrenOf(graphFocusFor(st)) }catch(e){ break }
      if(!kids || kids.length!==1) break;
      var only=kids[0];
      if(only.t==="species" || only.open===false) break;
      path=path.concat([{t:only.t,k:only.k}]);
    }
    return path;
  }
  function samePath(a,b){
    if(a.length!==b.length) return false;
    for(var i=0;i<a.length;i++){
      var x=typeof a[i]==="string"?{t:"family",k:a[i]}:a[i];
      var y=typeof b[i]==="string"?{t:"family",k:b[i]}:b[i];
      if(x.t!==y.t||String(x.k)!==String(y.k)) return false;
    }
    return true;
  }
  /* Going back has to clear the levels we walked through automatically,
     or "up" lands on a level that immediately forwards you here again. */
  function goBackTo(path){
    while(path.length && samePath(collapse(path),state.path)) path=path.slice(0,-1);
    goTo(path);
  }
  function goTo(path,opts){
    state.path=collapse(path); state.limit=120; state.scope=true; state.poke=null;
    var st=stepsOf(), last=st[st.length-1];
    if(!last) state.sel=null;
    else if(last.t==="group"||last.t==="referent") state.sel={t:last.t,k:last.k};
    else state.sel={t:"node",k:last.k,nt:last.t};
    if(!opts||opts.record!==false) record();
    renderDetail(); render(); markKindChips();
    if(opts&&opts.top) window.scrollTo({top:0,behavior:"smooth"});
  }
  function stepsOf(){ return state.path.map(function(p){ return typeof p==="string"?{t:"family",k:p}:p }) }
  function lastStep(){ var st=stepsOf(); return st[st.length-1] }
  function kindRows(){
    var tally={};
    Object.keys(D.families).forEach(function(n){
      var k=D.families[n].k||"unclassified";
      var t=tally[k]||(tally[k]={name:k,fams:0,n:0,list:[]});
      t.fams++; t.list.push(n);
    });
    var out=Object.keys(tally).map(function(k){
      var t=tally[k]; t.n=speciesIn(t.list); return t;
    }).filter(function(t){return t.n>0 && hasInferred({t:"kind",k:t.name})});
    if(state.sort==="az") out.sort(function(a,b){return a.name<b.name?-1:1});
    else out.sort(function(a,b){return b.n-a.n});
    return out;
  }
  function kindRow(r){
    var b=el("button","row");
    var nm=el("span","rowname",kindLabel(r.name)); nm.appendChild(el("span","intonode"," ›"));
    b.appendChild(nm);
    var meta=el("span","rowmeta");
    meta.appendChild(el("span","num nest",r.fams+(r.fams===1?" family":" families")));
    meta.appendChild(el("span","num",r.n+" Pokémon"));
    b.appendChild(meta);
    b.onclick=function(){ goTo([{t:"kind",k:r.name}],{top:true}) };
    return b;
  }
  function branchRows(kind){
    var defs=(D.branches||{})[kind];
    if(!defs) return null;
    return defs.map(function(d){
      return {name:d[0], fams:d[1], n:speciesIn(d[1])};
    }).filter(function(r){return r.fams.length && r.n>0 &&
      (r.fams.length>1 ? hasInferred({t:"branch",k:r.name}) : hasInferred({t:"family",k:r.fams[0]}))});
  }
  function branchRow(r){
    var b=el("button","row");
    var nm=el("span","rowname",r.name);
    if(r.fams.length>1) nm.appendChild(el("span","intonode"," ›"));
    b.appendChild(nm);
    var meta=el("span","rowmeta");
    meta.appendChild(el("span","num nest",r.fams.length+(r.fams.length===1?" family":" families")));
    meta.appendChild(el("span","num",r.n+" Pokémon"));
    b.appendChild(meta);
    b.onclick=function(){
      /* a branch holding one family is not worth a click of its own */
      var step = r.fams.length===1 ? {t:"family",k:r.fams[0]} : {t:"branch",k:r.name};
      goTo(state.path.concat([step]));
    };
    return b;
  }
  function familiesIn(step){
    var st=stepsOf();
    if(step.t==="kind"){
      var br=branchRows(step.k);
      if(br) return null;                        /* branches are shown instead */
      return Object.keys(D.families).filter(function(n){return (D.families[n].k||"unclassified")===step.k});
    }
    var defs=(D.branches||{})[st[0].k]||[];
    for(var i=0;i<defs.length;i++) if(defs[i][0]===step.k) return defs[i][1].slice();
    return [];
  }
  function nodeNames(){
    var st=stepsOf(), last=st[st.length-1], prev=st[st.length-2];
    if(last.t==="family"){
      var f=D.families[last.k];
      if(!f) return [];
      if(f.rg) return [];                       /* regions are rendered instead */
      return f.c.concat(state.onlymulti?[]:f.l);
    }
    if(last.t==="region"){
      var list=(regionsOf(prev.k)||{})[last.k]||[];
      return state.onlymulti ? list.filter(function(n){return D.groups[n].m.length>1}) : list.slice();
    }
    var g=D.groups[last.k];
    return (g && g.ch) ? g.ch.slice() : [];
  }
  function famMemberRows(fam){
    var names=nodeNames(), out=[];
    names.forEach(function(n){
      if(D.groups[n] && groupPassesAttrs(n) && hasInferred({t:"group",k:n})) out.push({name:n,g:D.groups[n]});
    });
    /* a node's own referents belong in the list too, beside the nested nodes —
       otherwise the bears inside "bear" are invisible while browsing. */
    var last=lastStep();
    if(last && last.t==="group" && D.groups[last.k]){
      (D.groups[last.k].m||[]).forEach(function(m){
        var r=D.referents[m];
        if(r && (!state.onlyinf || r.i)) out.push({name:m, ref:r});
      });
    }
    var s=state.sort;
    function size(x){ return x.ref ? x.ref.s.length : x.g.n }
    function kids(x){ return x.ref ? 0 : (x.g.ch||[]).length }
    out.sort(function(a,b){
      if(s==="az") return a.name<b.name?-1:1;
      if(s==="members") return (b.ref?1:b.g.m.length)-(a.ref?1:a.g.m.length) || size(b)-size(a);
      return (kids(b)>0)-(kids(a)>0) || size(b)-size(a) || (a.name<b.name?-1:1);
    });
    return out;
  }
  function refRow(r){
    var b=el("button","row");
    b.setAttribute("aria-current", state.sel&&state.sel.t==="referent"&&state.sel.k===r.name ? "true":"false");
    var nm=el("span","rowname",disp(r.name));
    if(r.ref.w) nm.appendChild(el("span","wikimark"," ↗"));
    b.appendChild(nm);
    var meta=el("span","rowmeta");
    if(r.ref.x) meta.appendChild(el("span","num soft","allusion"));
    meta.appendChild(kindTag(r.ref.k,r.ref.i));
    meta.appendChild(el("span","num",shownCount({t:"referent",k:r.name},r.ref.s.length)+" Pokémon"));
    b.appendChild(meta);
    b.onclick=function(){
      select({t:"referent",k:r.name});       /* routes by the canonical path */
    };
    return b;
  }
  function crumb(){
    var c=el("div"); c.style.cssText="display:flex;gap:6px;align-items:center;margin-bottom:10px;flex-wrap:wrap";
    var up=el("button","ghost", state.path.length>1 ? "← Up" : "← All categories");
    up.onclick=function(){ goBackTo(state.path.slice(0,-1)) };
    c.appendChild(up);
    var all=el("button","crumblink","Categories");
    all.onclick=function(){ goTo([]) };
    c.appendChild(all);
    var allsteps=stepsOf();
    allsteps.forEach(function(step,i){
      var nx=allsteps[i+1];
      if(step.t==="group" && nx && nx.t==="referent" && nx.k===step.k) return;   /* same name twice */
      c.appendChild(el("span","crumbsep","›"));
      if(i===state.path.length-1){ c.appendChild(el("span","crumbhere",step.t==="kind"?kindLabel(step.k):disp(step.k))); return }
      var b=el("button","crumblink",step.t==="kind"?kindLabel(step.k):disp(step.k));
      b.onclick=function(){ goBackTo(state.path.slice(0,i+1)) };
      c.appendChild(b);
    });
    return c;
  }
  var ATTRCACHE=null;
  function attrsActive(){
    return state.types.size||state.gens.size||state.colours.size||state.misc.size;
  }
  function groupPassesAttrs(name){
    if(!attrsActive()) return true;
    if(!ATTRCACHE) ATTRCACHE={};
    if(ATTRCACHE[name]!=null) return ATTRCACHE[name];
    var g=D.groups[name], ok=false;
    if(g){
      var ids=Object.keys(speciesOfGroup(g));
      for(var i=0;i<ids.length;i++){ if(passAttrs(ids[i])){ ok=true; break } }
    }
    return (ATTRCACHE[name]=ok);
  }
  function passAttrs(id){
    var a=(D.attrs||{})[String(id)]; if(!a) return true;
    if(state.types.size && !(a.t||[]).some(function(t){return state.types.has(t)})) return false;
    if(state.gens.size && !state.gens.has(a.g)) return false;
    if(state.colours.size && !state.colours.has(a.c)) return false;
    if(state.misc.size){
      if(state.misc.has("legendary") && a.l!==1) return false;
      if(state.misc.has("mythical") && a.l!==2) return false;
      if(state.misc.has("stage1") && a.st!==1) return false;
      if(state.misc.has("fully") && !isFinal(id)) return false;
    }
    return true;
  }
  function isFinal(id){
    var a=(D.attrs||{})[String(id)]; if(!a) return true;
    return a.st===3 || (a.st===2 && !hasHigher(id)) || (a.st===1 && !hasHigher(id));
  }
  function hasHigher(id){
    /* a final form is one nothing evolves from: approximate with stage counts
       inside the same colour-blind check is wrong, so use the evolution map */
    var e=(D.evo||{})[String(id)];
    return e ? (e.to||[]).length>0 : false;
  }
  /* The place you are browsing is a filter in its own right: switching to the
     Pokémon tab should keep it, not throw it away. */
  function speciesUnder(){
    var st=stepsOf(); if(!st.length) return null;
    var last=st[st.length-1], sp={};
    function fromGroup(g){ var gg=D.groups[g]; if(gg) Object.keys(speciesOfGroup(gg)).forEach(function(i){sp[i]=1}) }
    /* A family counts the referents filed under it. Walking into child groups
       would also sweep in clusters that live in another family, which is how
       the scope and the row counts came to disagree. */
    function fromFamily(f){
      famGroups(f).forEach(function(g){
        ((D.groups[g]||{}).m||[]).forEach(function(m){
          var r=D.referents[m]; if(r) r.s.forEach(function(i){sp[i]=1});
        });
      });
    }
    if(last.t==="referent"){ ((D.referents[last.k]||{}).s||[]).forEach(function(i){sp[i]=1}) }
    else if(last.t==="group"){ fromGroup(last.k) }
    else if(last.t==="family"){ fromFamily(last.k) }
    else if(last.t==="region"){
      var pf=st[st.length-2];
      (((D.families[pf&&pf.k]||{}).rg||{})[last.k]||[]).forEach(fromGroup);
    }
    else if(last.t==="branch"){
      var defs=D.branches||{};
      Object.keys(defs).forEach(function(k){ defs[k].forEach(function(d){ if(d[0]===last.k) d[1].forEach(fromFamily) }) });
    }
    else if(last.t==="kind"){
      Object.keys(D.families).forEach(function(f){ if((D.families[f].k||"")===last.k) fromFamily(f) });
    }
    var ids=Object.keys(sp);
    return ids.length ? {label:last.k, set:sp, n:ids.length} : null;
  }
  function speciesRows(){
    var q=state.q,out=[],scope=state.scope?speciesUnder():null;
    Object.keys(D.species).forEach(function(id){
      var s=D.species[id];
      /* the scope already says which part of the taxonomy you are in, so the
         category chips would only subtract from it — ignore them while it is on */
      if(!passAttrs(id)) return;
      if(!hasInferred({t:"species",k:id})) return;
      if(scope && !scope.set[id]) return;
      if(q){
        var hit=s[0].toLowerCase().indexOf(q)>=0 || s[1].some(function(r){return r.toLowerCase().indexOf(q)>=0});
        if(!hit) return;
      }
      out.push({id:+id,s:s});
    });
    var at=function(r){return (D.attrs||{})[String(r.id)]||{}};
    if(state.sort==="az") out.sort(function(a,b){return a.s[0]<b.s[0]?-1:1});
    else if(state.sort==="members") out.sort(function(a,b){return b.s[1].length-a.s[1].length});
    else if(state.sort==="bst") out.sort(function(a,b){return (at(b).bst||0)-(at(a).bst||0)});
    else if(state.sort==="tall") out.sort(function(a,b){return (at(b).h||0)-(at(a).h||0)});
    else if(state.sort==="heavy") out.sort(function(a,b){return (at(b).w||0)-(at(a).w||0)});
    else out.sort(function(a,b){return a.id-b.id});
    return out;
  }

  /* ---------- render ---------- */
  function render(){
    if(!D) return;
    var host=$("#results"); host.innerHTML=""; ATTRCACHE=null; INFCACHE=null;
    syncClears();
    setTimeout(topbar,0);          /* the heading row may have changed height */
    $("#rail").classList.toggle("hidden",state.tab==="flags");
    $("#pokefilters").classList.toggle("hidden",state.tab==="flags");
    $("#detail").classList.toggle("hidden",state.tab==="flags");
    var lay=document.querySelector(".layout");
    /* One frame on every tab, and the rail never moves — that is what makes
       switching feel continuous. What changes is where the slack goes:
         both side columns hold still at the same width on every tab, and the
         middle takes whatever is left — rows capped at a readable measure,
         the canvas free to use the rest. */
    lay.style.gridTemplateColumns = state.tab==="flags" ? "minmax(0,1fr)"
      /* wide enough for two Pokémon chips side by side — at 380px a long name
         like "Brambleghast" or "Poltchageist" took a row to itself */
      : "232px minmax(0,1fr) minmax(0,clamp(380px, 26vw, 460px))";
    lay.style.maxWidth = "min(1860px, 98vw)";
    $("#graph").classList.toggle("hidden",state.tab!=="map");
    $("#atlas").classList.toggle("hidden",state.tab!=="atlas");
    host.classList.toggle("hidden",state.tab==="map"||state.tab==="atlas");
    document.querySelector(".results").classList.toggle("mapmode",state.tab==="map");
    document.querySelector(".results").classList.toggle("atlasmode",state.tab==="atlas");
    if(state.tab==="atlas"){
      $("#resulttitle").textContent="Atlas";
      $("#resultnote").textContent=atlasBroken?"":"placing the referents\u2026";
      if(atlasBroken){
        $("#atlas").classList.add("hidden");
        host.classList.remove("hidden");
        host.appendChild(el("p","empty","The atlas layer could not be loaded \u2014 the other tabs still work."));
      } else {
        ensureAtlas().then(drawAtlas).catch(function(){
          atlasBroken=true; render();
        });
      }
      syncClears();
      return;
    }
    if(state.tab==="map"){
      var mf=graphFocus(true);
      $("#resulttitle").textContent=mf.label||mf.k;
      $("#resultnote").textContent=state.path.length?"click the middle node to go back":"the whole map";
      ensureD3().then(drawGraph).catch(function(){
        $("#graph").innerHTML='<p class="empty">The map needs the d3 library and it could not be loaded — Browse still works.</p>';
      });
      syncClears();
      return;
    }
    if(state.tab==="flags"){ renderFlags(host); return; }
    var rows,mode;
    if(state.tab==="species"){
      rows=speciesRows(); mode="species"; $("#resulttitle").textContent="Pokémon";
      var sc=state.scope?speciesUnder():null;
      if(sc){
        var bar=el("div","scopebar");
        bar.appendChild(el("span","scopelabel","within"));
        var sb=stepsOf();
        var crumbs=sb.filter(function(x,i){
          var nx=sb[i+1];
          return !(x.t==="group" && nx && nx.t==="referent" && nx.k===x.k);
        }).map(function(x){return x.t==="kind"?kindLabel(x.k):x.k});
        bar.appendChild(el("span","scopename",crumbs.join(" › ")));
        var x=el("button","scopeclear","✕ clear");
        x.title="Show every Pokémon again";
        x.onclick=function(){ state.scope=false; state.limit=120; render() };
        bar.appendChild(x);
        host.appendChild(bar);
      }
    }
    else if(state.q){ rows=groupRows(); mode="group"; $("#resulttitle").textContent="Search"; }
    else if(state.path.length){
      var st=stepsOf(), last=st[st.length-1];
      $("#resulttitle").textContent=last.t==="kind"?kindLabel(last.k):last.k; host.appendChild(crumb());
      if(last.t==="kind" || last.t==="branch"){
        var fams=familiesIn(last);
        if(fams===null){ rows=branchRows(last.k); mode="branch"; }
        else { rows=fams.map(function(n){return {name:n,f:D.families[n],fn:speciesIn([n])}})
                 .filter(function(r){return r.fn>0 && hasInferred({t:"family",k:r.name})})
                 .sort(function(a,b){ return state.sort==="az" ? (a.name<b.name?-1:1) : b.fn-a.fn });
               mode="family"; }
      }
      else if(last.t==="referent" && D.referents[last.k]){
        rows=D.referents[last.k].s.map(function(id){return {id:id,s:D.species[String(id)]}})
             .filter(function(r){return r.s});
        mode="species";
      }
      else if(last.t==="family" && regionsOf(last.k)){ rows=regionRows(last.k); mode="region"; }
      else { rows=famMemberRows(); mode="group"; }
    }
    else { rows=kindRows(); mode="kind"; $("#resulttitle").textContent="Categories"; }
    var noun = mode==="species"?" Pokémon":(mode==="family"?" families":(mode==="region"?" places of origin":(mode==="kind"?" categories":(mode==="branch"?" groups":" clusters & referents"))));
    $("#resultnote").textContent = rows.length + noun + (state.q?" matching “"+state.q+"”":"");
    if(!rows.length){
      var why=(state.tab==="species" && (attrsActive()||state.scope))
        ? "No Pokémon match all of these filters at once. Drop one — the type chips, or the “within” scope above."
        : "Nothing matches that. Try a broader word — “fox”, “bell”, “wrestler”.";
      host.appendChild(el("p","empty",why));
      return;
    }
    var list=el("div","rows");
    rows.slice(0,state.limit).forEach(function(r){
      list.appendChild(
        mode==="species"?speciesRow(r):
        mode==="kind"?kindRow(r):
        mode==="branch"?branchRow(r):
        mode==="family"?familyRow(r):
        mode==="region"?regionRow(r):(r.ref?refRow(r):groupRow(r)));
    });
    host.appendChild(list);
    if(rows.length>state.limit){
      var m=el("button","more","Show "+Math.min(200,rows.length-state.limit)+" more of "+rows.length);
      m.onclick=function(){state.limit+=200; render()};
      host.appendChild(m);
    }
  }
  var KINDLABEL={object:"objects",person:"people",concept:"concepts",
                 prehistoric:"prehistoric life"};
  function kindLabel(k){ return KINDLABEL[k]||k }
  function kindClass(k){ return "k-"+String(k||"unclassified").replace(/[^a-z]/gi,"") }
  function kindTag(k,guess){
    var t=el("span","kind "+kindClass(k)+(guess?" guess":""),k||"unclassified");
    if(guess) t.title="Category inferred from the Pokémon citing it — correct it if it looks wrong";
    return t;
  }
  function regionRows(fam){
    var rg=regionsOf(fam), out=[];
    Object.keys(rg).some;
    Object.keys(rg).forEach(function(name){
      var sp={};
      rg[name].forEach(function(g){
        (D.groups[g].m||[]).forEach(function(m){
          var r=D.referents[m]; if(r) r.s.forEach(function(i){sp[i]=1});
        });
      });
      var filter=attrsActive();
      var ids=Object.keys(sp).filter(function(i){return !filter||passAttrs(i)});
      if(!ids.length) return;
      if(state.onlyinf && !rg[name].some(function(g){return hasInferred({t:"group",k:g})})) return;
      out.push({name:name, list:rg[name], n:ids.length});
    });
    if(state.sort==="az") out.sort(function(a,b){return a.name<b.name?-1:1});
    else out.sort(function(a,b){return b.list.length-a.list.length});
    return out;
  }
  function regionRow(r){
    var b=el("button","row");
    var nm=el("span","rowname",r.name);
    nm.appendChild(el("span","intonode"," ›"));
    b.appendChild(nm);
    var meta=el("span","rowmeta");
    meta.appendChild(el("span","num nest",r.list.length+" clusters"));
    meta.appendChild(el("span","num",r.n+" Pokémon"));
    b.appendChild(meta);
    b.onclick=function(){ goTo(state.path.concat([{t:"region",k:r.name}])) };
    return b;
  }
  function familyRow(r){
    var b=el("button","row");
    b.appendChild(el("span","rowname",r.name));
    var meta=el("span","rowmeta");
    var inside=r.f.c.length+(r.f.l||[]).length;
    meta.appendChild(el("span","num nest",inside+(inside===1?" cluster":" clusters")));
    meta.appendChild(kindTag(r.f.k));
    meta.appendChild(el("span","num",(r.fn!=null?r.fn:r.f.n)+" Pokémon"));
    b.appendChild(meta);
    b.onclick=function(){ goTo(state.path.concat([{t:"family",k:r.name}]),{top:true}) };
    return b;
  }
  /* with filters on, a row shows the filtered total — otherwise the list and
     the map print different numbers for the same cluster */
  function shownCount(node,raw){
    if(!attrsActive()) return raw;
    return mapCount(node);
  }
  function groupRow(r){
    var leaf=r.g.m.length<2, only=leaf?r.g.m[0]:null;
    var b=el("button","row");
    var cur = state.sel && ((leaf && state.sel.t==="referent" && state.sel.k===only) ||
                            (!leaf && state.sel.t==="group" && state.sel.k===r.name));
    b.setAttribute("aria-current",cur?"true":"false");
    var kids=(r.g.ch||[]).length;
    var nm=el("span","rowname",disp(leaf&&!kids?only:r.name));
    if(kids) nm.appendChild(el("span","intonode"," ›"));
    b.appendChild(nm);
    var meta=el("span","rowmeta");
    if(kids) meta.appendChild(el("span","num nest",kids+(kids===1?" cluster":" clusters")));
    meta.appendChild(el("span","num",leaf?"1 referent":r.g.m.length+" referents"));
    meta.appendChild(kindTag(r.g.k,r.g.i));
    meta.appendChild(el("span","num",shownCount({t:"group",k:r.name},kids?(r.g.tn||r.g.n):r.g.n)+" Pokémon"));
    b.appendChild(meta);
    b.onclick=function(){
      /* a node with children both opens and shows itself, so a click always
         goes one step more specific */
      /* every row is a move: the map follows the list, always */
      if(kids) select({t:"group",k:r.name});
      else if(leaf) select({t:"referent",k:only});
      else select({t:"group",k:r.name});
    };
    return b;
  }
  /* the categories a Pokémon draws on, for the rail to light up */
  function kindsOf(id){
    var out={}, sp=D.species[String(id)];
    (sp?sp[1]:[]).forEach(function(x){
      var ref=D.referents[String(x).toLowerCase()];
      if(ref) out[ref.k||"unclassified"]=1;
    });
    return out;
  }
  function litRail(kinds){
    [].forEach.call(document.querySelectorAll("#kinds .chip"),function(c){
      c.classList.toggle("lit", !!(kinds && kinds[c.dataset.kind]));
    });
  }
  function speciesRow(r){
    var b=el("button","row");
    b.addEventListener("mouseenter",function(){ litRail(kindsOf(r.id)) });
    b.addEventListener("mouseleave",function(){ litRail(null) }); b.setAttribute("aria-current",state.sel&&state.sel.t==="species"&&state.sel.k===r.id?"true":"false");
    var im=sprite(r.id); if(im) b.appendChild(im);
    b.appendChild(el("span","num",dex(r.id)));
    b.appendChild(el("span","rowname",r.s[0]));
    var meta=el("span","rowmeta");
    var a=(D.attrs||{})[String(r.id)];
    if(a){
      (a.t||[]).forEach(function(t){
        var x=el("span","type",t);
        x.style.setProperty("--th",(TYPEHUE[t]!=null?TYPEHUE[t]:0));
        meta.appendChild(x);
      });
      if(a.l===1) meta.appendChild(el("span","num rare","legendary"));
      if(a.l===2) meta.appendChild(el("span","num rare","mythical"));
      if(state.sort==="bst") meta.appendChild(el("span","num",a.bst));
      else if(state.sort==="tall") meta.appendChild(el("span","num",(a.h/10)+" m"));
      else if(state.sort==="heavy") meta.appendChild(el("span","num",(a.w/10)+" kg"));
    }
    meta.appendChild(el("span","num",r.s[1].length+" refs"));
    b.appendChild(meta);
    b.onclick=function(){select({t:"species",k:r.id})};
    return b;
  }

  /* ---------- history ----------
     Every move that changes what the panel shows is recorded, so the arrows
     walk back and forth through the trail you actually followed. */
  var hist=[], hpos=-1, replaying=false;
  function sameStep(a,b){
    if(!a||!b) return false;
    var x=a.sel,y=b.sel;
    var s = (!x&&!y) || (x&&y&&x.t===y.t&&String(x.k)===String(y.k));
    return s && a.fam===b.fam && a.tab===b.tab;
  }
  function record(){
    if(replaying) return;
    var now={sel:state.sel?{t:state.sel.t,k:state.sel.k}:null,fam:state.path.join(" › "),
             tab:state.tab,path:state.path.slice(),poke:state.poke};
    if(sameStep(hist[hpos],now)) return;
    hist=hist.slice(0,hpos+1);
    hist.push(now); hpos=hist.length-1;
    if(hist.length>300){ hist.shift(); hpos-- }
  }
  function travel(step){
    var n=hpos+step;
    if(n<0 || n>=hist.length) return;
    hpos=n;
    var h=hist[n];
    replaying=true;
    state.sel=h.sel?{t:h.sel.t,k:h.sel.k}:null;
    state.path=(h.path||[]).slice(); state.limit=120;
    state.poke=(h.poke==null?null:h.poke);
    if(state.tab!==h.tab){
      state.tab=h.tab;
      ["clusters","map","atlas","species","flags"].forEach(function(o){ $("#tab-"+o).setAttribute("aria-selected",o===h.tab?"true":"false") });
    }
    renderDetail(); render();
    replaying=false;
  }
  addEventListener("keydown",function(e){
    if(e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    /* Escape steps out one level, wherever you are — the map's middle node
       and Browse's "Up" button do the same thing, so the key should too */
    if(e.key==="Escape"){
      if(state.poke!=null || state.path.length){ e.preventDefault(); graphUp(); return }
      if(state.sel){ e.preventDefault(); state.sel=null; record(); renderDetail(); render(); return }
    }
    if(!(e.altKey||e.metaKey)) return;
    if(e.key==="ArrowLeft"){ e.preventDefault(); travel(-1) }
    if(e.key==="ArrowRight"){ e.preventDefault(); travel(1) }
  });

  /* Where a cluster or referent sits, as a full path from its category down:
     selecting one from the panel has to move Browse and the Map too, or the
     panel ends up describing a place the other two columns are not in. */
  /* the path down to a family: category, the branch when there is one, family */
  function famSteps(fam){
    var f=D.families[fam]; if(!f) return null;
    var kind=f.k||"unclassified", steps=[{t:"kind",k:kind}];
    var defs=(D.branches||{})[kind]||[];
    for(var i=0;i<defs.length;i++){
      if(defs[i][1].indexOf(fam)>=0){
        if(defs[i][1].length>1) steps.push({t:"branch",k:defs[i][0]});
        break;
      }
    }
    steps.push({t:"family",k:fam});
    return steps;
  }
  function pathTo(sel){
    var g=null;
    if(sel.t==="referent"){ var r=D.referents[sel.k]; if(!r) return null; g=r.g }
    else if(sel.t==="group"){ g=sel.k }
    else return null;
    if(!D.groups[g]) return null;
    var chain=[], seen={}, cur=g;
    while(cur && !seen[cur]){ seen[cur]=1; chain.unshift(cur); cur=D.groups[cur].p }
    var steps=[], top=chain[0], fam=D.groups[top].f, f=fam&&D.families[fam];
    if(f){
      steps=famSteps(fam)||[];
      if(f.rg) for(var rg in f.rg){ if(f.rg[rg].indexOf(top)>=0){ steps.push({t:"region",k:rg}); break } }
    }
    chain.forEach(function(c){ steps.push({t:"group",k:c}) });
    if(sel.t==="referent") steps.push({t:"referent",k:sel.k});
    return steps;
  }
  function select(sel){
    /* A Pokémon is not a place in the tree — it hangs off many referents at
       once. So the map centres on it instead, and shows that whole fan. */
    state.poke = (sel && sel.t==="species") ? sel.k : null;
    var route=pathTo(sel);
    if(route){ goTo(route) }
    else { state.sel=sel; record(); renderDetail(); render() }
    var d=$("#detail");
    if(d){
      d.scrollTop=0;                       /* a new selection starts at its own top */
      var r=d.getBoundingClientRect();
      if(r.top>innerHeight-40 || r.bottom<40){   /* only when it is genuinely off screen */
        try{ d.scrollIntoView({block:"nearest"}) }catch(e){}
      }
    }
  }

  function renderDetail(){
    var d=$("#detail"); d.innerHTML="";
    var sel=state.sel;
    if(!sel){
      var hd=el("div","dhead"), ht=el("div","dtitles");
      hd.appendChild(ht); hd.appendChild(navButtons());
      d.appendChild(hd);
      d.appendChild(el("p","empty","Pick a family, then a cluster, to see what sits inside it."));
      return;
    }
    var head=el("div","dhead"), titles=el("div","dtitles");
    var title,sub,body=el("div");

    if(sel.t==="group"){
      var g=D.groups[sel.k];
      /* a grouping node owns no referents of its own, so report its subtree */
      var tot=g.tn||g.n, own=g.m.length;
      title=disp(sel.k); sub=(g.f?g.f+" · ":"")+(g.rg?g.rg+" · ":"")+(g.k||"unclassified")+(g.i?" · inferred":"")+
        " · "+tot+" Pokémon · "+(own?own+" referent"+(own===1?"":"s"):(g.ch||[]).length+" groups inside");
      if(g.ch && g.ch.length){
        body.appendChild(sectionTitle("Nested inside"));
        var nl=el("div","taglist");
        g.ch.forEach(function(ch){
          var t=el("button","tag",disp(ch)+" ("+(D.groups[ch].tn||D.groups[ch].n)+")");
          t.dataset.cluster=ch;
          t.onclick=function(){ goTo(state.path.concat([{t:"group",k:ch}])) };
          nl.appendChild(t);
        });
        body.appendChild(nl);
      }
      body.appendChild(sectionTitle("Referents in this cluster"));
      var tl=el("div","taglist");
      g.m.slice().sort().forEach(function(m){
        var t=el("button","tag"+(D.referents[m]&&D.referents[m].w?" wiki":""),disp(m));
        t.dataset.ref=m;
        var rk=D.referents[m];
        if(rk && rk.k && rk.k!==g.k) t.appendChild(kindTag(rk.k,rk.i));
        t.onclick=function(){select({t:"referent",k:m})};
        tl.appendChild(t);
      });
      body.appendChild(tl);
      /* The header counts the whole subtree, so the list has to cover it too:
         own referents first, then whatever the nested clusters add — otherwise
         "horse · 9 Pokémon" shows five and Ponyta is nowhere. */
      var own=unionSpecies(g.m);
      var all=Object.keys(speciesOfGroup(g)).map(Number).sort(function(a,b){return a-b});
      var seen={}; own.forEach(function(i){ seen[i]=1 });
      var nested=all.filter(function(i){ return !seen[i] });
      body.appendChild(sectionTitle("Pokémon"));
      body.appendChild(speciesTags(own.length?own:all));
      if(own.length && nested.length){
        body.appendChild(sectionTitle("In the clusters nested here · "+nested.length));
        body.appendChild(speciesTags(nested));
      }
    }
    else if(sel.t==="referent"){
      var r=D.referents[sel.k];
      var rg=D.groups[r.g]||{};
      title=disp(sel.k); sub=((rg.f?rg.f+" · ":"")+(r.k||"unclassified"))+(r.x?" · allusion":"")+(r.i?" · inferred":"")+" · "+r.s.length+" Pokémon";
      if(rg.m && rg.m.length>1){
        var up=el("button","tag","↑ see the whole “"+r.g+"” cluster ("+rg.m.length+" referents)");
        up.onclick=function(){select({t:"group",k:r.g})};
        body.appendChild(up);
      }
      body.appendChild(sectionTitle("Pokémon"));
      body.appendChild(speciesTags(r.s,sel.k));
      var og=originSection(sel.k);
      if(og) body.appendChild(og);
      if(r.w){
        var wa=el("a","src","Wikipedia: "+r.w+" ↗");
        wa.href="https://en.wikipedia.org/wiki/"+encodeURIComponent(r.w.replace(/ /g,"_"));
        wa.target="_blank"; wa.rel="noopener noreferrer";
        var wp=el("p"); wp.style.marginTop="14px"; wp.appendChild(wa); body.appendChild(wp);
      }
    }
    else if(sel.t==="place"){
      /* A place is not a node in the tree — it is where the things in the
         tree came from, so it lists its referents by category and then every
         Pokémon that reaches it through them. */
      var pl=atlasPlace(sel.k);
      title=sel.k;
      if(!pl){
        sub="place of origin";
        body.appendChild(el("p","empty","Nothing is placed here with these filters."));
      } else {
        sub="place of origin · "+pl.refs.length+" referent"+(pl.refs.length===1?"":"s")+
            " · "+pl.n+" Pokémon";
        var how=el("div","dvia",howPlaced(pl)+(pl.soft?" — a culture area, so the pin is a region, not a spot":""));
        body.appendChild(how);
        var byk={};
        pl.refs.forEach(function(m){
          var k=(D.referents[m]||{}).k||"unclassified";
          (byk[k]||(byk[k]=[])).push(m);
        });
        Object.keys(byk).sort(function(a,b){ return byk[b].length-byk[a].length }).forEach(function(k){
          body.appendChild(sectionTitle(kindLabel(k)+" · "+byk[k].length));
          var tl=el("div","taglist");
          byk[k].sort(function(a,b){
            return (D.referents[b].s||[]).length-(D.referents[a].s||[]).length || (a<b?-1:1);
          }).forEach(function(m){
            var r=D.referents[m];
            var t=el("button","tag"+(r.w?" wiki":""),disp(m));
            t.dataset.ref=m;
            t.title=(GEO.vias[GEO.refs[m][1]]||"")+" · "+(r.s||[]).length+" Pokémon";
            if(r.i) t.appendChild(kindTag(r.k,true));
            t.onclick=function(){ select({t:"referent",k:m}) };
            tl.appendChild(t);
          });
          body.appendChild(tl);
        });
        body.appendChild(sectionTitle("Pokémon · "+pl.n));
        body.appendChild(speciesTags(Object.keys(pl.sp).map(Number).sort(function(a,b){return a-b})));
      }
    }
    else if(sel.t==="node"){
      /* a kind, branch, family or region: describe the place, list what is in it */
      /* Count the whole subtree. Walking only the children missed every child
         that was itself a branch, which is why "life" claimed 229 Pokémon
         while one family inside it claimed 322. */
      var f=graphFocus(), kids=childrenOf(f);
      var pkids=nodeAllSpecies(f).map(Number);
      if(attrsActive()) pkids=pkids.filter(function(i){ return passAttrs(i) });
      pkids.sort(function(a,b){return a-b});
      var label={kind:"category",branch:"group of families",family:"family",region:"place of origin"}[sel.nt]||"";
      var pk=pkids.length;
      /* name what is inside, instead of a bare "4 inside" */
      var noun={family:"families",branch:"groups of families",group:"clusters",
                referent:"referents",species:"Pokémon",region:"places of origin",
                kind:"categories"}[(kids[0]||{}).t]||"inside";
      title=sel.nt==="kind"?kindLabel(sel.k):sel.k;
      sub=label+(pk?" · "+pk+" Pokémon":"")+(kids.length?" · "+kids.length+" "+noun:"");
      body.appendChild(sectionTitle("Inside"));
      var nl=el("div","taglist");
      kids.slice(0,80).forEach(function(c){
        var t=el("button","tag",disp(c.label)+(c.n?" ("+c.n+")":""));
        t.dataset.node=c.t+":"+c.k;
        if(c.fam) t.dataset.fam=c.fam;          /* a region belongs to a family */
        t.onclick=function(){ goTo(state.path.concat([{t:c.t,k:c.k}])) };
        nl.appendChild(t);
      });
      body.appendChild(nl);
      /* and the Pokémon themselves: a place that counts 19 of them should let
         you see them, not only the names of its boxes */
      if(pkids.length){
        body.appendChild(sectionTitle(pkids.length>120?"Pokémon · first 120 of "+pkids.length:"Pokémon"));
        body.appendChild(speciesTags(pkids.slice(0,120)));
      }
    }
    else {
      var s=D.species[String(sel.k)];
      title=s[0]; sub=dex(sel.k)+" · "+s[2].join(", ");
      /* Bulbapedia mixes two claims: what it is drawn from, and what it
         references. They read alike in one list, so they get their own. */
      var design=[], inspo=[];
      s[1].forEach(function(ref){
        var r=D.referents[ref.toLowerCase()];
        (r && r.x ? inspo : design).push(ref);
      });
      if(design.length){
        body.appendChild(sectionTitle("Design"));
        body.appendChild(refTags(design));
      }
      if(inspo.length){
        body.appendChild(sectionTitle("Inspiration"));
        body.appendChild(refTags(inspo,true));
      }
      var forms=Object.keys(D.forms).filter(function(f){return D.forms[f].s===sel.k});
      if(forms.length){
        body.appendChild(sectionTitle("Form-specific"));
        forms.forEach(function(f){
          var row=el("div","formrow");
          var fh=el("div","formhead");
          var fi=formSprite(f); if(fi) fh.appendChild(fi);
          fh.appendChild(el("div","fm",D.forms[f].f));
          row.appendChild(fh);
          var own=D.forms[f].own;
          if(own && own.length) row.appendChild(refTags(own));
          else row.appendChild(el("div","fnote","same origins as the base form"));
          body.appendChild(row);
        });
      }
      var a=el("a","src","Bulbapedia Origin section ↗");
      a.href="https://bulbapedia.bulbagarden.net/wiki/"+encodeURIComponent(s[0].replace(/ /g,"_"))+"_(Pok%C3%A9mon)#Origin";
      a.target="_blank"; a.rel="noopener";
      var p=el("p"); p.style.marginTop="14px"; p.appendChild(a); body.appendChild(p);
    }

    titles.appendChild(el("div","dtitle",title));
    titles.appendChild(el("div","dsub",String(sub).replace(/(\d+) /g,"$1\u00a0")));
    /* which cluster this sits inside: without it "aspen" reads as unconnected
       to "tree", though it has been nested under it all along */
    var host=null;
    if(sel.t==="group") host=sel.k;
    else if(sel.t==="referent") host=(D.referents[sel.k]||{}).g;
    if(host){
      var chain=[], seen={}, up=(D.groups[host]||{}).p;
      while(up && !seen[up] && chain.length<6){ seen[up]=1; chain.push(up); up=(D.groups[up]||{}).p }
      if(sel.t==="referent" && host && D.groups[host]) chain.unshift(host);
      if(chain.length){
        var line=el("div","dsub"); line.style.marginTop="4px";
        line.appendChild(document.createTextNode("inside "));
        chain.forEach(function(g,i){
          if(i) line.appendChild(el("span","crumbsep"," ‹ "));
          var b=el("button","crumblink",g);
          b.style.fontSize="inherit";
          b.onclick=function(){ select({t:"group",k:g}) };
          line.appendChild(b);
        });
        titles.appendChild(line);
      }
    }
    if(sel.t==="species"){ var hi=sprite(sel.k); if(hi) head.appendChild(hi) }
    head.appendChild(titles);
    var acts=el("div","dactions");
    acts.appendChild(navButtons());
    /* a flag, not the word: the panel heading is the one place where a
       line of vertical space is worth more than a label */
    var fb=el("button","flagbtn","\u2691");
    fb.title="Flag a problem with this"; fb.setAttribute("aria-label","Flag a problem with this");
    fb.onclick=function(){ var f=$("#flagform"); if(f) f.classList.toggle("hidden") };
    acts.appendChild(fb);
    head.appendChild(acts);
    /* keep the heading and the "inside" chips in view while the rest of the
       panel scrolls under them */
    var top=el("div","dtop");
    top.appendChild(head);
    var first=body.firstChild;
    if(first && first.className==="sectitle" && /^(Inside|Nested inside)$/.test(first.textContent)){
      var list=first.nextSibling;
      top.appendChild(first);
      if(list) top.appendChild(list);
    }
    d.appendChild(top); d.appendChild(body);
    wireHover(d);
    d.appendChild(flagForm(sel,title));
    d.appendChild(existingFlags(targetKey(sel)));
  }
  /* Hovering a Pokémon in the panel answers "why is it here?": the referents
     that cite it light up, and so do the category chips in the rail those
     referents belong to. Hovering a referent does the reverse. Nothing is
     clicked, nothing navigates — it only shows what is connected. */
  function wireHover(scope){
    var dexes=[].slice.call(scope.querySelectorAll(".tag[data-dex]"));
    /* A chip beside the Pokémon can be a referent, a cluster, or — in a
       category or family panel — a branch, a family or a place of origin.
       Rather than a branch per kind, each says what it is and one resolver
       turns it into the Pokémon it covers. */
    var others=[].slice.call(scope.querySelectorAll(
      ".tag[data-ref],.tag[data-cluster],.tag[data-node]"));
    if(!dexes.length && !others.length) return;
    var lit=[].concat(dexes,others);
    function clear(){
      lit.forEach(function(e){ e.classList.remove("lit") });
      litRail(null);
    }
    function nodeOf(e){
      if(e.dataset.ref) return {t:"referent",k:e.dataset.ref};
      if(e.dataset.cluster) return {t:"group",k:e.dataset.cluster};
      var bits=(e.dataset.node||"").split(":");
      var n={t:bits.shift(),k:bits.join(":")};
      if(e.dataset.fam) n.fam=e.dataset.fam;
      return n.t?n:null;
    }
    function kindOf(n){
      if(n.t==="referent") return (D.referents[n.k]||{}).k;
      if(n.t==="group") return (D.groups[n.k]||{}).k;
      if(n.t==="family") return (D.families[n.k]||{}).k;
      if(n.t==="kind") return n.k;
      if(n.t==="region") return (D.families[n.fam]||{}).k;
      return null;
    }
    /* resolved once when the panel is built, not on every mouse move */
    var covers=[];
    others.forEach(function(e){
      var n=nodeOf(e), set={};
      if(n) nodeAllSpecies(n).forEach(function(i){ set[+i]=1 });
      covers.push({el:e,node:n,set:set});
    });
    dexes.forEach(function(d){
      var id=+d.dataset.dex;
      d.addEventListener("mouseenter",function(){
        clear();
        covers.forEach(function(c){ if(c.set[id]) c.el.classList.add("lit") });
        /* the rail reads the Pokémon's own origins, so it lights even where
           this panel lists places or families rather than referents */
        litRail(kindsOf(id));
      });
      d.addEventListener("mouseleave",clear);
    });
    covers.forEach(function(c){
      c.el.addEventListener("mouseenter",function(){
        clear();
        dexes.forEach(function(d){ if(c.set[+d.dataset.dex]) d.classList.add("lit") });
        var k=kindOf(c.node||{}); if(k){ var m={}; m[k]=1; litRail(m) }
      });
      c.el.addEventListener("mouseleave",clear);
    });
    scope.addEventListener("mouseleave",clear);
  }
  function navButtons(){
    var nav=el("div","dnav");
    [["\u2039",-1,"Back"],["\u203A",1,"Forward"]].forEach(function(o){
      var b=el("button","navbtn",o[0]);
      b.type="button"; b.title=o[2]+(o[1]<0?" (alt \u2190)":" (alt \u2192)");
      b.setAttribute("aria-label",o[2]);
      b.disabled = o[1]<0 ? hpos<=0 : hpos>=hist.length-1;
      b.onclick=function(){ travel(o[1]) };
      nav.appendChild(b);
    });
    return nav;
  }
  function sectionTitle(t){ return el("div","sectitle",t) }
  /* Where a referent is from, said plainly enough to audit: the place, the
     point it is pinned at, the claim that put it there, and how far from the
     referent that claim was made. Everything here comes from geo.json, which
     is generated — correcting one means correcting the pass that wrote it,
     not this panel. */
  var ORIGINTIER=["from its own Wikidata entry","one hop out, through what it belongs to",
                  "from the culture area this dataset files it under"];
  function originSection(name){
    if(!GEO) return null;                        /* still loading; the panel redraws when it lands */
    var row=GEO.refs[name], r=D.referents[name]||{};
    var box=el("div");
    box.appendChild(sectionTitle("Where it is from"));
    var card=el("div","origincard");
    box.appendChild(card);
    if(!row){
      card.classList.add("empty");
      card.appendChild(el("p","onote", r.w
        ? "Not placed \u2014 neither its own Wikidata entry nor what it belongs to says where it is from."
        : "Not placed \u2014 no Wikipedia article is linked, so there was nothing to ask."));
      return box;
    }
    var p=GEO.places[row[0]], tier=row[2];
    var head=el("div","oplace");
    var btn=el("button","tag origin"+(tier===2?" soft":""),p[0]);
    btn.title="Show this place on the Atlas";
    btn.onclick=function(){ openOnAtlas() };
    head.appendChild(btn);
    var go=el("button","oshow","see the pin \u2192");
    go.type="button"; go.onclick=function(){ openOnAtlas() };
    head.appendChild(go);
    card.appendChild(head);
    /* the three things an audit needs, labelled: the point, the claim that
       produced it, and how far from the referent that claim was made */
    var facts=el("dl","ofacts");
    function fact(k,v,mono){
      facts.appendChild(el("dt","",k));
      facts.appendChild(el("dd",mono?"num":"",v));
    }
    fact("pinned at",p[1].toFixed(2)+", "+p[2].toFixed(2),true);
    fact("claim",GEO.vias[row[1]]||"?");
    fact("source",ORIGINTIER[tier]||"");
    card.appendChild(facts);
    if(tier===2) card.appendChild(el("p","onote","A region, not a spot \u2014 the pin stands for the whole area."));
    if(p[3]){
      var wd=el("a","src","Wikidata: "+p[3]+" \u2197");
      wd.href="https://www.wikidata.org/wiki/"+p[3];
      wd.target="_blank"; wd.rel="noopener noreferrer";
      var wrap=el("p","olink"); wrap.appendChild(wd);
      card.appendChild(wrap);
    }
    return box;
  }
  /* Keep the selection and switch tabs: the atlas lights up the place the
     open referent came from, with that referent marked in its fan. */
  function openOnAtlas(){
    state.tab="atlas";
    ["clusters","map","atlas","species","flags"].forEach(function(o){
      $("#tab-"+o).setAttribute("aria-selected",o==="atlas"?"true":"false");
    });
    record(); render();
  }
  function unionSpecies(members){
    var set={}; members.forEach(function(m){ (D.referents[m]?D.referents[m].s:[]).forEach(function(id){set[id]=1}) });
    return Object.keys(set).map(Number).sort(function(a,b){return a-b});
  }
  function refTags(list,soft){
    var tl=el("div","taglist");
    (list||[]).forEach(function(ref){
      var key=String(ref).toLowerCase(), known=!!D.referents[key];
      var t=el(known?"button":"span","tag"+(soft?" soft":""),ref);
      if(known){ t.dataset.ref=key; t.onclick=function(){ select({t:"referent",k:key}) } }
      tl.appendChild(t);
    });
    return tl;
  }
  /* when a referent belongs to one FORM of a Pokémon, that form is what it
     refers to: "Dobermann" is Zygarde-10%, not the 50% forme. */
  function formFor(refKey,id){
    var m=D.formrefs && D.formrefs[String(refKey).toLowerCase()];
    return m ? m[String(id)] : null;
  }
  function speciesTags(ids,refKey){
    var tl=el("div","taglist");
    ids.forEach(function(id){
      var sp=D.species[String(id)]; if(!sp) return;
      var t=el("button","tag dex");
      t.dataset.dex=id;
      var slug=refKey?formFor(refKey,id):null;
      var im=(slug&&formSprite(slug))||sprite(id);
      if(im){ im.classList.add("spr"); t.appendChild(im) }
      t.appendChild(el("span","dexno",dex(id)));
      t.appendChild(document.createTextNode(sp[0]));
      if(slug){
        var f=(D.forms[slug]||{}).f;
        if(f) t.appendChild(el("span","formtag"," "+f));
      }
      t.onclick=function(){select({t:"species",k:id})};
      tl.appendChild(t);
    });
    return tl;
  }

  /* ---------- visual map ----------
     The same tree the Browse tab walks, drawn as nodes: the focus in the
     middle, its children around it, one hop at a time so the 2,600 clusters
     never arrive at once. d3 is fetched the first time the tab is opened. */
  /* Browse and Map are two drawings of the same place: both read and write
     state.path, so switching tabs keeps you where you were. */
  var D3=null, gstate={showAll:false};
  function graphFocus(forMap){
    /* a search is a place like any other: on the map it becomes the centre,
       with what it found around it. Only the map asks for this. */
    /* the search is a place you start from: once you have gone somewhere, the
       map shows where you are, even while the box still filters the list */
    if(forMap && state.q && state.poke==null && !state.path.length){
      return {t:"search",k:state.q,label:"\u201c"+state.q+"\u201d",kind:"concept",n:0,search:true};
    }
    if(state.poke!=null && D.species[String(state.poke)]){
      var sp=D.species[String(state.poke)];
      return {t:"species",k:state.poke,label:sp[0],kind:(sp[2]||[])[0],n:1,poke:true};
    }
    return graphFocusFor(stepsOf());
  }
  function graphFocusFor(st){
    if(!st.length) return {t:"root",k:"Everything",label:"Everything"};
    var last=st[st.length-1];
    var out={t:last.t,k:last.k,label:last.t==="kind"?kindLabel(last.k):disp(last.k)};
    if(last.t==="family"){ var f=D.families[last.k]; if(f) out.kind=f.k; }
    else if(last.t==="group"){ var g=D.groups[last.k]; if(g){ out.kind=g.k; out.n=g.tn||g.n } }
    else if(last.t==="referent"){ var r=D.referents[last.k]; if(r){ out.kind=r.k; out.n=r.s.length } }
    else if(last.t==="kind"){ out.kind=last.k }
    else if(last.t==="region"){
      var pf=st[st.length-2]; out.fam=pf&&pf.k; out.kind=(D.families[out.fam]||{}).k;
    }
    return out;
  }
  var GCAP=22;   /* a ring of more than this stops being readable */

  function kindHue(k){
    var map={"life":122,"object":210,"concept":272,"folklore":300,"mythology":340,"person":15,"earth & sky":190,"media & art":258,"prehistoric":45,"food":88};
    return map[k]!=null?map[k]:0;
  }
  function speciesOfGroup(g){
    var sp={};
    (g.m||[]).forEach(function(m){ var r=D.referents[m]; if(r) r.s.forEach(function(i){sp[i]=1}) });
    (g.ch||[]).forEach(function(c){ var k=D.groups[c]; if(k) Object.keys(speciesOfGroup(k)).forEach(function(i){sp[i]=1}) });
    return sp;
  }
  var GSPRITES=4;   /* above this a node shows a plain circle, not a mush of sprites */
  function nodeSpecies(ref){
    if(!ref) return [];
    if(ref.t==="species") return [ref.k];
    if(ref.t==="referent") return (D.referents[ref.k]||{}).s||[];
    if(ref.t==="group"){
      var g=D.groups[ref.k]; if(!g) return [];
      return Object.keys(speciesOfGroup(g)).map(Number);
    }
    return [];
  }
  /* The rail's filters already narrow Browse and the Pokémon tab. The map
     ignored them, so the three columns disagreed about what was in scope.
     This counts a node's Pokémon whatever kind of node it is. */
  function nodeAllSpecies(n){
    var sp={};
    function addFam(f){
      famGroups(f).forEach(function(g){
        ((D.groups[g]||{}).m||[]).forEach(function(m){
          var r=D.referents[m]; if(r) r.s.forEach(function(i){ sp[i]=1 });
        });
      });
    }
    if(n.t==="root") Object.keys(D.species).forEach(function(i){ sp[i]=1 });
    else if(n.t==="kind") Object.keys(D.families).forEach(function(f){
      if((D.families[f].k||"unclassified")===n.k) addFam(f) });
    else if(n.t==="branch") Object.keys(D.branches||{}).forEach(function(k){
      (D.branches[k]||[]).forEach(function(d){ if(d[0]===n.k) d[1].forEach(addFam) }) });
    else if(n.t==="family") addFam(n.k);
    else if(n.t==="region") ((((D.families[n.fam]||{}).rg)||{})[n.k]||[]).forEach(function(g){
      Object.keys(speciesOfGroup(D.groups[g]||{})).forEach(function(i){ sp[i]=1 }) });
    else nodeSpecies(n).forEach(function(i){ sp[i]=1 });
    return Object.keys(sp);
  }
  /* An inferred category is a guess the pipeline made, not something read off
     Bulbapedia. This narrows all three columns to what still carries one, so
     the backlog can be walked through and corrected. */
  var INFCACHE=null;
  function refsUnder(n){
    var out=[];
    function addGroup(g){
      var gg=D.groups[g]; if(!gg) return;
      (gg.m||[]).forEach(function(m){ out.push(m) });
      (gg.ch||[]).forEach(addGroup);
    }
    function addFam(f){ famGroups(f).forEach(addGroup) }
    if(n.t==="referent") out.push(n.k);
    else if(n.t==="group") addGroup(n.k);
    else if(n.t==="family") addFam(n.k);
    else if(n.t==="kind") Object.keys(D.families).forEach(function(f){
      if((D.families[f].k||"unclassified")===n.k) addFam(f) });
    else if(n.t==="branch") Object.keys(D.branches||{}).forEach(function(k){
      (D.branches[k]||[]).forEach(function(d){ if(d[0]===n.k) d[1].forEach(addFam) }) });
    else if(n.t==="region") ((((D.families[n.fam]||{}).rg)||{})[n.k]||[]).forEach(addGroup);
    else if(n.t==="species"){
      var sp=D.species[String(n.k)];
      (sp?sp[1]:[]).forEach(function(x){ out.push(String(x).toLowerCase()) });
    }
    return out;
  }
  function hasInferred(n){
    if(!state.onlyinf) return true;
    if(!INFCACHE) INFCACHE={};
    var key=n.t+":"+n.k;
    if(INFCACHE[key]!=null) return INFCACHE[key];
    var hit=refsUnder(n).some(function(m){ var r=D.referents[m]; return r && r.i });
    return (INFCACHE[key]=hit);
  }
  function mapCount(n){
    if(!attrsActive()) return n.n||0;
    var ids=nodeAllSpecies(n), k=0;
    for(var i=0;i<ids.length;i++) if(passAttrs(ids[i])) k++;
    return k;
  }

  function childrenOf(node){
    var out=[];
    if(node.t==="root"){
      kindRows().forEach(function(r){ out.push({t:"kind",k:r.name,label:kindLabel(r.name),kind:r.name,n:r.n,open:true}) });
    } else if(node.t==="kind"){
      var br=branchRows(node.k);
      if(br) br.forEach(function(r){ out.push({t:r.fams.length===1?"family":"branch",
            k:r.fams.length===1?r.fams[0]:r.name,label:r.name,kind:node.k,n:r.n,open:true}) });
      else Object.keys(D.families).filter(function(n){return (D.families[n].k||"unclassified")===node.k})
            .forEach(function(n){ out.push({t:"family",k:n,label:n,kind:node.k,n:D.families[n].n,open:true}) });
    } else if(node.t==="branch"){
      /* look the branch up directly: the map has no Browse path to lean on */
      var fams=[];
      Object.keys(D.branches||{}).forEach(function(kind){
        (D.branches[kind]||[]).forEach(function(d){ if(d[0]===node.k) fams=d[1] });
      });
      fams.forEach(function(n){
        if(D.families[n]) out.push({t:"family",k:n,label:n,kind:D.families[n].k,n:D.families[n].n,open:true});
      });
    } else if(node.t==="family"){
      var f=D.families[node.k];
      if(f.rg) Object.keys(f.rg).forEach(function(rg){
        out.push({t:"region",k:rg,label:rg,kind:f.k,n:f.rg[rg].length,open:true,fam:node.k}) });
      else f.c.concat(f.l).forEach(function(g){ out.push(groupNode(g)) });
    } else if(node.t==="region"){
      ((D.families[node.fam]||{}).rg||{})[node.k].forEach(function(g){ out.push(groupNode(g)) });
    } else if(node.t==="group"){
      (D.groups[node.k].ch||[]).forEach(function(c){ out.push(groupNode(c)) });
      (D.groups[node.k].m||[]).forEach(function(m){
        var r=D.referents[m];
        if(r) out.push({t:"referent",k:m,label:disp(m),kind:r.k,n:r.s.length,open:r.s.length>0});
      });
    } else if(node.t==="search"){
      /* the same matcher the Browse list uses, so both tabs find the same things */
      groupRows().slice(0,GCAP).forEach(function(r){
        out.push({t:"group",k:r.name,label:r.name,kind:r.g.k,n:r.g.tn||r.g.n,open:true});
      });
    } else if(node.t==="species" && node.poke){
      /* every referent this Pokémon is drawn from, design and allusion alike */
      var sp=D.species[String(node.k)]||["",[]];
      (sp[1]||[]).forEach(function(ref){
        var key=String(ref).toLowerCase(), r=D.referents[key];
        out.push({t:"referent",k:r?key:ref,label:ref,kind:r?r.k:"unclassified",
                  n:r?r.s.length:0,open:!!r});
      });
      Object.keys(D.forms).forEach(function(f){
        if(D.forms[f].s!==node.k) return;
        (D.forms[f].own||[]).forEach(function(ref){
          var key=String(ref).toLowerCase(), r=D.referents[key];
          if(out.some(function(o){return o.k===key||o.k===ref})) return;
          out.push({t:"referent",k:r?key:ref,label:ref+" ("+D.forms[f].f+")",
                    kind:r?r.k:"unclassified",n:r?r.s.length:0,open:!!r});
        });
      });
    } else if(node.t==="referent"){
      (D.referents[node.k].s||[]).forEach(function(id){
        var sp=D.species[String(id)];
        if(sp) out.push({t:"species",k:id,label:sp[0],kind:(sp[2]||[])[0],n:1,open:false});
      });
    }
    return out;
  }
  function groupNode(g){
    var gg=D.groups[g];
    /* a cluster holding one referent and nothing else IS that referent, so
       opening it would show the same thing again — unless that referent covers
       several Pokémon, and they are what you came to see: "clydesdale" is one
       referent but two horses, and it should open onto them. */
    var solo=(gg.ch||[]).length===0 && (gg.m||[]).length<=1;
    var sref=solo?((gg.m||[])[0]||null):null;
    var only=solo && (!sref || ((D.referents[sref]||{s:[]}).s||[]).length<=1);
    return {t:"group",k:g,label:disp(g),kind:gg.k,n:gg.tn||gg.n,open:!only,
            only:only?sref:null,
            kids:(gg.ch||[]).length+(gg.m||[]).length};
  }

  function openGraph(node){
    gstate.showAll=false;
    if(node.t==="species"){ select({t:"species",k:node.k}); return }
    /* from a Pokémon's fan there is no path to append to: route the referent
       to wherever it sits in the tree */
    if(state.poke!=null || state.q){
      /* picking a result is the end of the search: drop it so the map shows
         where you landed instead of the ring you came from */
      if(state.q){ state.q=""; $("#q").value="" }
      select({t:node.t,k:node.k}); return;
    }
    goTo(state.path.concat([{t:node.t,k:node.k}]));
  }
  function graphUp(){
    if(state.q && state.poke==null){     /* the centre IS the search: clear it */
      state.q=""; $("#q").value=""; state.limit=120;
      record(); render(); return;
    }
    if(state.poke!=null){        /* step off the Pokémon, back to the tree */
      state.poke=null; gstate.showAll=false;
      state.sel=state.path.length?state.sel:null;
      record(); renderDetail(); render(); return;
    }
    if(!state.path.length) return;
    gstate.showAll=false; goBackTo(state.path.slice(0,-1));
  }

  /* the ring is laid out for the pane it was drawn in, so a resized pane
     needs a fresh layout — debounced, since a drag fires this continuously */
  var regrow=null;
  function watchGraphSize(){
    if(!window.ResizeObserver) return;
    try{
      new ResizeObserver(function(){
        if(state.tab!=="map" || !D3 || !D) return;
        clearTimeout(regrow);
        regrow=setTimeout(function(){ if(state.tab==="map") drawGraph() },180);
      }).observe($("#graph"));
    }catch(e){}
  }

  function ensureD3(){
    if(D3) return Promise.resolve(D3);
    if(window.d3){ D3=window.d3; return Promise.resolve(D3) }
    return new Promise(function(res,rej){
      var sc=document.createElement("script");
      sc.src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js";
      sc.onload=function(){ D3=window.d3; res(D3) };
      sc.onerror=rej;
      document.head.appendChild(sc);
    });
  }

  var graphWatched=false;
  function drawGraph(){
    var host=$("#graph"), svgEl=$("#gsvg");
    if(!D3||!D) return;
    if(!graphWatched){ graphWatched=true; watchGraphSize() }
    var d3=D3;
    var focus=graphFocus(true), all=childrenOf(focus);
    /* a filtered-out node is not drawn, and the counts shown are the filtered
       ones, so the ring says the same thing as the list beside it */
    var filtering=attrsActive()||state.onlyinf;
    if(filtering){
      var keep=[];
      all.forEach(function(c){
        if(!hasInferred(c)) return;
        var m=mapCount(c); if(!m) return;
        var cc={}; for(var k in c) cc[k]=c[k];
        cc.n=m; keep.push(cc);
      });
      all=keep;
    }
    /* biggest first, so a capped ring still shows what matters */
    all=all.slice().sort(function(a,b){ return (b.n||0)-(a.n||0) || (a.label<b.label?-1:1) });
    var hidden=0, kids=all;
    if(!gstate.showAll && all.length>GCAP){ kids=all.slice(0,GCAP); hidden=all.length-GCAP; }
    var w=host.clientWidth||900, h=svgEl.clientHeight||600;
    var ring=Math.min(h,w)*0.36;
    var nodes=[{id:"__focus",label:focus.label||focus.k,kind:focus.kind||focus.k,
                n:focus.n||0,focus:true,fx:w/2,fy:h/2}];
    var shown=kids.length+(hidden?1:0);
    kids.forEach(function(c,i){
      var a=(i/shown)*Math.PI*2;
      nodes.push({id:"c"+i,ref:c,label:c.label,kind:c.kind,n:c.n,
                  x:w/2+Math.cos(a)*ring, y:h/2+Math.sin(a)*ring});
    });
    if(hidden){
      var a=((shown-1)/shown)*Math.PI*2;
      nodes.push({id:"__more",more:true,label:"+"+hidden+" more",kind:focus.kind,n:0,
                  x:w/2+Math.cos(a)*ring, y:h/2+Math.sin(a)*ring});
    }
    var links=nodes.slice(1).map(function(n){return {source:"__focus",target:n.id}});
    /* Size is relative to the ring you are looking at, not to the whole
       dataset: inside Carnivores, "cat" should dwarf "hyena" even though both
       are small next to "animal". */
    var counts=nodes.filter(function(d){return !d.focus && !d.more})
                    .map(function(d){return Math.max(d.n||0,1)});
    var lo=counts.length?Math.min.apply(null,counts):1;
    var hi=counts.length?Math.max.apply(null,counts):1;
    var area=d3.scaleSqrt().domain([lo,Math.max(hi,lo+1)]).range([26,hi/lo>3?62:48]);
    var R=function(d){
      if(d.focus) return focus.poke?56:42;
      if(d.more) return 22;
      var r=area(Math.max(d.n||0,1));
      if(SPR && d.ref){
        /* a node wearing a face is sized for the face, not for its count */
        var c=nodeSpecies(d.ref).length;
        if(c>0 && c<=GSPRITES) r=Math.max(r,c===1?34:42);
      }
      return r;
    };

    var svg=d3.select(svgEl); svg.selectAll("*").remove();
    svg.attr("viewBox","0 0 "+w+" "+h);
    var defs=svg.append("defs");
    /* one soft gradient per hue on screen, so bubbles read as glass, not discs */
    var hues={}; nodes.forEach(function(d){ hues[kindHue(d.kind)]=1 });
    Object.keys(hues).forEach(function(hue){
      var g=defs.append("radialGradient").attr("id","gh"+hue)
        .attr("cx","35%").attr("cy","30%").attr("r","75%");
      g.append("stop").attr("offset","0%").attr("stop-color","hsl("+hue+" 70% 62% / .55)");
      g.append("stop").attr("offset","65%").attr("stop-color","hsl("+hue+" 55% 45% / .26)");
      g.append("stop").attr("offset","100%").attr("stop-color","hsl("+hue+" 50% 38% / .12)");
    });
    var glow=defs.append("filter").attr("id","gglow").attr("x","-45%").attr("y","-45%")
      .attr("width","190%").attr("height","190%");
    glow.append("feGaussianBlur").attr("stdDeviation","4").attr("result","b");
    var fm=glow.append("feMerge"); fm.append("feMergeNode").attr("in","b");
    fm.append("feMergeNode").attr("in","SourceGraphic");

    var root=svg.append("g");
    var zoom=d3.zoom().scaleExtent([0.25,4]).on("zoom",function(e){ root.attr("transform",e.transform) });
    svg.call(zoom);

    /* once the ring settles, frame it: big rings zoom out instead of spilling
       over the edge of the pane. */
    var fitted=false;
    function fit(animate){
      var pad=56, x0=1e9, y0=1e9, x1=-1e9, y1=-1e9;
      nodes.forEach(function(d){
        /* a sprite overhangs its circle and the label sits below it, so the
           box has to be wider than the node itself or the ring gets clipped */
        var r=R(d)*1.2+30;
        x0=Math.min(x0,d.x-r); x1=Math.max(x1,d.x+r);
        y0=Math.min(y0,d.y-r); y1=Math.max(y1,d.y+r);
      });
      var bw=Math.max(x1-x0,1), bh=Math.max(y1-y0,1);
      var cap = nodes.length<=3 ? 1.5 : nodes.length<=8 ? 1.35 : 1.2;
      var k=Math.min((w-pad)/bw,(h-pad)/bh,cap);
      var tx=w/2-k*(x0+x1)/2, ty=h/2-k*(y0+y1)/2;
      var t=d3.zoomIdentity.translate(tx,ty).scale(k);
      if(animate) svg.transition().duration(420).call(zoom.transform,t);
      else svg.call(zoom.transform,t);
      fitted=true;
    }

    var link=root.append("g").selectAll("path").data(links).join("path")
      .attr("class","glink").attr("fill","none")
      .attr("stroke",function(d){ return "hsl("+kindHue((d.target.kind)||focus.kind)+" 40% 52% / .35)" })
      .attr("stroke-width",1.1);
    var node=root.append("g").selectAll("g").data(nodes).join("g")
      .attr("class",function(d){return "gnode"+(d.focus?" focus":"")});
    node.append("circle").attr("r",R)
      .attr("fill",function(d){return d.more?"transparent":"url(#gh"+kindHue(d.kind)+")"})
      .attr("stroke",function(d){return d.more?"var(--rule-strong)":"hsl("+kindHue(d.kind)+" 60% 62% / .85)"})
      .attr("stroke-width",function(d){return d.focus?2.2:1.4})
      .attr("stroke-dasharray",function(d){return d.more?"3 3":null})
      .attr("filter",function(d){return d.focus?"url(#gglow)":null});
    /* the count lives inside the bubble when there is room and no sprite */
    node.filter(function(d){
        if(d.more||d.focus||!d.n) return false;
        var c=SPR&&d.ref?nodeSpecies(d.ref).length:0;
        return R(d)>=17 && !(c>0&&c<=GSPRITES);
      })
      .append("text").attr("class","gcount").attr("text-anchor","middle").attr("dy","0.34em")
      .style("font-size",function(d){return Math.max(10,Math.min(17,R(d)*0.38))+"px"})
      .text(function(d){return d.n>=10000?Math.round(d.n/1000)+"k":d.n});
    /* anything flagged wears it here too, not only in the side panel */
    node.each(function(d){
      var fl=d.ref?flagsOn(d.ref.t,d.ref.k):(d.focus?flagsOn(focus.t,focus.k):null);
      if(!fl) return;
      var g=d3.select(this), r=R(d);
      g.classed("flagged",true);
      g.append("circle").attr("class","gflagring").attr("r",r+5)
        .style("opacity",fl.open?0.85:0.4);
      var a=-Math.PI/4, bx=Math.cos(a)*r, by=Math.sin(a)*r;
      var badge=g.append("g").attr("class","gflag").attr("transform","translate("+bx+","+by+")");
      badge.append("circle").attr("r",7.5)
        .attr("fill",fl.open?"var(--flag)":"var(--rule-strong)")
        .attr("stroke","var(--card)").attr("stroke-width",1.6);
      badge.append("text").attr("text-anchor","middle").attr("dy","0.33em")
        .style("font-family","var(--mono)").style("font-size","9px").style("font-weight","600")
        .style("fill","var(--card)").text(fl.total>9?"9+":fl.total);
    });
    /* Sprites wherever they still read: a node standing for one Pokémon wears
       its face, two to four show a small cluster, more than that would be mush
       so the circle keeps its size badge instead. */
    if(SPR){
      node.each(function(d){
        /* the Pokémon at the centre of its own fan wears its face */
        if(d.focus && focus.poke && SPR[String(focus.k)]){
          var fr=R(d)*1.08;
          d3.select(this).append("image")
            .attr("href","data:image/png;base64,"+SPR[String(focus.k)])
            .attr("x",-fr).attr("y",-fr).attr("width",fr*2).attr("height",fr*2)
            .attr("preserveAspectRatio","xMidYMid meet")
            .style("image-rendering","pixelated").style("pointer-events","none");
          return;
        }
        /* a species node under a referent shows that referent's form */
        if(d.ref && d.ref.t==="species" && focus.t==="referent"){
          var fslug=formFor(focus.k,d.ref.k);
          if(fslug && FSPR && FSPR[fslug]){
            var rr=R(d)*1.15;
            d3.select(this).append("image")
              .attr("href","data:image/png;base64,"+FSPR[fslug])
              .attr("x",-rr).attr("y",-rr).attr("width",rr*2).attr("height",rr*2)
              .attr("preserveAspectRatio","xMidYMid meet")
              .style("image-rendering","pixelated").style("pointer-events","none");
            return;
          }
        }
        var ids=nodeSpecies(d.ref).filter(function(i){return SPR[String(i)]});
        if(!ids.length || ids.length>GSPRITES) return;
        /* when a referent is about one FORM, that form is the face to show:
           "shetland pony" is Galarian Ponyta, not the Kanto one. A cluster
           standing for a single referent inherits the same override. */
        var rk=null;
        if(d.ref.t==="referent") rk=d.ref.k;
        else if(d.ref.t==="group"){
          var gm=(D.groups[d.ref.k]||{}).m||[];
          if(gm.length===1 && !((D.groups[d.ref.k]||{}).ch||[]).length) rk=gm[0];
        }
        function faceOf(id){
          var slug=rk?formFor(rk,id):null;
          return (slug && FSPR && FSPR[slug]) ? FSPR[slug] : SPR[String(id)];
        }
        var g=d3.select(this), r=R(d);
        if(ids.length===1){
          var r1=r*1.15;
          g.append("image").attr("href","data:image/png;base64,"+faceOf(ids[0]))
            .attr("x",-r1).attr("y",-r1).attr("width",r1*2).attr("height",r1*2);
        } else {
          var size=r*1.35, step=(Math.PI*2)/ids.length;
          ids.forEach(function(id,i){
            var a=step*i-Math.PI/2, dx=Math.cos(a)*r*0.58, dy=Math.sin(a)*r*0.58;
            g.append("image").attr("href","data:image/png;base64,"+faceOf(id))
              .attr("x",dx-size/2).attr("y",dy-size/2)
              .attr("width",size).attr("height",size);
          });
        }
        g.selectAll("image").attr("preserveAspectRatio","xMidYMid meet")
          .style("image-rendering","pixelated").style("pointer-events","none");
      });
    }
    node.append("title").text(function(d){
      var fl=d.ref?flagsOn(d.ref.t,d.ref.k):null;
      return d.label+(d.n?" · "+d.n+" Pokémon":"")+
        (fl?" · "+fl.total+" flag"+(fl.total===1?"":"s")+(fl.open?" ("+fl.open+" open)":" (applied)"):"");
    });
    /* SVG text does not wrap, so a long name is laid out over up to three
       lines. A tspan with its own dy overrides the dy on <text>, which is why
       the label used to land on top of the count: give each line an explicit y. */
    node.append("text").attr("class","glabel").attr("text-anchor","middle")
      .each(function(d){
        var words=String(d.label||"").split(/\s+/), lines=[], line="";
        words.forEach(function(w){
          var next=line?line+" "+w:w;
          if(next.length>16 && line){ lines.push(line); line=w } else line=next;
        });
        if(line) lines.push(line);
        if(lines.length>3){ lines=lines.slice(0,2).concat([lines.slice(2).join(" ")]); }
        var t=d3.select(this), top=R(d)+16, lh=13;
        if(d.focus) t.style("font-size","12.5px").style("fill","var(--ink)");
        lines.forEach(function(ln,i){
          t.append("tspan").attr("x",0).attr("y",top+i*lh).text(ln);
        });
      });
    /* an arrival you can follow: the ring fades up instead of appearing */
    node.style("opacity",0).transition().duration(320).style("opacity",1);
    link.style("opacity",0).transition().duration(420).delay(80).style("opacity",1);
    node.on("mouseenter",function(){ d3.select(this).raise().classed("hot",true) })
        .on("mouseleave",function(){ d3.select(this).classed("hot",false) });
    node.filter(function(d){return !d.focus}).on("click",function(e,d){
      if(d.more){ gstate.showAll=true; drawGraph(); return }
      if(d.ref.open!==false){ openGraph(d.ref); return }
      if(d.ref.t==="species") select({t:"species",k:d.ref.k});
      else if(d.ref.only) select({t:"referent",k:d.ref.only});
      else select({t:d.ref.t,k:d.ref.k});
    });
    node.filter(function(d){return !!d.focus}).on("click",graphUp);

    var sim=d3.forceSimulation(nodes)
      .force("link",d3.forceLink(links).id(function(d){return d.id})
        .distance(function(l){
          var few=Math.max(0,6-kids.length)*30;        /* a lonely pair needs air */
          return R(l.source)+R(l.target)+100+few+Math.random()*40;
        }).strength(0.7))
      .force("charge",d3.forceManyBody().strength(kids.length<6?-900:-320))
      .force("collide",d3.forceCollide(function(d){return R(d)+34}).strength(1))
      .on("end",function(){ fit(true) })
      .on("tick",function(){
        link.attr("d",function(d){
          var x1=d.source.x,y1=d.source.y,x2=d.target.x,y2=d.target.y;
          var dx=x2-x1, dy=y2-y1, dr=Math.hypot(dx,dy)*1.9;
          return "M"+x1+","+y1+"A"+dr+","+dr+" 0 0,1 "+x2+","+y2;
        });
        node.attr("transform",function(d){return "translate("+d.x+","+d.y+")"});
      });
    var ticks=0;
    sim.on("tick.fit",function(){ if(++ticks===60) fit(false) });
    setTimeout(function(){ if(!fitted) fit(false) },1400);   /* belt and braces */
    node.call(d3.drag()
      .on("start",function(e,d){ if(!e.active) sim.alphaTarget(0.25).restart(); d.fx=d.x; d.fy=d.y })
      .on("drag",function(e,d){ d.fx=e.x; d.fy=e.y })
      .on("end",function(e,d){ if(!e.active) sim.alphaTarget(0); if(!d.focus){ d.fx=null; d.fy=null } }));

    var st=stepsOf();
    if(!all.length){
      $("#graphnote").textContent = filtering
        ? focus.label+" · nothing here matches the filters · clear them in the rail"
        : focus.label+" · nothing inside";
      return;
    }
    if(focus.search){
      $("#graphnote").textContent=focus.label+" · "+all.length+
        " cluster"+(all.length===1?"":"s")+" found"+(filtering?" · filtered":"")+
        " · click one to open it where it sits · click the middle to clear";
      return;
    }
    if(focus.poke){
      $("#graphnote").textContent=focus.label+" · "+all.length+
        " referent"+(all.length===1?"":"s")+" · click one to open it where it sits · click the middle to go back";
      return;
    }
    var crumbs=["Everything"].concat(st.filter(function(x,i){
      var nx=st[i+1];
      return !(x.t==="group" && nx && nx.t==="referent" && nx.k===x.k);
    }).map(function(t){return t.t==="kind"?kindLabel(t.k):disp(t.k)}));
    if($("#graph").classList.contains("hidden")) return;
    /* the hint names what the ring holds, for the same reason the rows do */
    var ringNoun={family:"families",branch:"groups of families",group:"clusters",
                  referent:"referents",species:"Pokémon",region:"places of origin",
                  kind:"categories"}[(all[0]||{}).t]||"inside";
    $("#graphnote").textContent=crumbs.join(" › ")+" · "+all.length+" "+ringNoun+
      (filtering?(state.onlyinf?" · inferred only":" · filtered"):"")+
      (hidden?" · showing the "+GCAP+" biggest":"")+
      (state.path.length?" · click the middle node to go back":"");
  }

  /* ---------- atlas ----------
     The visual map above answers "what sits inside what". This one answers
     "where did it come from": one pin per place, sized by how many Pokémon
     trace back to it, with the place's own referents fanned out around it
     when you open one.

     No tiles and no projection library. tools/worldgen.py pre-projects
     Natural Earth 110m outlines (public domain) to plate carrée path data, so
     a point goes on the map with two multiplications and the land takes its
     colours from the page's own theme. data/geo.json says where each referent
     is from, and how that was arrived at — a claim on its own Wikidata item,
     one hop out through what it belongs to, or the culture area the dataset
     already files it under. The third is a region, not a spot, so its pins
     are drawn hollow-dashed: Celtic folklore is not at one coordinate. */
  var WORLD=null, GEO=null, atlasWant=null, geoWant=null, atlasWired=false, atlasBroken=false;
  var AHOME={cx:1000,cy:500,w:2000};   /* the whole globe, exactly filling a 2:1 canvas */
  var AVIEW={cx:AHOME.cx,cy:AHOME.cy,w:AHOME.w};
  var APLACES=null, ABYNAME=null, ALABELS=true, ALASTFOCUS=null;

  /* geo.json is 33 KB and the side panel wants it on every tab, so it loads
     with the dataset; world.json is the 134 KB of outlines, and only the
     Atlas tab ever needs those. */
  function ensureGeo(){
    if(geoWant) return geoWant;
    geoWant=fetch("geo.json").then(function(r){ if(!r.ok) throw new Error("geo"); return r.json() })
      .then(function(j){ GEO=j; APLACES=null; return j });
    return geoWant;
  }
  function ensureAtlas(){
    if(atlasWant) return atlasWant;
    atlasWant=Promise.all([
      fetch("world.json").then(function(r){ if(!r.ok) throw new Error("world"); return r.json() }),
      ensureGeo()
    ]).then(function(a){ WORLD=a[0]; APLACES=null });
    return atlasWant;
  }
  /* plate carrée: the whole globe across WORLD.w by WORLD.h units */
  function ax(lon){ return (lon+180)/360*WORLD.w }
  function ay(lat){ return (90-lat)/180*WORLD.h }
  function arect(){
    var svg=$("#asvg");
    var r=svg?svg.getBoundingClientRect():null;
    return (r && r.width && r.height) ? r : {left:0,top:0,width:1000,height:520};
  }
  /* the viewBox follows the box's own shape, so the map never letterboxes */
  function aview(){
    var r=arect(), h=AVIEW.w*(r.height/r.width);
    return {x:AVIEW.cx-AVIEW.w/2, y:AVIEW.cy-h/2, w:AVIEW.w, h:h};
  }
  /* world units per CSS pixel — what keeps a pin the same size at any zoom */
  function aunit(){ return AVIEW.w/arect().width }
  function atoworld(cx,cy){
    var r=arect(), v=aview();
    return {x:v.x+(cx-r.left)/r.width*v.w, y:v.y+(cy-r.top)/r.height*v.h};
  }
  function atoscreen(x,y){
    var r=arect(), v=aview();
    return {x:r.left+(x-v.x)/v.w*r.width, y:r.top+(y-v.y)/v.h*r.height};
  }

  /* Pins obey the rail and the search box, like every other view: the
     category chips filter which referents count, and a search dims the
     places that have nothing matching rather than hiding them — an empty
     Japan would read as "no Japanese origins", which is not what it means. */
  function atlasPlaces(){
    if(APLACES) return APLACES;
    if(!GEO||!D) return [];
    var bag={};
    Object.keys(GEO.refs).forEach(function(name){
      var r=D.referents[name];
      if(!r) return;                                  /* dataset moved on */
      var kind=r.k||"unclassified";
      if(state.kinds.size && !state.kinds.has(kind)) return;
      if(state.onlyinf && !r.i) return;
      var row=GEO.refs[name], p=GEO.places[row[0]];
      if(!p) return;
      var e=bag[row[0]];
      if(!e) e=bag[row[0]]={i:row[0],name:p[0],lat:p[1],lon:p[2],
                            refs:[],sp:{},kinds:{},hits:0,conf:[0,0,0]};
      e.refs.push(name);
      (r.s||[]).forEach(function(id){ e.sp[id]=1 });
      e.kinds[kind]=(e.kinds[kind]||0)+1;
      e.conf[row[2]]++;
      if(state.q && atlasHit(name,r,state.q)) e.hits++;
    });
    APLACES=Object.keys(bag).map(function(k){
      var e=bag[k];
      e.n=Object.keys(e.sp).length;
      e.x=ax(e.lon); e.y=ay(e.lat);
      /* a place is "regional" when most of what sits there was placed by
         culture area rather than by a claim about the thing itself */
      e.soft=e.conf[2] > (e.conf[0]+e.conf[1]);
      return e;
    }).sort(function(a,b){ return b.n-a.n });
    ABYNAME={};
    APLACES.forEach(function(p){ ABYNAME[p.name]=p });
    return APLACES;
  }
  function atlasHit(name,r,q){
    if(name.indexOf(q)>=0) return true;
    if((r.d||"").toLowerCase().indexOf(q)>=0) return true;
    var s=r.s||[];
    for(var i=0;i<s.length;i++){
      var sp=D.species[String(s[i])];
      if(sp && sp[0].toLowerCase().indexOf(q)>=0) return true;
    }
    return false;
  }
  function atlasPlace(name){ atlasPlaces(); return (ABYNAME&&ABYNAME[name])||null }
  /* which place the panel is pointing at — a place itself, or the place the
     selected referent came from, so opening a referent lights up its pin */
  function atlasFocus(){
    var sel=state.sel;
    if(!sel) return null;
    if(sel.t==="place") return atlasPlace(sel.k);
    if(sel.t==="referent" && GEO && GEO.refs[sel.k]){
      var p=GEO.places[GEO.refs[sel.k][0]];
      return p?atlasPlace(p[0]):null;
    }
    return null;
  }
  function atlasRadius(n){ return Math.min(26,3.2+2.5*Math.sqrt(n)) }   /* px */

  var ANS="http://www.w3.org/2000/svg";
  function svgel(t,attrs,cls){
    var e=document.createElementNS(ANS,t);
    if(cls) e.setAttribute("class",cls);
    for(var k in attrs) e.setAttribute(k,attrs[k]);
    return e;
  }
  function atlasTip(html,cx,cy){
    var tip=$("#atlastip"); if(!tip) return;
    if(!html){ tip.hidden=true; return }
    tip.innerHTML=html; tip.hidden=false;
    var box=$("#atlas").getBoundingClientRect(), t=tip.getBoundingClientRect();
    var x=cx-box.left+14, y=cy-box.top+14;
    if(x+t.width>box.width-8) x=cx-box.left-t.width-14;
    if(y+t.height>box.height-8) y=cy-box.top-t.height-14;
    tip.style.left=Math.max(6,x)+"px"; tip.style.top=Math.max(6,y)+"px";
  }
  function atlasTopKinds(p){
    return Object.keys(p.kinds).sort(function(a,b){ return p.kinds[b]-p.kinds[a] })
      .slice(0,3).map(function(k){ return kindLabel(k)+" "+p.kinds[k] }).join(" · ");
  }
  function howPlaced(p){
    var bits=[];
    if(p.conf[0]) bits.push(p.conf[0]+" from its own entry");
    if(p.conf[1]) bits.push(p.conf[1]+" one hop out");
    if(p.conf[2]) bits.push(p.conf[2]+" by culture area");
    return bits.join(", ");
  }

  function drawAtlas(){
    if(!WORLD||!GEO||!D) return;
    var svg=$("#asvg"); if(!svg) return;
    APLACES=null;                 /* the rail, the search box and the flags all move it */
    var v=aview(), u=aunit();
    svg.setAttribute("viewBox",v.x+" "+v.y+" "+v.w+" "+v.h);
    while(svg.firstChild) svg.removeChild(svg.firstChild);

    /* graticule first, so the land sits on top of it */
    var grat=svgel("g",{},"agrat");
    for(var lon=-150;lon<=150;lon+=30)
      grat.appendChild(svgel("path",{d:"M"+ax(lon)+" 0V"+WORLD.h}));
    for(var lat=-60;lat<=60;lat+=30)
      grat.appendChild(svgel("path",{d:"M0 "+ay(lat)+"H"+WORLD.w}));
    svg.appendChild(grat);

    var land=svgel("g",{},"aland");
    WORLD.countries.forEach(function(c){
      var path=svgel("path",{d:c.d});
      var nm=svgel("title",{});
      nm.textContent=c.n;
      path.appendChild(nm);
      land.appendChild(path);
    });
    svg.appendChild(land);

    var places=atlasPlaces(), focus=atlasFocus();
    /* An opened place fans its referents out around the pin, and a pin near
       the edge would fan them off the map. Nudge the view the first time a
       place opens — never afterwards, or panning away would snap back. */
    if(focus && focus!==ALASTFOCUS){
      var need=(atlasRadius(focus.n)+26+2*23+14)*u;
      var nx=Math.min(Math.max(AVIEW.cx, focus.x-(v.w/2-need)), focus.x+(v.w/2-need));
      var ny=Math.min(Math.max(AVIEW.cy, focus.y-(v.h/2-need)), focus.y+(v.h/2-need));
      if(v.w>2*need && v.h>2*need && (nx!==AVIEW.cx || ny!==AVIEW.cy)){
        AVIEW.cx=nx; AVIEW.cy=ny; atlasClamp();
        v=aview(); svg.setAttribute("viewBox",v.x+" "+v.y+" "+v.w+" "+v.h);
      }
    }
    ALASTFOCUS=focus;
    var pins=svgel("g",{}), labels=svgel("g",{}), fan=svgel("g",{});
    var taken=[];                       /* label boxes already placed, in px */

    places.forEach(function(p){
      var rpx=atlasRadius(p.n), cls="apin";
      if(state.q && !p.hits) cls+=" soft";
      if(p.soft) cls+=" guessed";
      if(focus===p) cls+=" on";
      var fl=flagsOn("place",p.name);
      if(fl && fl.open) cls+=" flagged";
      var c=svgel("circle",{cx:p.x,cy:p.y,r:rpx*u,tabindex:"0",role:"button",
                            "aria-label":p.name+", "+p.n+" Pokémon"},cls);
      var tiptext="<b>"+p.name+"</b><span class='tipmeta'>"+p.refs.length+
        " referent"+(p.refs.length===1?"":"s")+" · "+p.n+" Pok\u00e9mon</span>"+
        "<span class='tipmeta'>"+atlasTopKinds(p)+"</span>"+
        "<span class='tipmeta'>"+howPlaced(p)+"</span>"+
        (p.soft?"<span class='tipmeta'>a culture area, not a single spot</span>":"");
      function show(e){ atlasTip(tiptext,e.clientX,e.clientY) }
      c.addEventListener("pointerenter",show);
      c.addEventListener("pointermove",show);
      c.addEventListener("pointerleave",function(){ atlasTip(null) });
      /* Picking is settled on pointerup, not by a click listener: the drag
         handler captures the pointer, and a captured pointer sends its click
         to the element that captured it, so a listener here would never run. */
      c.__pick=function(){ select({t:"place",k:p.name}) };
      c.__zoom=function(){ atlasZoomTo(p) };
      c.addEventListener("keydown",function(e){
        if(e.key==="Enter"||e.key===" "){ e.preventDefault(); select({t:"place",k:p.name}) }
      });
      pins.appendChild(c);

      if(!ALABELS) return;
      /* a name only where it fits: big pins first, and never over a name
         already drawn — overlapping monospace at this size is unreadable */
      if(rpx<7 && p.n<6) return;
      if(taken.length>=44) return;
      var s=atoscreen(p.x,p.y);
      var w=p.name.length*5.6+6, h=12;
      var box=[s.x+rpx+4, s.y-h/2, w, h];
      var clash=taken.some(function(t){
        return !(box[0]>t[0]+t[2]+3 || box[0]+box[2]+3<t[0] ||
                 box[1]>t[1]+t[3]+2 || box[1]+box[3]+2<t[1]);
      });
      if(clash) return;
      taken.push(box);
      var tx=p.x+(rpx+4)*u, ty=p.y+3.4*u;
      var lab=svgel("text",{x:tx,y:ty},"alabel"+(p.n>=12?" big":""));
      lab.setAttribute("font-size",(10*u)+"px");
      lab.setAttribute("stroke-width",(3*u)+"px");
      lab.textContent=p.name;
      labels.appendChild(lab);
    });

    /* the open place, opened out: its referents on a ring around the pin */
    if(focus){
      var list=focus.refs.slice().sort(function(a,b){
        var sa=(D.referents[a].s||[]).length, sb=(D.referents[b].s||[]).length;
        return sb-sa || (a<b?-1:1);
      });
      var shown=list.slice(0,48);
      fan.appendChild(svgel("circle",{cx:focus.x,cy:focus.y,
        r:(atlasRadius(focus.n)+7)*u},"aring"));
      shown.forEach(function(name,i){
        var ring=Math.floor(i/12), slot=i%12;
        var rad=(atlasRadius(focus.n)+26+ring*23)*u;
        var ang=slot/12*Math.PI*2 + ring*0.26 - Math.PI/2;
        var fx=focus.x+Math.cos(ang)*rad, fy=focus.y+Math.sin(ang)*rad;
        fan.appendChild(svgel("line",{x1:focus.x,y1:focus.y,x2:fx,y2:fy},"aspoke"));
        var on=state.sel && state.sel.t==="referent" && state.sel.k===name;
        var dot=svgel("circle",{cx:fx,cy:fy,r:4.6*u,tabindex:"0",role:"button",
                                "aria-label":disp(name)},"afan"+(on?" on":""));
        dot.addEventListener("pointerenter",function(e){
          var r=D.referents[name];
          atlasTip("<b>"+disp(name)+"</b><span class='tipmeta'>"+(r.k||"unclassified")+
                   " · "+(r.s||[]).length+" Pokémon</span><span class='tipmeta'>"+
                   GEO.vias[GEO.refs[name][1]]+"</span>",e.clientX,e.clientY);
        });
        dot.addEventListener("pointerleave",function(){ atlasTip(null) });
        dot.__pick=function(){ select({t:"referent",k:name}) };
        dot.addEventListener("keydown",function(e){
          if(e.key==="Enter"||e.key===" "){ e.preventDefault(); select({t:"referent",k:name}) }
        });
        fan.appendChild(dot);
      });
      if(list.length>shown.length){
        var more=svgel("text",{x:focus.x,y:focus.y-(atlasRadius(focus.n)+34)*u},"alabel big");
        more.setAttribute("font-size",(10*u)+"px");
        more.setAttribute("text-anchor","middle");
        more.textContent="+"+(list.length-shown.length)+" more in the panel";
        fan.appendChild(more);
      }
    }
    svg.appendChild(fan); svg.appendChild(pins); svg.appendChild(labels);
    var old=$("#atlas").querySelector(".atlasempty");
    if(old) old.remove();
    if(!places.length){
      var e2=el("p","atlasempty","Nothing on the map matches these filters \u2014 drop a category chip, or clear the search.");
      $("#atlas").appendChild(e2);
    }

    var sp={}, shownRefs=0;
    places.forEach(function(p){
      shownRefs+=p.refs.length;
      Object.keys(p.sp).forEach(function(i){ sp[i]=1 });
    });
    $("#atlasnote").textContent=places.length+" places · "+shownRefs+" referents · "+
      Object.keys(sp).length+" Pokémon"+
      (state.q?" · "+places.filter(function(p){return p.hits}).length+" with a match":"")+
      " · drag to pan, scroll to zoom";
    $("#resultnote").textContent=places.length+" places of origin · "+
      Object.keys(sp).length+" Pokémon placed";
    atlasWire();
  }

  function atlasZoomTo(p){
    AVIEW.cx=p.x; AVIEW.cy=p.y; AVIEW.w=Math.max(90,Math.min(AVIEW.w,420));
    atlasClamp(); drawAtlas();
  }
  function atlasClamp(){
    AVIEW.w=Math.max(70,Math.min(2600,AVIEW.w));
    var h=AVIEW.w*(arect().height/arect().width);
    /* keep at least a quarter of the canvas on screen, so the map cannot be
       flicked into empty space and lost */
    AVIEW.cx=Math.max(-AVIEW.w/4,Math.min(WORLD.w+AVIEW.w/4,AVIEW.cx));
    AVIEW.cy=Math.max(-h/4,Math.min(WORLD.h+h/4,AVIEW.cy));
  }
  function atlasZoom(factor,cx,cy){
    var before=(cx!=null)?atoworld(cx,cy):null;
    AVIEW.w=AVIEW.w*factor;
    atlasClamp();
    if(before){
      var after=atoworld(cx,cy);
      AVIEW.cx+=before.x-after.x; AVIEW.cy+=before.y-after.y;
      atlasClamp();
    }
    drawAtlas();
  }
  function atlasWire(){
    if(atlasWired) return;
    atlasWired=true;
    var svg=$("#asvg"), drag=null, moved=0, down=null;
    svg.addEventListener("wheel",function(e){
      e.preventDefault();
      atlasZoom(Math.pow(1.0016,e.deltaY), e.clientX, e.clientY);
    },{passive:false});
    svg.addEventListener("pointerdown",function(e){
      if(e.button) return;
      drag={x:e.clientX,y:e.clientY}; moved=0; down=e.target;
      svg.classList.add("dragging");
      try{ svg.setPointerCapture(e.pointerId) }catch(err){}
    });
    svg.addEventListener("pointermove",function(e){
      if(!drag) return;
      var u=aunit();
      AVIEW.cx-=(e.clientX-drag.x)*u; AVIEW.cy-=(e.clientY-drag.y)*u;
      moved+=Math.abs(e.clientX-drag.x)+Math.abs(e.clientY-drag.y);
      drag={x:e.clientX,y:e.clientY};
      atlasClamp();
      var v=aview();
      svg.setAttribute("viewBox",v.x+" "+v.y+" "+v.w+" "+v.h);
    });
    function endDrag(e,pick){
      if(!drag) return;
      drag=null; svg.classList.remove("dragging");
      var target=down; down=null;
      if(pick && moved<=6){
        /* a tap, not a pan: whatever was under the finger decides */
        if(target && target.__pick){ target.__pick(); atlasTip(null); return }
        if(state.sel){ state.sel=null; record(); renderDetail(); drawAtlas(); return }
      }
      /* a drag redraws once at the end: pin sizes and labels are computed in
         pixels, so they only need settling when the panning stops */
      drawAtlas();
    }
    svg.addEventListener("pointerup",function(e){ endDrag(e,true) });
    svg.addEventListener("pointercancel",function(e){ endDrag(e,false) });
    svg.addEventListener("dblclick",function(e){
      if(e.target && e.target.__zoom){ e.preventDefault(); e.target.__zoom() }
    });
    $("#atlasin").addEventListener("click",function(){ atlasZoom(1/1.6) });
    $("#atlasout").addEventListener("click",function(){ atlasZoom(1.6) });
    $("#atlasreset").addEventListener("click",function(){
      AVIEW={cx:AHOME.cx,cy:AHOME.cy,w:AHOME.w}; drawAtlas();
    });
    $("#atlaslabels").addEventListener("change",function(e){
      ALABELS=e.target.checked; drawAtlas();
    });
    addEventListener("resize",function(){ if(state.tab==="atlas" && WORLD) drawAtlas() });
  }

  /* ---------- flags ---------- */
  function targetKey(sel){ return sel.t+":"+sel.k }
  function flagForm(sel,label){
    var f=el("form","form hidden"); f.id="flagform";
    var l1=el("label","","What's wrong"); l1.htmlFor="fissue";
    var sel2=document.createElement("select"); sel2.id="fissue";
    [["wrong-kind","Wrong category"],["wrong-parent","Wrong cluster / parent"],
     ["not-a-referent","Not a real referent"],["missing","Something is missing"],
     ["wrong-species","Wrong Pokémon linked"],["other","Something else"]]
      .forEach(function(o){ var op=document.createElement("option"); op.value=o[0]; op.textContent=o[1]; sel2.appendChild(op) });
    /* structured correction: a category to move it to */
    var l4=el("label","","Should be"); l4.htmlFor="fkind";
    var kin=document.createElement("select"); kin.id="fkind";
    [["","— leave the category alone —"]].concat((D.meta.kinds||[]).map(function(k){return [k,k]}))
      .concat([["unclassified","unclassified"]])
      .forEach(function(o){ var op=document.createElement("option"); op.value=o[0]; op.textContent=o[1]; kin.appendChild(op) });
    /* structured correction: a cluster or family it belongs under */
    var l5=el("label","","Belongs under"); l5.htmlFor="fparent";
    var par=document.createElement("input"); par.type="text"; par.id="fparent";
    par.placeholder="the cluster or family it should sit in, exactly as spelled here";
    par.setAttribute("list","parentlist");
    var l2=el("label","","Anything else to correct (optional)"); l2.htmlFor="fsugg";
    var sugg=document.createElement("input"); sugg.type="text"; sugg.id="fsugg"; sugg.placeholder="free text — slower for me to apply than the fields above";
    var l3=el("label","","Note (optional)"); l3.htmlFor="fnote";
    var note=document.createElement("textarea"); note.id="fnote"; note.rows=2; note.placeholder="Anything else worth recording";
    var act=el("div","actions");
    var sub=el("button","submit","Save flag"); sub.type="submit";
    var cancel=el("button","ghost","Close"); cancel.type="button"; cancel.onclick=function(){f.classList.add("hidden")};
    var st=el("span","status"); st.id="fstatus";
    act.appendChild(sub); act.appendChild(cancel); act.appendChild(st);
    var kwrap=el("div","fsub"); kwrap.appendChild(l4); kwrap.appendChild(kin);
    var pwrap=el("div","fsub"); pwrap.appendChild(l5); pwrap.appendChild(par);
    function sync(){
      var v=sel2.value;
      kwrap.style.display = (v==="wrong-kind") ? "" : "none";
      pwrap.style.display = (v==="wrong-parent") ? "" : "none";
    }
    sel2.onchange=sync;
    [l1,sel2,kwrap,pwrap,l2,sugg,l3,note,act].forEach(function(n){f.appendChild(n)});
    sync();
    if(canWrite===false){ sub.disabled=true; st.textContent="Read-only access — flags can't be saved from this view."; }
    f.onsubmit=function(e){
      e.preventDefault();
      if(!dbNS){ st.textContent="Not connected to the store; sign in to save flags."; return; }
      sub.disabled=true; st.textContent="Saving…";
      var body={targetType:sel.t,target:String(sel.k),label:label,issue:sel2.value,
                suggestion:sugg.value.trim(),note:note.value.trim(),
                created:new Date().toISOString(),status:"open",
                build:(D.meta&&D.meta.build)||""};
      if(sel2.value==="wrong-kind" && kin.value) body.newKind=kin.value;
      if(sel2.value==="wrong-parent" && par.value.trim()) body.newParent=par.value.trim();
      if(viewerId) body.by=viewerId;
      dbNS.collection("corrections").add(body).then(function(){
        st.textContent="Saved."; sugg.value=""; note.value=""; kin.value=""; par.value="";
        setTimeout(function(){ st.textContent=""; f.classList.add("hidden"); sub.disabled=false },900);
      }).catch(function(err){
        sub.disabled=false;
        st.textContent = err && err.code==="invalid_argument" ? "This view can't write flags." : "Couldn't save — try again.";
      });
    };
    return f;
  }
  function existingFlags(key){
    var mine=flags.filter(function(f){return f.d.targetType+":"+f.d.target===key});
    var box=el("div");
    if(!mine.length) return box;
    box.appendChild(sectionTitle("Flagged here"));
    mine.forEach(function(f){ box.appendChild(flagCard(f,true)) });
    return box;
  }
  function flagCard(f,compact){
    var c=el("div","flagcard");
    var top=el("div","fm");
    top.textContent=(f.d.issue||"other")+" · "+(f.d.created||"").slice(0,10);
    var st=el("span","pill "+(f.d.status==="done"?"done":"open"),f.d.status==="done"?"applied":"open");
    st.style.marginLeft="6px"; top.appendChild(st);
    if(!compact) c.appendChild(el("div","ft",(f.d.targetType||"")+" · "+(f.d.label||f.d.target)));
    c.appendChild(top);
    if(f.d.newKind) c.appendChild(el("div","fn","→ category: "+f.d.newKind));
    if(f.d.newParent) c.appendChild(el("div","fn","→ under: "+f.d.newParent));
    if(f.d.suggestion) c.appendChild(el("div","fn",f.d.suggestion));
    if(f.d.note) c.appendChild(el("div","fn",f.d.note));
    if(f.d.resolution){ var r=el("div","fn"); r.style.cssText="border-left:2px solid var(--accent);padding-left:8px;color:var(--ink)"; r.textContent="Fixed: "+f.d.resolution; c.appendChild(r) }
    if(canWrite!==false){
      var act=el("div","actions");
      var tog=el("button","ghost",f.d.status==="done"?"Reopen":"Mark applied");
      tog.onclick=function(){
        tog.disabled=true;
        dbNS.collection("corrections").doc(f.id).update({status:f.d.status==="done"?"open":"done"})
          .catch(function(){tog.disabled=false});
      };
      var del=el("button","ghost","Delete");
      del.onclick=function(){ del.disabled=true; dbNS.collection("corrections").doc(f.id).delete().catch(function(){del.disabled=false}) };
      act.appendChild(tog); act.appendChild(del); c.appendChild(act);
    }
    return c;
  }
  function renderFlags(host){
    $("#resulttitle").textContent="Flags";
    $("#resultnote").textContent=flags.length?flags.length+" recorded":"";
    if(!flagsReady && !flags.length){
      host.appendChild(el("p","empty",flagsNote||"Checking for saved flags…"));
      return;
    }
    if(!flags.length){
      var e=el("p","empty","No flags yet. Open any cluster, referent or Pokémon and press Flag to record what looks wrong — the notes are saved with the artifact, and I can read them back and fix the source data.");
      host.appendChild(e); return;
    }
    var openF=flags.filter(function(f){return f.d.status!=="done"});
    var doneF=flags.filter(function(f){return f.d.status==="done"});
    var bar=el("div","actions"); bar.style.marginBottom="12px";
    [["open","Open ("+openF.length+")"],["done","Applied ("+doneF.length+")"],["all","All ("+flags.length+")"]]
      .forEach(function(o){
        var b=el("button","chip",o[1]);
        b.setAttribute("aria-pressed",state.flagview===o[0]?"true":"false");
        b.onclick=function(){ state.flagview=o[0]; render() };
        bar.appendChild(b);
      });
    if(doneF.length && canWrite!==false){
      var clr=el("button","ghost","Clear applied");
      clr.onclick=function(){
        clr.disabled=true; clr.textContent="Clearing…";
        Promise.all(doneF.map(function(f){ return dbNS.collection("corrections").doc(f.id).delete().catch(function(){}) }))
          .then(function(){ clr.textContent="Clear applied"; clr.disabled=false });
      };
      bar.appendChild(clr);
    }
    host.appendChild(bar);
    var shown = state.flagview==="open"?openF:(state.flagview==="done"?doneF:flags);
    if(!shown.length){
      host.appendChild(el("p","empty",state.flagview==="open"?"No open flags — everything recorded has been applied.":"Nothing here."));
      return;
    }
    var grid=el("div","flaggrid");
    shown.forEach(function(f){ grid.appendChild(flagCard(f,false)) });
    host.appendChild(grid);
  }

  /* ---------- clear ----------
     One button for all three columns: the rail's filters, the place the map
     and the list are in, and whatever the panel is showing. It greys out when
     there is nothing left to clear, so it never promises an empty action. */
  function anythingSet(){
    return !!(state.q || state.path.length || state.sel || state.poke || state.onlymulti || state.onlyinf ||
              attrsActive() || gstate.showAll || !state.scope);
  }
  function syncClears(){
    var b=$("#tab-clear"); if(b) b.disabled=!anythingSet();
  }
  $("#tab-clear").addEventListener("click",function(){
    if(!anythingSet()) return;
    state.types.clear(); state.gens.clear(); state.colours.clear(); state.misc.clear();
    state.onlymulti=false; $("#onlymulti").checked=false;
    state.onlyinf=false; $("#onlyinf").checked=false; INFCACHE=null;
    state.q=""; $("#q").value="";
    state.scope=true; gstate.showAll=false; state.sel=null; state.poke=null; state.limit=120;
    buildPokeFilters();
    goTo([]);                       /* re-renders, clears the panel, re-marks the chips */
  });

  /* ---------- theme ----------
     Three states, because "follow the system" is the right default and a
     two-way switch cannot get back to it. The choice is a per-viewer
     convenience, so localStorage is the right home — and it may throw. */
  var THEMES=[{k:"",g:"◐",l:"system"},{k:"light",g:"☀",l:"light"},{k:"dark",g:"☾",l:"dark"}];
  function applyTheme(k){
    var root=document.documentElement;
    if(k) root.setAttribute("data-theme",k); else root.removeAttribute("data-theme");
    var t=THEMES.filter(function(x){return x.k===k})[0]||THEMES[0];
    $("#themeglyph").textContent=t.g;
    $("#themelabel").textContent=t.l;
    $("#theme").title = k ? "Theme: "+t.l+" — click to cycle" : "Theme: follows your system — click to cycle";
    try{ if(k) localStorage.setItem("theme",k); else localStorage.removeItem("theme") }catch(e){}
  }
  (function(){
    var saved=""; try{ saved=localStorage.getItem("theme")||"" }catch(e){}
    if(saved!=="light" && saved!=="dark") saved="";
    applyTheme(saved);
  })();
  $("#theme").addEventListener("click",function(){
    var now=document.documentElement.getAttribute("data-theme")||"";
    var i=0; THEMES.forEach(function(t,n){ if(t.k===now) i=n });
    applyTheme(THEMES[(i+1)%THEMES.length].k);
    /* the map paints strokes and haloes from the theme's own variables */
    if(state.tab==="map" && D3 && D) drawGraph();
    if(state.tab==="atlas" && WORLD) drawAtlas();
  });

  /* ---------- search suggestions ----------
     The box already narrows the lists as you type. This is the other half:
     somewhere to jump straight to, with a Pokémon's own face beside its name
     so a dex search reads at a glance. */
  var SUGG=null, sgItems=[], sgAt=-1;
  function buildSuggest(){
    if(SUGG) return SUGG;
    SUGG=[];
    Object.keys(D.species).forEach(function(id){
      SUGG.push({t:"species",k:+id,label:D.species[id][0],n:D.species[id][1].length,kind:(D.species[id][2]||[])[0]});
    });
    Object.keys(D.referents).forEach(function(r){
      SUGG.push({t:"referent",k:r,label:disp(r),n:D.referents[r].s.length,kind:D.referents[r].k});
    });
    Object.keys(D.groups).forEach(function(g){
      var gg=D.groups[g];
      if((gg.m||[]).length===1 && !(gg.ch||[]).length) return;   /* same name as its one referent */
      SUGG.push({t:"group",k:g,label:disp(g),n:gg.tn||gg.n,kind:gg.k});
    });
    Object.keys(D.families).forEach(function(f){
      SUGG.push({t:"family",k:f,label:f,n:D.families[f].n,kind:D.families[f].k});
    });
    (D.meta.kinds||[]).forEach(function(k){
      SUGG.push({t:"kind",k:k,label:kindLabel(k),kind:k,n:0});
    });
    return SUGG;
  }
  var SGNOUN={species:"Pokémon",referent:"referent",group:"cluster",family:"family",kind:"category"};
  function suggestFor(q){
    var all=buildSuggest(), out=[];
    for(var i=0;i<all.length;i++){
      var it=all[i], low=it.label.toLowerCase(), at=low.indexOf(q);
      if(at<0) continue;
      /* a name that starts with what you typed beats one that merely contains it,
         and a whole-word hit beats a hit inside a word */
      var rank = at===0 ? 0 : (low.charAt(at-1)===" " ? 1 : 2);
      if(it.t==="species") rank-=0.5;              /* a dex search usually means the Pokémon */
      out.push({it:it,rank:rank,at:at});
    }
    out.sort(function(a,b){
      if(a.rank!==b.rank) return a.rank-b.rank;
      /* Pokémon fall in dex order among themselves — Charmander before
         Charjabug — while everything else leads with the biggest */
      if(a.it.t==="species" && b.it.t==="species") return a.it.k-b.it.k;
      return (b.it.n||0)-(a.it.n||0) || a.it.label.length-b.it.label.length;
    });
    return out.slice(0,9).map(function(x){return x.it});
  }
  function closeSuggest(){
    sgItems=[]; sgAt=-1;
    var box=$("#suggest"); box.hidden=true; box.innerHTML="";
    $("#q").setAttribute("aria-expanded","false");
  }
  function markSuggest(){
    var opts=$("#suggest").querySelectorAll(".sg");
    [].forEach.call(opts,function(o,i){ o.classList.toggle("on", i===sgAt) });
    if(sgAt>=0 && opts[sgAt] && opts[sgAt].scrollIntoView) opts[sgAt].scrollIntoView({block:"nearest"});
  }
  function pickSuggest(it){
    closeSuggest();
    state.q=""; $("#q").value="";
    if(it.t==="species"){ select({t:"species",k:it.k}); return }
    if(it.t==="referent"||it.t==="group"){ select({t:it.t,k:it.k}); return }
    if(it.t==="family"){ goTo(famSteps(it.k)||[],{top:true}); return }
    if(it.t==="kind"){ goTo([{t:"kind",k:it.k}],{top:true}) }
  }
  function renderSuggest(q){
    var box=$("#suggest");
    if(!D || q.length<2){ closeSuggest(); return }
    sgItems=suggestFor(q); sgAt=-1;
    if(!sgItems.length){ closeSuggest(); return }
    box.innerHTML="";
    var hint=el("div","sghint","enter to jump · ↑↓ to choose");
    box.appendChild(hint);
    sgItems.forEach(function(it,i){
      var b=el("button","sg"); b.type="button"; b.setAttribute("role","option");
      var im=it.t==="species"?sprite(it.k,"sgspr"):null;
      if(im){ im.className="spr sgspr"; b.appendChild(im) }
      else {
        var d=el("span","sgdot");
        d.style.background="hsl("+kindHue(it.kind)+" 55% 55%)";
        b.appendChild(d);
      }
      var nm=el("span","sgname");
      var at=it.label.toLowerCase().indexOf(q);
      nm.appendChild(document.createTextNode(it.label.slice(0,at)));
      nm.appendChild(el("b","",it.label.slice(at,at+q.length)));
      nm.appendChild(document.createTextNode(it.label.slice(at+q.length)));
      b.appendChild(nm);
      b.appendChild(el("span","sgkind",SGNOUN[it.t]));
      if(it.n) b.appendChild(el("span","sgn",it.t==="species"?it.n+" refs":it.n+" Pokémon"));
      b.onmouseenter=function(){ sgAt=i; markSuggest() };
      b.onclick=function(){ pickSuggest(it) };
      box.appendChild(b);
    });
    box.hidden=false;
    $("#q").setAttribute("aria-expanded","true");
  }
  $("#q").addEventListener("keydown",function(e){
    if(!sgItems.length){
      if(e.key==="Escape"){ state.q=""; e.target.value=""; render() }
      return;
    }
    if(e.key==="ArrowDown"||e.key==="ArrowUp"){
      e.preventDefault();
      var step=e.key==="ArrowDown"?1:-1;
      sgAt=(sgAt+step+sgItems.length)%sgItems.length;
      markSuggest();
    } else if(e.key==="Enter"){
      e.preventDefault(); pickSuggest(sgItems[sgAt<0?0:sgAt]);
    } else if(e.key==="Escape"){
      e.preventDefault(); closeSuggest();
    }
  });
  addEventListener("click",function(e){
    if(!e.target.closest || !e.target.closest(".searchbox")) closeSuggest();
  });

  /* ---------- controls ---------- */
  $("#q").addEventListener("input",function(e){
    state.q=e.target.value.trim().toLowerCase(); state.limit=120;
    renderSuggest(state.q); render();
  });
  $("#sort").addEventListener("change",function(e){ state.sort=e.target.value; render() });
  $("#onlymulti").addEventListener("change",function(e){ state.onlymulti=e.target.checked; state.limit=120; render() });
  $("#onlyinf").addEventListener("change",function(e){
    state.onlyinf=e.target.checked; INFCACHE=null; state.limit=120; render();
  });
  ["clusters","map","atlas","species","flags"].forEach(function(t){
    $("#tab-"+t).addEventListener("click",function(){
      state.tab=t; state.limit=120; record();
      ["clusters","map","atlas","species","flags"].forEach(function(o){ $("#tab-"+o).setAttribute("aria-selected",o===t?"true":"false") });
      render();
    });
  });

  /* ---------- capabilities ---------- */
  if(window.claude && window.claude.use){
    window.claude.use("user").then(function(u){
      userNS=u; if(!u) return;
      try{ canWrite = u.can ? u.can("data.write") : null }catch(e){}
      if(canWrite && typeof canWrite.then==="function") canWrite.then(function(v){canWrite=v});
      if(u.id) u.id().then(function(i){viewerId=i}).catch(function(){});
    }).catch(function(){});

    window.claude.use("db").then(function(db){
      dbNS=db;
      if(!db){ flagsNote="Sign in to record flags on this page."; flagsReady=true; if(state.tab==="flags") render(); return; }
      var timer=setTimeout(function(){
        if(!flagsReady){ flagsNote="Saved flags are taking a while to load; they may be out of date."; if(state.tab==="flags") render() }
      },10000);
      db.collection("corrections").orderBy("created","desc").limit(300).onSnapshot(function(snap){
        if(!snap.metadata.fromCache){ clearTimeout(timer); flagsReady=true; flagsNote="" }
        flags=snap.docs.map(function(doc){ return {id:doc.id,d:doc.data()||{}} });
        buildFlagIndex();
        var openN=flags.filter(function(f){return f.d.status!=="done"}).length;
        $("#flagcount").textContent=openN?"("+openN+")":"";
        if(state.tab==="flags") render();
        else if(state.tab==="map" && D3 && D) drawGraph();
        else if(state.tab==="atlas" && WORLD) drawAtlas();
        if(state.sel) renderDetail();
      },function(){
        clearTimeout(timer); flagsReady=true;
        flagsNote="Flags can't be loaded in this view.";
        if(state.tab==="flags") render();
      });
    }).catch(function(){});
  } else {
    flagsNote="Flagging needs the published page — it is off in this preview.";
  }
})();
