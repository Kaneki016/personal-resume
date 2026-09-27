const target=document.querySelector('#project-list');
const node=(tag,cls,value)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(value)el.textContent=value;return el;};
const gallery=node('dialog','project-gallery');
gallery.setAttribute('aria-labelledby','gallery-title');
gallery.innerHTML='<div class="gallery-header"><div><h2 id="gallery-title"></h2><p id="gallery-count" aria-live="polite"></p></div><button type="button" class="gallery-close" aria-label="Close screenshots">Close ×</button></div><div class="gallery-stage"><img id="gallery-image" alt=""></div><div class="gallery-controls"><button type="button" id="gallery-prev">← Previous</button><a id="gallery-original" target="_blank" rel="noopener noreferrer">Open full image ↗</a><button type="button" id="gallery-next">Next →</button></div><div class="gallery-thumbnails" aria-label="Choose a screenshot"></div>';
document.body.append(gallery);
let galleryProject=null,galleryImages=[],galleryIndex=0;
function showScreenshot(index){
 galleryIndex=index;
 const img=gallery.querySelector('#gallery-image');img.src=galleryImages[index];img.alt=galleryProject.title+' — screenshot '+(index+1);
 gallery.querySelector('#gallery-count').textContent='Screenshot '+(index+1)+' of '+galleryImages.length;
 gallery.querySelector('#gallery-original').href=galleryImages[index];
 gallery.querySelector('#gallery-prev').disabled=index===0;gallery.querySelector('#gallery-next').disabled=index===galleryImages.length-1;
 gallery.querySelectorAll('.gallery-thumbnails button').forEach((button,i)=>button.setAttribute('aria-pressed',String(i===index)));
}
function openGallery(project,images){
 galleryProject=project;galleryImages=images;gallery.querySelector('#gallery-title').textContent=project.title;
 const thumbnails=gallery.querySelector('.gallery-thumbnails');thumbnails.replaceChildren();
 images.forEach((src,index)=>{const button=node('button');button.type='button';button.setAttribute('aria-label','Show screenshot '+(index+1));const img=node('img');img.src=src;img.alt='';img.loading='lazy';button.append(img);button.addEventListener('click',()=>showScreenshot(index));thumbnails.append(button);});
 showScreenshot(0);gallery.showModal();
}
gallery.querySelector('.gallery-close').addEventListener('click',()=>gallery.close());
gallery.querySelector('#gallery-prev').addEventListener('click',()=>showScreenshot(galleryIndex-1));
gallery.querySelector('#gallery-next').addEventListener('click',()=>showScreenshot(galleryIndex+1));
gallery.addEventListener('keydown',event=>{if(event.key==='ArrowLeft'&&galleryIndex>0){event.preventDefault();showScreenshot(galleryIndex-1);}if(event.key==='ArrowRight'&&galleryIndex<galleryImages.length-1){event.preventDefault();showScreenshot(galleryIndex+1);}});
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
   const images=p.screenshots?.length?p.screenshots:(p.image?[p.image]:[]);
   if(images.length){const button=node('button','screenshots-button','View screenshots ('+images.length+')');button.type='button';button.setAttribute('aria-label','View '+p.title+' screenshots ('+images.length+')');button.addEventListener('click',()=>openGallery(p,images));card.append(button);}
   if(p.details){const detail=node('details','project-details');detail.append(node('summary','','About this project'),node('p','',p.details));card.append(detail);}
   if(p.url){const a=node('a','','Visit project ↗');a.href=p.url;a.target='_blank';a.rel='noopener noreferrer';card.append(a);}
   target.append(card);
  }
 }catch{target.replaceChildren(node('p','empty-state','Projects could not be loaded. Please refresh the page or contact me to see recent work.'));}
}
projects();
