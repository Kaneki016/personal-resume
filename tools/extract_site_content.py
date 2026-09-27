"""One-time extraction of the existing public page into editable content defaults."""
import json
from pathlib import Path
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
soup=BeautifulSoup((ROOT/'dist/index.html').read_text(encoding='utf-8'),'html.parser')
def text(node): return node.get_text(' ',strip=True) if node else ''
def lines(nodes): return '\n'.join(text(n) for n in nodes)
def image_path(path): return '/'+path.lstrip('/') if path else ''
hero=soup.select_one('.portfolio-hero'); about=soup.select_one('.about-panel')
defaults={
 'profile':{'name':'Lai Yoke Yau','initials':'LY','intro_label':text(hero.select_one('.intro-label')),'headline':'I build for\nthe real world.','introduction':text(hero.select_one('p')),'role':text(hero.select_one('figcaption strong')),'location':text(hero.select_one('figcaption span')),'portrait':'/assets/images/profile.jpg','portrait_alt':'Lai Yoke Yau','seo_title':soup.title.string,'seo_description':soup.select_one('meta[name=description]')['content']},
 'page':{'nav_work':'Work','nav_about':'About','nav_connect':'Let’s connect ↗','primary_cta':'Explore my work ↓','secondary_cta':'Get in touch','projects_label':'01 / SELECTED WORK','projects_title':'Ideas, made tangible.','projects_intro':'Client work and personal experiments.\nA selection of what I’ve been building.','about_label':'02 / A LITTLE CONTEXT','background_label':'03 / BACKGROUND','experience_title':'Experience','education_title':'Education','awards_title':'Hackathon awards','skills_title':'Tools I work with.','certifications_title':'Certifications & learning','photos_title':'Training & hackathon photos',**{k:True for k in ['show_about','show_experience','show_education','show_awards','show_skills','show_certifications','show_photos']}},
 'highlights':[], 'about':{'title':'Curious about how things work.\nMotivated to make them better.','body':lines(about.select('p'))},'facts':[],
 'contact':{'title':'Let’s connect.','description':'Thanks for exploring my work. You can find me here.','email':'laiyokeyau@gmail.com','whatsapp':'+60 18-382 2330','linkedin':'https://www.linkedin.com/in/yoke-yau-lai','linkedin_label':'Lai Yoke Yau'},
 'experience':[],'education':[],'awards':[],'skills':[],'certifications':[],'photos':[]}
for node in soup.select('.hero-foot>span'):
 strong=node.select_one('strong'); label=text(strong); strong.extract(); defaults['highlights'].append({'title':label,'description':text(node),'visible':True})
for node in about.select('.mini-facts>div'): defaults['facts'].append({'title':text(node.select_one('strong')),'description':text(node.select_one('span')),'visible':True})
for node in soup.select('.tl-item'):
 role=node.select_one('.tl-role'); company=role.select_one('.company'); company_name=text(company).lstrip('· '); company.extract()
 defaults['experience'].append({'title':text(role),'company':company_name,'period':text(node.select_one('.tl-date')),'location':text(node.select_one('.tl-loc')),'details':lines(node.select('li')),'visible':True})
for node in soup.select('.edu-card'): defaults['education'].append({'title':text(node.select_one('h3')),'school':text(node.select_one('.school')),'period':text(node.select_one('.date')),'details':lines(node.select('li,.plain')),'visible':True})
for node in soup.select('.award-item'): defaults['awards'].append({'title':text(node.select_one('.award-badge')),'description':text(node.select('span')[1]),'visible':True})
for node in soup.select('.skill-card'): defaults['skills'].append({'title':text(node.select_one('h3')),'items':lines(node.select('.tag')),'visible':True})
for node in soup.select('.cert-item'):
 issuer=node.select_one('.cert-issuer'); issuer_text=text(issuer); issuer.extract(); link=node.select_one('a')
 defaults['certifications'].append({'title':text(node),'issuer':issuer_text,'link':image_path(link['href']) if link else '', 'visible':True})
for heading in soup.select('.gallery-subtitle'):
 for image in heading.find_next_sibling('div').select('img'):defaults['photos'].append({'title':image['alt'],'group':text(heading),'image':image_path(image['src']),'visible':True})

def field(key,label,kind='text',required=False,maxlength=500):return {'key':key,'label':label,'type':kind,'required':required,'max':maxlength}
def section(label,fields,collection=False):return {'label':label,'collection':collection,'max_items':80,'fields':fields+([field('visible','Show publicly','checkbox')] if collection else [])}
f=field
schema={
 'profile':section('Profile & introduction',[f('name','Your name',required=True,maxlength=140),f('initials','Logo initials',required=True,maxlength=5),f('intro_label','Introductory label'),f('headline','Main headline (line breaks supported)','textarea',True),f('introduction','Introduction','textarea',True,3000),f('role','Role / job title'),f('location','Location'),f('portrait','Profile photo','image'),f('portrait_alt','Photo description'),f('seo_title','Search engine page title',required=True,maxlength=160),f('seo_description','Search engine description','textarea',True,320)]),
 'page':section('Page headings & visibility',[f(k,k.replace('_',' ').capitalize(),'checkbox' if isinstance(v,bool) else 'textarea' if k=='projects_intro' else 'text',not isinstance(v,bool),800) for k,v in defaults['page'].items()]),
 'highlights':section('Areas of work',[f('title','Heading',required=True),f('description','Description')],True),
 'about':section('About me',[f('title','Section headline','textarea',True),f('body','About text (one paragraph per line)','textarea',True,6000)]),
 'facts':section('About highlights',[f('title','Highlight',required=True),f('description','Supporting label')],True),
 'contact':section('Contact details',[f('title','Section heading',required=True),f('description','Contact introduction','textarea'),f('email','Public email','email'),f('whatsapp','WhatsApp number (with country code)','phone'),f('linkedin','LinkedIn URL','url'),f('linkedin_label','LinkedIn display name')]),
 'experience':section('Experience',[f('title','Job title',required=True),f('company','Company',required=True),f('period','Dates / period'),f('location','Location'),f('details','Responsibilities (one bullet per line)','textarea',False,6000)],True),
 'education':section('Education',[f('title','Qualification / school',required=True),f('school','Institution'),f('period','Dates / status'),f('details','Achievements (one bullet per line)','textarea',False,6000)],True),
 'awards':section('Awards',[f('title','Award',required=True),f('description','Event / year',required=True)],True),
 'skills':section('Skills',[f('title','Skill group',required=True),f('items','Skills (one per line)','textarea',True,3000)],True),
 'certifications':section('Certifications',[f('title','Certificate / qualification',required=True),f('issuer','Issuer'),f('link','Certificate image or verification URL','asset')],True),
 'photos':section('Photo galleries',[f('title','Photo description',required=True),f('group','Gallery name (e.g. Training & work)',required=True),f('image','Photo','image',True)],True)}
for name,value in [('site-defaults.json',defaults),('site-fields.json',schema)]:
 (ROOT/'backend'/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Extracted all existing public content into',len(defaults),'editable sections.')

if __name__=='__main__': pass
