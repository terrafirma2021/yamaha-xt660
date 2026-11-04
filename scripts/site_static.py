"""Render the reading/navigation experience at build time, before any scripts run."""
import copy
import json
import posixpath
import re
from html import escape as esc
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from bs4.dammit import EntitySubstitution
from bs4.formatter import HTMLFormatter
from site_routes import SECTIONS
from site_xdf import selected_definition


class OrderedFormatter(HTMLFormatter):
    def attributes(self, tag):
        return tag.attrs.items()


FORMAT = OrderedFormatter(entity_substitution=EntitySubstitution.substitute_xml)


def fragment(markup):
    return BeautifulSoup(markup, 'html.parser')


def put(node, markup):
    node.clear()
    node.extend(list(fragment(markup).contents))


def connector_svg(connector, flashing=False):
    slots = connector['slots']
    columns = len(slots)//2
    width = columns*75+64
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 225" role="img" aria-label="{len(slots)}-position {"flashing" if flashing else "manual"} connector reference"><rect class="connector-frame" width="{width}" height="225" rx="8" fill="#122631"/><path class="connector-latch" d="M{width/2-25} 47V32H{width/2+25}V47" fill="none" stroke="#9eb5c2" stroke-width="3"/>']
    for s in slots:
        x, y = 32+(s['column']-1)*75, 52 if s['row']=='Upper' else 130
        signal = s.get('signal')
        attrs = f'data-position="{s["position"]}" data-manual="{s.get("manual_position",s["position"])}"'
        if flashing:
            attrs += f' data-signal="{signal}"' if signal else ''
        else:
            parts.append(f'<a href="#connector-{s["position"]}">')
        klass = ('flash-slot'+(' signal-'+signal if signal else '')) if flashing else 'connector-slot'
        parts.append(f'<g class="{klass}" {attrs} data-connector="{s["position"]}"><title>{esc(s["position"]+" · "+(s["wire"] or "Cross-marked"))}</title><rect x="{x}" y="{y}" width="72" height="68" rx="4" fill="{"#274654" if s["wire"] else "#1b303b"}" stroke="#7895a6"/><text class="slot-coordinate" x="{x+36}" y="{y+22}" text-anchor="middle" fill="#a8c3d1" font-size="13">{s["position"]}</text><text class="slot-wire" x="{x+36}" y="{y+51}" text-anchor="middle" fill="white" font-size="20">{esc(s["wire"] or "×")}</text></g>')
        if not flashing:
            parts.append('</a>')
    return ''.join(parts)+'</svg>'


def kkl_svg():
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1040 280" role="img" aria-label="ECU to KKL: external fused 12V to U03 and OBD16, shared ground to U07 and OBD4 or 5, K-line U12 to OBD7. USB to computer."><text class="kkl-label" x="24" y="26">ECU CONNECTIONS</text><text class="kkl-label" x="762" y="26">KKL / OBD TERMINALS</text><rect class="kkl-box" x="12" y="44" width="244" height="212" rx="8"/><rect class="kkl-box" x="748" y="44" width="280" height="212" rx="8"/>']
    for signal,y,left,right in [('power',80,'+12V · U03','16 · +12V'),('ground',150,'GND · U07','4 / 5 · GND'),('kline',220,'K-line · U12','7 · K-line')]:
        parts.append(f'<g class="signal-{signal}"><path class="connection-wire" d="M256 {y}H748"/><circle class="wire-end" cx="256" cy="{y}" r="5"/><circle class="wire-end" cx="748" cy="{y}" r="5"/><text class="terminal-text" x="32" y="{y+6}">{left}</text><text class="terminal-text" x="770" y="{y+6}">{right}</text></g>')
    parts.append('<rect class="supply-label" x="352" y="62" width="300" height="36" rx="4"/><text class="supply-text" x="502" y="86" text-anchor="middle">Fused external +12V supply</text><rect class="supply-label" x="352" y="132" width="300" height="36" rx="4"/><text class="supply-text" x="502" y="156" text-anchor="middle">Shared supply negative / ground</text><text class="kkl-footer" x="888" y="278" text-anchor="middle">USB → computer</text></svg>')
    return ''.join(parts)


