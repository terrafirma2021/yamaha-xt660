"""Separate flashing workspace; source-backed connector redraws, no live writes."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def connection_data(catalog):
    audit = json.loads((ROOT/'analysis/firmware/pin_audit.json').read_text(encoding='utf-8'))
    vehicles = json.loads((ROOT/'dataset/vehicles.json').read_text(encoding='utf-8'))
    sources = {
        'early': dict(file='site/assets/references/xt660-early-flashing-photo.png',
                      url='assets/references/xt660-early-flashing-photo.png',
                      title='Supplied XT660 / MT03 2005–2008 connector photograph',
                      view='ECU connector mating face, latch above — as photographed',
                      note='The photograph identifies the face and three connections, but shows no ECU part-number label. Its 2005–2008 caption is not an independent fitment record.'),
        'late': dict(file=audit['flash_comparison']['source'],
                     url='assets/references/xt660-late-flashing-sketch.jpg',
                     title='Supplied XT660 2012 / 2C1-8591A-10 flashing drawing',
                     view='As drawn in the supplied flashing sketch, latch above',
                     note='The sketch labels 2C1-8591A-10. Its mating-face versus wire-entry convention is not stated; verify the physical connector view before wiring.'),
    }
    families = {}
    for family, source in sources.items():
        c = audit['families'][family]['connector']
        columns = len(c['slots']) // 2
        # Both supplied flashing references run opposite to the Yamaha manual.
        # Wire labels below are a correlated manual overlay, not labels read
        # from the photograph. Keep both coordinate systems explicit.
        slots = []
        for s in c['slots']:
            column = columns + 1 - s['column']
            signal = {'R': 'power', 'B/W': 'ground', 'Y/L': 'kline'}.get(s['wire']) if s['row'] == 'Upper' else None
            slots.append(dict(position=f'{s["row"][0]}{column:02}', row=s['row'], column=column,
                              wire=s['wire'], manual_position=s['position'], signal=signal))
        slots.sort(key=lambda s: (s['row'] != 'Upper', s['column']))
        assert {s['position']: s['signal'] for s in slots if s['signal']} == {'U03': 'power', 'U07': 'ground', 'U12': 'kline'}
        source['sha256'] = hashlib.sha256((ROOT/source['file']).read_bytes()).hexdigest()
        families[family] = dict(id=family, positions=columns*2, columns=columns, slots=slots,
                                source=source, manual_title=c['source_title'],
                                manual_url=c['source_url'] + '#page=' + str(c['source_pdf_pages'][-1]))
    images = {i['id']: i for i in catalog['images']}
    profiles = {}
    for p in vehicles['profiles']:
        if not p['firmware_ids']:
            continue
        families_for_profile = {images[i]['code_family'] for i in p['firmware_ids']}
        assert len(families_for_profile) == 1
        family = next(iter(families_for_profile))
        profiles[p['id']] = dict(family=family, firmware_ids=p['firmware_ids'], model=p['model'],
                                 year=p['year'], ecu=p['ecu'],
                                 evidence='labelled ECU drawing' if p['hardware']=='brazil-2c1-10' else
                                          'model reference photograph' if p['hardware'] in ('early-owner','early-reference') else
                                          'application-family reference; physical fitment unconfirmed')
    return dict(schema_version=1, families=families, profiles=profiles,
                kkl=dict(power=[16], ground=[4,5], kline=[7], source_url='https://www.guzzidiag.de/',
                         source_title='GuzziDiag / IAWDiag — USB-KKL adapter connection table'),
                live_operations_available=False)


def build(shell, write, catalog):
    data = connection_data(catalog)
    write('flashing/connections.json', json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    write(data['families']['late']['source']['url'], (ROOT/data['families']['late']['source']['file']).read_bytes())
    body = '''<div class="page-heading"><div class="kicker">XT660 / FLASHING</div><h1>Connect. Back up. Flash.</h1><p>Connector references and BIN checks for the selected ECU. <a href="../tune/">Edit features &amp; maps in Tune ↗</a></p></div>
<nav class="tool-links" aria-label="Flashing workflow"><a href="#connect"><span>01</span> Connections</a><a href="#backup"><span>02</span> Backup &amp; BIN checks</a><a href="#flash"><span>03</span> Flash &amp; verify</a></nav>
<p id="flash-error" class="notice" role="alert" hidden></p>
<section id="connect" class="tool-panel connection-panel"><div class="tool-step">01 / CONNECTIONS</div>
<div class="connection-heading"><div><h2 id="connection-title">Loading ECU connector…</h2><p id="connection-model" role="status"></p></div><span class="connection-badge" id="connection-badge">Source reference</span></div>
<div id="connection-content" hidden>
<div class="connection-legend" aria-label="Connection colours"><span class="signal-power">+12V · R</span><span class="signal-ground">GND · B/W</span><span class="signal-kline">K-line · Y/L</span></div>
<figure class="flash-connector"><div id="flash-connector-diagram"></div><figcaption id="connection-view"></figcaption></figure>
<div id="connection-terminals" class="connection-terminals"></div>
<p class="tool-note">U/L positions count left to right in this redraw; they are not Yamaha cavity numbers. Colours highlight signals; R, B/W and Y/L are the Yamaha wire codes.</p>
<div class="connection-kkl"><div class="tool-step">USB KKL / NUMBERED BREAKOUT</div><h3>ECU to USB KKL cable</h3><p>External 12V supply powers the ECU and the cable’s vehicle interface. USB connects the cable to your computer.</p>
<div id="kkl-diagram"></div><dl class="kkl-mobile"><div class="signal-power"><dt>+12V · U03</dt><dd>OBD 16</dd></div><div class="signal-ground"><dt>GND · U07</dt><dd>OBD 4 / 5</dd></div><div class="signal-kline"><dt>K-line · U12</dt><dd>OBD 7</dd></div></dl><p class="tool-note">Use a fused external 12V supply and shared ground. OBD numbers identify breakout terminals, not a plug-face orientation; use the moulded numbers on your breakout. Ground uses pin 4 or 5 depending on the cable. L-line pin 15 is unused in this reference.</p></div>
<div class="connection-limits"><strong>Connection reference · bench validation pending</strong><p id="connection-limit"></p><p>The flash-tool reference identifies K-line, but the internal route to the boot serial port and complete power-on sequence have not been hardware-validated.</p></div>
<details class="connection-sources"><summary>Source images, manual positions &amp; MCU links</summary><div id="connection-source-links"></div><p>Wire labels are taken from the Yamaha manual and reflected to match the supplied flash reference. The additional black ground wire shown in the manual is not identified as a separate bench lead by either flash reference.</p><p><a href="../pins/">Open this ECU’s connector &amp; MCU explorer ↗</a> · <a href="../docs/firmware/FLASH_CONNECTIONS.html">Connection evidence ↗</a></p></details></div>
<div class="connection-action"><div><strong>Boot connection</strong><p>9,600 baud · 8 data bits · no parity · 1 stop bit</p></div><button id="ecu-connect" disabled aria-describedby="connection-availability">Connect ECU</button></div><p id="connection-availability" class="tool-note">Live connection, reading and flashing are in development. The controls remain unavailable.</p></section>
<section id="backup" class="tool-panel"><div class="tool-step">02 / BACKUP &amp; BIN CHECKS</div><h2>Check the file before the write.</h2><div class="tool-actions"><button id="read-ecu" disabled aria-describedby="connection-availability">Read BIN from ECU</button></div>
<p>Open a repository BIN or your saved file to check its identity, startup checksum and boot coverage. Inspection leaves every byte unchanged.</p>
<div class="flash-file-picker"><label>Repository BIN<select id="flash-repo-bin" disabled><option>Loading repository BINs…</option></select></label><button id="flash-repo-open" disabled>Open repository BIN</button><label class="file-label">Or open a local BIN<input id="flash-bin-file" type="file" accept=".bin,application/octet-stream"></label></div>
<p id="flash-bin-status" role="status">No BIN opened.</p><div id="flash-checks" class="flash-checks"></div><dl id="flash-bin-facts" class="firmware-facts"></dl>
<div class="tool-actions"><button id="flash-save-copy" disabled>Save unchanged BIN</button><button id="flash-save-report" disabled>Save check report</button><a class="workbench-link" href="../tune/">Open Tune ↗</a></div>
<label>Compare another backup or saved readback<input id="flash-compare-file" type="file" accept=".bin,application/octet-stream" disabled></label><p id="flash-compare-status" role="status"></p></section>
<section id="flash" class="tool-panel"><div class="tool-step">03 / FLASH &amp; VERIFY</div><h2>Write. Read back. Compare.</h2><p>Live writing and ECU readback are in development. A checksum pass alone does not establish a complete backup or physical ECU compatibility.</p><div class="tool-actions"><button id="flash-ecu" disabled aria-describedby="connection-availability">Flash ECU</button><button id="verify-readback" disabled aria-describedby="connection-availability">Verify ECU readback</button></div><a href="../docs/firmware/FLASH_TOOLING.html">Protocol research &amp; implementation progress ↗</a></section>'''
    write('flashing/index.html', shell('Flashing — connections and backup', body, 'flashing/index.html', 'Flashing',
          '<link rel="stylesheet" href="../assets/tools.css"><link rel="stylesheet" href="../assets/flashing.css"><script type="module" src="../assets/flashing.mjs"></script>'))
