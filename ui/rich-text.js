'use strict';
// Local, bounded Markdown and MathML subset. Raw HTML, links and remote resources
// are text. Unknown TeX is preserved verbatim; it is never interpreted as HTML.
function richEscape(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function localMath(source){
  if(source.length>6000)return `<code>${richEscape(source)}</code>`;
  let i=0,depth=0;
  const symbols={cdot:'·',times:'×',div:'÷',le:'≤',leq:'≤',ge:'≥',geq:'≥',ne:'≠',neq:'≠',pi:'π',alpha:'α',beta:'β',gamma:'γ',rho:'ρ',Delta:'Δ',theta:'θ',infty:'∞',pm:'±',degree:'°',Rightarrow:'⇒',rightarrow:'→'};
  function atom(){
    if(++depth>30)throw Error('depth');
    let out='';
    if(source[i]==='{'){i++;out='<mrow>'+sequence('}')+'</mrow>';if(source[i++]!=='}')throw Error('brace');}
    else if(source[i]==='\\'){
      i++;const m=/^[a-zA-Z]+/.exec(source.slice(i));if(!m)throw Error('command');i+=m[0].length;
      while(source[i]===' ')i++;
      if(m[0]==='frac')out='<mfrac>'+atom()+atom()+'</mfrac>';
      else if(m[0]==='sqrt')out='<msqrt>'+atom()+'</msqrt>';
      else if(symbols[m[0]])out='<mo>'+symbols[m[0]]+'</mo>';
      else if(['text','mathrm','operatorname'].includes(m[0]))out=atom();
      else throw Error('unsupported');
    }else {const c=source[i++];if(!c||c==='}')throw Error('atom');out=`<${/[0-9.,]/.test(c)?'mn':/[a-zA-Zа-яА-Я]/.test(c)?'mi':'mo'}>${richEscape(c)}</${/[0-9.,]/.test(c)?'mn':/[a-zA-Zа-яА-Я]/.test(c)?'mi':'mo'}>`;}
    --depth;return out;
  }
  function sequence(end){let out='';while(i<source.length&&source[i]!==end){if(/\s/.test(source[i])){i++;continue;}let a=atom();while(source[i]==='^'||source[i]==='_'){const op=source[i++];a=`<${op==='^'?'msup':'msub'}>${a}${atom()}</${op==='^'?'msup':'msub'}>`;}out+=a;}return out;}
  try{return `<math xmlns="http://www.w3.org/1998/Math/MathML" aria-label="${richEscape(source)}"><mrow>${sequence(null)}</mrow></math>`;}catch{return `<code class="formula-fallback">${richEscape(source)}</code>`;}
}
function renderRich(value){
  const source=String(value??'');if(source.length>100000)return `<pre>${richEscape(source)}</pre>`;
  const tokens=[];const keep=html=>{tokens.push(html);return `\u0000${tokens.length-1}\u0000`;};
  let prepared=source.replace(/\u0000/g,'�').replace(/```[^\n]*\n([\s\S]*?)```/g,(_,s)=>keep(`<pre><code>${richEscape(s)}</code></pre>`));
  prepared=prepared.replace(/\$\$([\s\S]*?)\$\$|\\\[([\s\S]*?)\\\]|\\\(([\s\S]*?)\\\)|\$([^$\n]+)\$/g,(_,a,b,c,d)=>keep(localMath(a??b??c??d)));
  let html=richEscape(prepared).replace(/^### (.+)$/gm,'<h4>$1</h4>').replace(/^## (.+)$/gm,'<h3>$1</h3>').replace(/^# (.+)$/gm,'<h2>$1</h2>')
    .replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>').replace(/`([^`\n]+)`/g,'<code>$1</code>')
    .replace(/^[-*] (.+)$/gm,'<div class="rich-list">• $1</div>').replace(/\n/g,'<br>');
  return html.replace(/\u0000(\d+)\u0000/g,(_,i)=>tokens[Number(i)]||'');
}
