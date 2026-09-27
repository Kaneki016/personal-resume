"""Validated public content with revision checks and escaped server rendering."""
import copy
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE=Path(__file__).resolve().parent
DEFAULTS=json.loads((HERE/'site-defaults.json').read_text(encoding='utf-8'))
SCHEMA=json.loads((HERE/'site-fields.json').read_text(encoding='utf-8'))
TEMPLATES=Environment(loader=FileSystemLoader(HERE/'templates'),autoescape=select_autoescape(['html']))
TEMPLATES.filters['lines']=lambda value:[line.strip() for line in value.splitlines() if line.strip()]

def image_path(value):
    return bool(re.fullmatch(r'(?:/media/[a-f0-9]{32}\.(?:jpg|png|webp)|/assets/images/[a-zA-Z0-9_./-]+)',value)) and '..' not in value

def clean(section,value):
    if section not in SCHEMA:raise ValueError('Unknown website section.')
    spec=SCHEMA[section]
    if spec['collection']:
        if not isinstance(value,list) or len(value)>spec['max_items']:raise ValueError('Use at most 80 entries in a section.')
        items=value
    else:items=[value]
    cleaned=[]
    for item in items:
        if not isinstance(item,dict):raise ValueError('Check the content fields.')
        row={}
        for field in spec['fields']:
            key,kind=field['key'],field['type']; v=item.get(key,True if kind=='checkbox' else '')
            if kind=='checkbox':
                if not isinstance(v,bool):raise ValueError('Check '+field['label']+'.')
            else:
                if not isinstance(v,str):raise ValueError(field['label']+' must be text.')
                v=v.strip()
                if len(v)>field['max'] or (field['required'] and not v):raise ValueError('Check '+field['label']+'.')
                if any(ord(c)<32 and c not in '\n\r\t' for c in v):raise ValueError('Invalid characters in '+field['label']+'.')
                if v and kind in ('url','asset'):
                    parsed=urlsplit(v)
                    if not (kind=='asset' and image_path(v)) and not (parsed.scheme in ('http','https') and parsed.netloc and not parsed.username and not parsed.password):raise ValueError('Use a full http or https URL for '+field['label']+'.')
                if v and kind=='image' and not image_path(v):raise ValueError('Upload an image or choose an existing site image.')
                if v and kind=='email' and not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',v):raise ValueError('Enter a valid public email.')
                if v and kind=='phone' and (not re.fullmatch(r'\+?[\d ()-]+',v) or not 8<=len(re.sub(r'\D','',v))<=15):raise ValueError('Include the country code in your WhatsApp number.')
            row[key]=v
        cleaned.append(row)
    return cleaned if spec['collection'] else cleaned[0]

def read(c):
    sections=copy.deepcopy(DEFAULTS); revisions={key:0 for key in SCHEMA}
    for row in c.execute('SELECT id,body,revision FROM site_content'):
        if row['id'] in SCHEMA:
            sections[row['id']]=json.loads(row['body']);revisions[row['id']]=row['revision']
    return {'sections':sections,'revisions':revisions,'schema':SCHEMA}

def public_sections(sections):
    result=copy.deepcopy(sections)
    for key,spec in SCHEMA.items():
        if spec['collection']:result[key]=[item for item in result[key] if item.get('visible',True)]
    return result

def public_image(c,path):
    data=public_sections(read(c)['sections']); page=data['page']
    if data['profile']['portrait']==path:return True
    for section,field in [('certifications','link'),('photos','image')]:
        if page['show_'+section] and any(item[field]==path for item in data[section]):return True
    return False

def render(c):
    data=public_sections(read(c)['sections'])
    albums={}
    for photo in data['photos']:albums.setdefault(photo['group'],[]).append(photo)
    return TEMPLATES.get_template('portfolio.html').render(**data,albums=albums,year=date.today().year,whatsapp_number=re.sub(r'\D','',data['contact']['whatsapp']))
