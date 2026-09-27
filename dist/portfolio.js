const target=document.querySelector('#project-list');
const node=(tag,cls,value)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(value)el.textContent=value;return el;};
async function projects(){
 try{
  const response=await fetch('/api/public/projects');if(!response.ok)throw new Error();const items=await response.json();
  target.replaceChildren();
  if(!items.length){target.append(node('p','empty-state','New projects will be shared here soon.'));return;}
  for(const [index,p] of items.entries()){
   const card=node('article','project-item'),visual=node('div','project-visual');
   if(p.image){const img=node('img');img.src=p.image;img.alt=p.title+' screenshot';img.loading='lazy';img.addEventListener('error',()=>{visual.replaceChildren(node('strong','',p.title));visual.classList.add('project-type-cover');});visual.append(img);}
   else {visual.classList.add('project-type-cover');visual.append(node('span','',String(index+1).padStart(2,'0')+' / '+p.category),node('strong','',p.title));}
   card.append(visual,node('span','eyebrow',p.category),node('h3','',p.title),node('p','',p.summary));
   const tags=node('div','tags');p.tags.split(',').filter(x=>x.trim()).forEach(x=>tags.append(node('span','tag',x.trim())));card.append(tags);
   if(p.details){const detail=node('details','project-details');detail.append(node('summary','','About this project'),node('p','',p.details));card.append(detail);}
   if(p.url){const a=node('a','','Visit project ↗');a.href=p.url;a.target='_blank';a.rel='noopener noreferrer';card.append(a);}
   target.append(card);
  }
 }catch{target.replaceChildren(node('p','empty-state','Projects could not be loaded. Please refresh the page or contact me to see recent work.'));}
}
projects();