class StaticSite:
    def __init__(self, root, site, records):
        self.root, self.site, self.records = root, site, records
        read = lambda p: json.loads((site/p).read_text(encoding='utf-8'))
        self.vehicles = read('vehicles/catalog.json')
        self.profiles = {p['id']:p for p in self.vehicles['profiles']}
        self.models = {m['id']:m for m in self.vehicles['models']}
        self.images = {i['id']:i for i in read('firmware/catalog.json')['images']}
        self.parts = {p['id']:p for p in read('vehicles/parts.json')['records']}
        self.definitions = read('vehicles/definitions.json')
        self.connections = read('flashing/connections.json')
        self.audit = read('pins/pin_audit.json')

    def path(self, profile, image, section):
        record = next(r for r in self.records if r['profile']==profile['id'] and r['firmware']==image['id'])
        return record['path']+('' if section=='overview' else section+'/')

    def overview(self, p, i, url, hardware=False):
        model = self.models[p['model']]
        photo = model['photo']
        record = self.parts.get(p.get('parts_record'))
        specs = [('Market',p['market']),('ECU',p['ecu'])]
        if record:
            specs += [('Model code / variant',record['model_code']+' · '+record['variant']),('Harness reference','; '.join((v['replaces']+' → ' if v['replaces'] else '')+v['listed_part'] for v in record['parts'] if v['role']=='harness'))]
        specs += [('Firmware',i['label']+' · '+i['variant']),('Oxygen sensor',p['oxygen'])]
        body = f'<div class="vehicle-summary"><div><div class="kicker">{esc(model["style"])} / {esc(p.get("display_status",p["association"]))}</div><h2>{esc(model["name"])}<br>{esc(str(p["year"]))}</h2><dl class="vehicle-specs">'+''.join(f'<dt>{k}</dt><dd>{esc(v)}</dd>' for k,v in specs)+'</dl></div>'
        body += f'<div><figure class="model-photo"><img class="vehicle-art" src="{url(photo["file"])}" width="{photo["width"]}" height="{photo["height"]}" alt="Yamaha {esc(model["name"])} — {esc(str(photo["year"]))} model reference" loading="lazy"><figcaption>{esc(photo["caption"])} <a href="{esc(photo["source"])}">Photo source ↗</a></figcaption></figure></div></div>'
        body += '<div class="profile-actions">'+''.join(f'<a href="{url(self.path(p,i,s))}">{label}</a>' for s,label in [('maps','Maps'),('pins','Pins'),('xdf','BIN & XDF downloads')])+'</div>'
        if hardware:
            if record:
                body += f'<h3>Catalogue parts for {esc(record["model_code"])} / {esc(record["country"])}</h3><div class="part-cards">'
                for part in record['parts']:
                    body += f'<article><span class="kicker">{esc(part["role"].replace("_"," "))}</span><strong>{esc(part["replaces"] or part["listed_part"])}</strong><p>{"Listed replacement: "+esc(part["listed_part"]) if part["replaces"] else "Listed part; no replacement relationship shown."}</p><a href="{esc(part["source_url"])}">{esc(part["assembly"])} · item {esc(str(part["reference"]))} ↗</a></article>'
                body += '</div>'
            body += '<h3>Wiring and MCU applicability</h3><p>Early and later application families have separate GPIO assignments and 26- / 34-position manual references. Exact hardware fitment, connector orientation and board continuity remain separately qualified.</p>'
        sources = [s for s in self.vehicles['sources'] if s['id'] in p['source_ids']]
        body += '<details><summary>Identification &amp; sources</summary><p>'+esc(p['notes'])+'</p><p>'+str(i['size'])+' bytes · SHA-256 <code>'+i['sha256']+'</code></p>'
        if p.get('label_evidence'):
            body += '<p>'+esc(p['label_evidence'])+'</p>'
        return body+'<ul class="source-list">'+''.join(f'<li><h3><a href="{esc(s["url"])}">{esc(s["title"])} ↗</a></h3><p>{esc(s["claim"])}</p><small>{esc(s["locator"])}</small></li>' for s in sources)+'</ul></details>'

    def picker(self, p, i, section, url):
        records = []
        for r in self.records:
            profile, image = self.profiles[r['profile']], self.images[r['firmware']]
            records.append(dict(model=profile['model'], year=str(profile['year']), market=profile['market'],
                                ecu=profile['ecu'], key=r['profile']+'/'+r['firmware'],
                                firmware=image['label']+' · '+image['variant'], path=url(r['path'])))
        data = dict(selected=p['id']+'/'+i['id'], records=records,
                    models=[dict(id=m['id'],name=m['name']) for m in self.models.values() if not m.get('reference_only')])
        body = '<div id="choose-bike" class="bike-chooser"><form id="bike-form" hidden><div class="vehicle-selectors">'
        for key,label in [('model','Motorcycle'),('year','Year'),('market','Market / specification'),('ecu','ECU'),('firmware','Firmware')]:
            body += f'<label>{label}<select id="choose-{key}" required></select></label>'
        body += '</div><div class="bike-form-actions"><button type="submit">View bike</button></div></form>'
        # CSS/HTML navigation remains available if the local enhancement is blocked.
        body += '<details id="bike-fallback" class="bike-fallback"><summary>Choose bike</summary><div class="bike-fallback-models">'
        for m in self.models.values():
            if m.get('reference_only'):
                continue
            choices = [r for r in records if r['model']==m['id']]
            if not choices:
                body += '<p class="unavailable">'+esc(m['name'])+' · No BIN yet</p>'
                continue
            body += '<details><summary>'+esc(m['name'])+'</summary>'
            for year in sorted({r['year'] for r in choices}):
                body += '<details><summary>'+esc(year)+'</summary><ul>'
                for r in choices:
                    if r['year']!=year:
                        continue
                    current = ' aria-current="page"' if r['key']==data['selected'] else ''
                    body += f'<li><a href="{esc(r["path"])}"{current}>{esc(r["market"]+" · "+r["firmware"])}</a></li>'
                body += '</ul></details>'
            body += '</details>'
        body += '</div></details><script type="application/json" id="bike-choices">'+json.dumps(data,ensure_ascii=False).replace('</','<\\/')+'</script></div>'
        return body+f'<script src="{url("assets/bike-picker.js")}" defer></script>'

    def pin_reference(self, soup, image, url):
        audited = next(i for i in self.audit['images'] if i['id']==image['id'])
        family = copy.deepcopy(self.audit['families'][audited['family']])
        pins, connector = family['pins'], family['connector']
        for pin in pins:
            pin['check'] = next(c for c in audited['checks'] if c['pin']==pin['pin'])
        scope = soup.find(id='pin-scope')
        scope['data-firmware'], scope['data-family'] = image['id'], audited['family']
        put(scope, f'<div class="eyebrow">Selected firmware / {audited["family"]} application</div><h2>{esc(image["label"])}</h2><p>{esc(image["variant"])} · Boot {esc(image["boot_status"])} · <code>{image["sha256"][:16]}…</code></p><div class="pin-checks"><div><strong>{audited["verified_code_pins"]} positions</strong><span>Instruction bytes checked in this BIN<br>{audited["runtime_code_pins"]} runtime use · {audited["configuration_code_pins"]} configuration only</span></div><div><strong>80 / 80</strong><span>Package labels checked against the MC9S12T64 datasheet</span></div><div><strong>Physical match open</strong><span>Chip marking and connector-to-board continuity unconfirmed</span></div></div>')
        soup.find(id='pin-eyebrow').string = 'Firmware hardware reference / '+image['label']
        soup.find(id='pin-intro').string = 'Select a connector position or MCU pin to read its signal and evidence. All 80 positions and the selected BIN’s connector reference are included in this page.'
        put(soup.find(id='connector-intro'),f'<strong>{len(connector["slots"])} drawing positions</strong> · <a href="{esc(connector["source_url"])}#page={connector["source_pdf_pages"][-1]}">{esc(connector["source_title"])} ↗</a><br>{esc(connector["target_scope"])}')
        put(soup.select_one('.connector-scroll'),connector_svg(connector))
        put(soup.find(id='connector-detail'),'<p>Follow a connector position to its circuit reference below.</p>')
        put(soup.find(id='detail'),'<h2>Choose a signal</h2><p>The package diagram links to the complete pin reference below.</p>')
        notes = ('Early code: PAIR uses PP1. The ordinary ADC scan skips AN7; PE2/PE3 cycle during banked acquisition. Oxygen software exists but stock variant 9 leaves feedback inactive.' if audited['family']=='early' else 'Later code: PAIR uses PP0; PP1 drives a diagnostic/fault-pattern output. AN7 is sampled, PE2/PE3 are initialized low, and PT7 is an auxiliary GPIO with an unresolved external destination. The manual adds an oxygen-signal and heater circuit.')
        soup.find(id='family-notes').string = notes
        put(soup.find(id='flash-comparison'),f'<h2>Flashing connections</h2><p><a href="{url(self.path(self.p,image,"flashing"))}">Open this ECU’s flashing connector and KKL reference ↗</a></p>')
        base = json.loads(soup.find(id='pin-data').string)
        base.update(pins=pins,ecu_connector=connector,sources=self.audit['sources'])
        soup.find(id='pin-data').string = json.dumps(base).replace('</','<\\/')
        put(soup.find(id='comparison'),''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in row)+'</tr>' for row in base['model_comparison']))
        put(soup.find(id='sources'),''.join(f'<li><a href="{esc(s["url"])}">{esc(s["title"])}</a>, PDF pages {", ".join(map(str,s["pdf_pages"]))}</li>' for s in self.audit['sources']))
        soup.find(id='pin-structured')['href'] = url('pins/pin_audit.json')
        colors = dict(sensor='#147d92',digital='#147d92',actuator='#c86027',communication='#5863bd',internal='#728092',power='#b63d57',unresolved='#aab4bd')
        diagram = soup.select_one('.diagram svg')
        diagram.find('text').string = image['label']+' · conditional MCU package reference'
        for el in diagram.select('.pin'):
            pin = pins[int(el['data-pin'])-1]
            el.find('rect')['fill'] = colors[pin['category']]
            el['aria-label'] = f'Package pin {pin["pin"]}: {pin["signal"]}, {pin["role"]}'
            el.attrs.pop('role',None)
            link = soup.new_tag('a',href='#pin-'+str(pin['pin']))
            el.wrap(link)
        asset = 'pins/'+image['id']+'-package.svg'
        (self.site/asset).write_text(str(diagram),encoding='utf-8')
        soup.find(id='pin-drawing')['href'] = url(asset)
        put(soup.find(id='rows'),''.join(f'<tr><td><a href="#pin-{pin["pin"]}">{pin["pin"]}</a></td><td>{esc(pin["signal"])}</td><td><a href="#pin-{pin["pin"]}">{esc(pin["role"])}</a></td><td>{esc(pin["status"])}<br>{esc(pin["check"]["code_status"])}</td><td>{pin["diagnostic"] if pin["diagnostic"] is not None else "—"}</td></tr>' for pin in pins))
        soup.find(id='count').string = '80 of 80 package positions'
        body = '<section class="static-pin-reference"><h2>Connector circuit reference</h2><div class="static-pin-cards">'
        for slot in connector['slots']:
            refs = ' · '.join(f'<a href="#pin-{n}">MCU pin {n}</a>' for n in slot['mcu_package_pins'])
            body += f'<article id="connector-{slot["position"]}"><h3>{slot["position"]} · {esc(slot["wire"] or "Cross-marked")}</h3><strong>{esc(slot["role"])}</strong><p>{esc(slot["association"])}. {esc(slot["path"])}</p><p>{refs or "No specific MCU package pin assigned to this route."}</p></article>'
        body += '</div><h2>MCU package reference — all 80 positions</h2><div class="static-pin-cards">'
        for pin in pins:
            refs = ' · '.join(f'<a href="#connector-{s["position"]}">{s["position"]} · {esc(s["wire"])}</a>' for s in pin['ecu_connector_positions'])
            evidence = ''.join(f'<p><code>{esc(e["address"]+" · "+e["bytes"]+" · "+e["instruction"])}</code></p>' for e in pin['evidence_instructions'])
            body += f'<article id="pin-{pin["pin"]}" data-static-pin="{pin["pin"]}"><div class="eyebrow">MCU package pin {pin["pin"]}</div><h3>{esc(pin["signal"])}</h3><strong>{esc(pin["role"])}</strong><p>{esc(pin["function"])}</p><p>{esc(pin["status"])} · {esc(pin["check"]["code_status"])}</p><dl><dt>Register / channel</dt><dd>{esc(pin["register"] or "Package function or unresolved application role")}</dd><dt>Diagnostic selector</dt><dd>{pin["diagnostic"] if pin["diagnostic"] is not None else "Not assigned"}</dd><dt>Runtime RAM</dt><dd>{esc(" · ".join(pin["ram"]) or "Not assigned")}</dd><dt>Harness circuit</dt><dd>{esc(pin["xt_wire"] or "Physical route unconfirmed")}</dd><dt>Connector reference</dt><dd>{refs or "No external terminal association established."}</dd></dl>'
            if pin.get('boot_required') and not pin['check']['code_verified']:
                body += '<p>Instructions below are from the companion boot; those bytes are absent from this BIN.</p>'
            body += '<p><a href="https://www.nxp.com/docs/en/data-sheet/9S12T64AF16V1.pdf#page=60">Datasheet package reference ↗</a>. Physical chip marking and board continuity remain unconfirmed.</p><details><summary>Firmware instruction evidence</summary>'+ (evidence or '<p>No instruction assignment established.</p>')+'</details></article>'
        body += '</div></section>'
        soup.find(id='pin-explorer').append(fragment(body))
        # Keep the enhanced explorer, using the already-selected embedded data.
        # A separately blocked catalogue script must never hide the static view.
        for script in soup.find_all('script'):
            if not script.get('src') and script.get('type')!='application/json' and script.string:
                text = script.string.replace("document.getElementById('pin-explorer').hidden=true;",'')
                text = text.replace("scope.setAttribute('aria-busy','true');scope.textContent=", "if(scope.dataset.firmware===firmware)return;scope.setAttribute('aria-busy','true');scope.textContent=")
                text += "\ndocument.documentElement.classList.add('pins-ready');\n"
                text = text.replace("if(c){selectConnector", "if(c){e.preventDefault();selectConnector")
                text = text.replace("if(el)selectPin(el.dataset.pin||el.dataset.select)","if(el){e.preventDefault();selectPin(el.dataset.pin||el.dataset.select)}")
                script.string = text

    def flashing(self, soup, image, url):
        p = self.connections['profiles'][self.p['id']]
        f = self.connections['families'][p['family']]
        soup.find(id='connection-content').attrs.pop('hidden',None)
        soup.find(id='connection-title').string = image['label']+f' · {f["positions"]} positions'
        soup.find(id='connection-model').string = f'{self.p["model"].upper()} · {self.p["year"]} · {image["variant"]}'
        soup.find(id='connection-badge').string = p['evidence']
        soup.find(id='connection-view').string = f['source']['view']
        soup.find(id='connection-limit').string = f['source']['note']
        diagram = soup.find(id='flash-connector-diagram')
        diagram['data-family'],diagram['data-firmware'] = p['family'],image['id']
        put(diagram,connector_svg(f,True))
        names = dict(power='+12V',ground='GND',kline='K-line')
        put(soup.find(id='connection-terminals'),''.join(f'<article class="signal-{s["signal"]}"><span>{names[s["signal"]]}</span><strong>Upper {s["column"]}</strong><small>{esc(s["wire"])} · manual {s["manual_position"]}</small></article>' for s in f['slots'] if s.get('signal')))
        put(soup.find(id='kkl-diagram'),kkl_svg())
        put(soup.find(id='connection-source-links'),f'<ul><li><a href="{url(f["source"]["url"])}">{esc(f["source"]["title"])}</a></li><li><a href="{esc(f["manual_url"])}">{esc(f["manual_title"])}</a></li><li><a href="{self.connections["kkl"]["source_url"]}">{esc(self.connections["kkl"]["source_title"])}</a></li></ul>')

    def page(self, path):
        current = path.relative_to(self.site).as_posix()
        soup = fragment(path.read_text(encoding='utf-8'))
        panel = soup.find(id='vehicle-context')
        if panel is None:
            return
        iid = panel.get('data-firmware')
        if current.startswith('firmware/') and len(current.split('/'))>2:
            iid = current.split('/')[1]
        p = self.profiles.get(panel.get('data-profile'))
        if not p:
            p = next((p for p in self.profiles.values() if iid in p['firmware_ids']),self.profiles[self.vehicles['default_profile']])
        image = self.images.get(iid) or self.images[p['firmware_ids'][0]]
        self.p = p
        section = panel.get('data-section') or next((k for k,v in SECTIONS.items() if current==v),'overview')
        if current.startswith('firmware/'):
            section = 'maps' if '/maps/' in current else 'overview'
        url = lambda target: posixpath.relpath(target,posixpath.dirname(current))+('/' if target.endswith('/') else '')
        panel['data-profile'],panel['data-firmware'] = p['id'],image['id']
        panel['data-static-context'] = 'true'
        put(soup.find(id='selection-status'),esc(f'{self.models[p["model"]]["name"]} · {p["year"]} · {image["label"]} · {image["variant"]}'))
        if soup.select_one('.bike-picker') is not None:
            panel.append(fragment(self.picker(p,image,section,url)))
        else:
            panel['class'] = [*panel.get('class',[]),'vehicle-context-compact']
            panel.append(fragment(f'<a class="change-bike" href="{url(self.path(p,image,"overview"))}#choose-bike">Change bike</a>'))
        for ident in ['vehicle-research','vehicle-hardware']:
            node=soup.find(id=ident)
            if node is not None:
                put(node,self.overview(p,image,url,ident=='vehicle-hardware'))
        selected=soup.find(id='xdf-selected')
        if selected is not None:
            put(selected,selected_definition(image,url))
        defs=soup.find(id='vehicle-definitions')
        if defs is not None:
            selected=[d for d in self.definitions if (d['source_path'].startswith('xt 660 r/') if image.get('map_catalog')=='primary' else '2012-2016' in d['source_path'] if '2c1-10' in image['id'] else '2008' in d['source_path'] if re.search(r'5vk-(1x|11)',image['id']) else False)]
            put(defs,('<ul class="definition-list">'+''.join(f'<li><a href="https://github.com/terrafirma2021/yamaha-xt660/blob/main/{d["stored_path"].replace(" ","%20")}">{esc(d["source_path"])}</a></li>' for d in selected)+'</ul><p>Source definitions are candidates; presence does not verify addressing, units or ECU compatibility.</p>') if selected else '<p>No definition is assigned to this firmware. Existing XDFs are not automatically transferred.</p>')
        for el in soup.select('[data-study]'):
            kind=el['data-study']
            if kind=='pins' or (image.get('shared_map_count') and (kind!='hardware' or p['hardware']=='early-owner')):
                continue
            el['hidden']=''
            el.insert_before(fragment(f'<section class="scope-unavailable"><h2>Original-calibration reference</h2><p>This document describes the original application. Use the selected BIN’s own maps and family analysis.</p><p><a href="{url("firmware/"+image["id"]+"/maps/")}">Maps for {esc(image["label"])} ↗</a> · <a href="{url("docs/firmware/FAMILY_DECODING.html")}">Application-family analysis ↗</a></p></section>'))
        if soup.find(id='pin-data'):
            self.pin_reference(soup,image,url)
        if soup.find(id='flash-connector-diagram'):
            self.flashing(soup,image,url)
        # All primary links keep exact model/BIN context without click handlers.
        for link in soup.find_all('a',href=True):
            u=urlsplit(link['href'])
            if u.scheme or u.netloc or not u.path or u.path.startswith('/'):
                continue
            dest=posixpath.normpath(posixpath.join(posixpath.dirname(current),u.path)).rstrip('/')
            target=next((k for k,v in SECTIONS.items() if dest in (v,v.removesuffix('/index.html'))),None)
            if dest in ('.','index.html'):
                target='overview'
            if target:
                link['href']=url(self.path(p,image,target))+('#'+u.fragment if u.fragment else '')
            elif dest in ('firmware','firmware/index.html') and link.find_parent('nav',attrs={'aria-label':'Main navigation'}):
                link['href']=url('firmware/'+image['id']+'/')
        path.write_text(soup.decode(formatter=FORMAT),encoding='utf-8',newline='\n')


def build(root,site,records):
    renderer=StaticSite(root,site,records)
    for page in sorted(site.rglob('*.html')):
        renderer.page(page)
    print('Rendered complete HTML contexts, connector diagrams and all 80 MCU positions without JavaScript.')
