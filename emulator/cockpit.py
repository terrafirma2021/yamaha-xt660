"""External bike fixtures and a serial-connected dash around unchanged firmware.

The simple rotating-engine fixture is a demonstration, not a torque model.
Instrument data comes from MeterPeer; RAM is confined to advanced debug state.
"""
from engine import Engine
from meter import MeterPeer

FAULTS = {
    'none': ('Healthy sensors', {}),
    'coolant': ('Coolant disconnected', {6:1023}),
    'throttle': ('Throttle circuit low', {0:0}),
    'pressure': ('Intake pressure circuit low', {1:0}),
    'air': ('Intake temperature disconnected', {3:1023}),
    'combined': ('Coolant + throttle faults', {6:1023,0:0}),
}


def intake_fixture(throttle, pitch, turning):
    """Uncalibrated sensor-count model, not a recovered pressure/VE map.

    At rest pressure equals the chosen ambient input. Pumping causes a dip;
    opening the throttle reduces that depression, increasing speed increases
    it. Native ADC sampling applies the dip over two crank revolutions.
    The ECU itself still performs all pressure filtering and map lookups.
    """
    ambient = 512
    if not turning:
        return ambient, 0
    pumping = min(224, max(64, round(160 * 1800 / pitch)))
    depression = round(pumping * (1 - 0.75 * throttle / 100))
    return ambient, depression


class Cockpit:
    def __init__(self, executable, wsl=False):
        self.executable, self.wsl = executable, wsl
        self.engine = None
        self.image = None
        self.storage = None
        self.meter = MeterPeer()
        self.gear = 0
        self.throttle = 0
        self.coolant = 512
        self.fault = 'none'
        self.run = True
        self.rotating = False
        self.starting = False
        self.auth = 'Key off'
        self.pitch = 2800
        self.start_cycle = 0
        self.last_firing = 0
        self.start_ticks = 0

    def select(self, image):
        self.power(False)
        if image != self.image:
            self.storage = None
        self.image = image
        self.fault = 'none'
        self.throttle = self.gear = 0

    def power(self, enabled, wrong_key=False, diagnostic=False):
        if type(enabled) is not bool or type(wrong_key) is not bool:
            raise ValueError('Key state must be boolean')
        if not enabled:
            if self.engine:
                try:
                    self.storage = self.engine.external_storage()
                finally:
                    self.engine.close()
                    self.engine = None
            self.engine = None
            self.meter = MeterPeer()
            self.rotating = self.starting = False
            self.auth = 'Key off'
            return
        if self.engine:
            return
        if self.image is None:
            raise ValueError('Select a BIN first')
        self.engine = Engine(self.executable,self.image,self.wsl,storage=self.storage)
        self.meter = MeterPeer(lambda:self.engine.cycles,self.engine.wait_cycles)
        self.engine.session.command('set memory xtboot_0_cfg 41 1')
        self.inputs()
        # Let the firmware's switch filters observe starter released before
        # a later start-button press; host time does not advance the ECU.
        self.engine.step(200000)
        self.auth = 'Disabled in BIN'
        if self.engine.authentication_required:
            self.engine.authenticate(corrupt=wrong_key)
            self.auth = 'Key rejected' if wrong_key else 'Key accepted'
        if self.auth != 'Key rejected':
            self.meter.connect(self.engine.exchange,diagnostic)

    def inputs(self):
        if not self.engine:
            return
        # PB4: low neutral; PB1: low starter request. PB0 interlock stays low.
        self.engine.set_port('B', (16 if self.gear else 0) | (0 if self.starting else 2))
        values = [round(120+self.throttle*7),512,512,512,
                  0 if self.meter.mode!='normal' and not self.run else 512,512,self.coolant,512]
        values_override = FAULTS[self.fault][1]
        for channel, value in enumerate(values):
            self.engine.set_adc(channel,values_override.get(channel,value))
        self.pressure_input()
        self.engine.session.command(f'set memory xtboot_0_cfg 40 {1 if self.meter.mode=="normal" else 0}')

    def pressure_input(self):
        ambient, dip = intake_fixture(self.throttle,self.pitch,self.starting or self.rotating)
        if self.fault == 'pressure':
            ambient = dip = 0
        self.engine.set_adc(1,ambient)
        self.engine.session.command(f'set memory xtboot_0_cfg 39 {dip}')

    def control(self, name, value):
        if name == 'gear':
            if type(value) is not int or value not in (0,1):
                raise ValueError('Gear must be 0 (neutral) or 1')
            self.gear = value
        elif name == 'throttle':
            if type(value) is not int or not 0 <= value <= 100:
                raise ValueError('Throttle travel must be 0..100')
            self.throttle = value
        elif name == 'coolant':
            if type(value) is not int or not 0 <= value <= 1023:
                raise ValueError('Coolant input must be 0..1023 ADC')
            self.coolant = value
        elif name == 'fault':
            if value not in FAULTS:
                raise ValueError('Unknown external fault fixture')
            self.fault = value
        elif name == 'run':
            if type(value) is not bool:
                raise ValueError('Run switch must be boolean')
            self.run = value
            if not value:
                self.stop()
        else:
            raise ValueError('Unknown bike control')
        self.inputs()

    def stop(self):
        self.starting = self.rotating = False
        if self.engine:
            self.engine.drive(None)
            self.inputs()

    def start(self):
        if not self.engine or not self.run:
            raise ValueError('Turn the key and run switch on first')
        if self.meter.mode != 'normal':
            raise ValueError('Leave diagnostic mode before starting')
        if self.auth == 'Key rejected':
            raise ValueError('The ECU rejected this key')
        if self.rotating or self.starting:
            return
        # A stationary key-on interval gives the stock scheduler time to
        # qualify idle inputs before the first CPS edge. Time is simulated.
        while self.engine.snapshot()['counts']['bus_cycles'] < 32000000:
            self.engine.step(1000000)
            self.meter.poll(self.engine.exchange)
        self.starting = True
        self.start_ticks = 0
        self.pitch = 2800
        self.inputs()
        self.start_cycle = self.engine.snapshot()['counts']['bus_cycles']
        self.last_firing = self.start_cycle
        self.engine.start_drive(self.pitch)

    def tick(self):
        if not self.engine:
            raise ValueError('Key is off')
        if self.rotating:
            target = round(1800-self.throttle*13)
            self.pitch += max(-200,min(200,target-self.pitch))
            self.engine.drive(self.pitch,road=bool(self.gear))
            self.pressure_input()
        if self.meter.mode != 'normal':
            for _ in range(8):self.meter.poll(self.engine.exchange)
        else:
            self.engine.step(200000)
            if self.auth != 'Key rejected':
                self.meter.poll(self.engine.exchange)
        now = self.engine.snapshot()['counts']['bus_cycles']
        edges = [e for e in self.engine.trace if e['kind']=='output' and e['cycle']>self.start_cycle]
        coil = [e['cycle'] for e in edges if e['channel']==3]
        fuel = [e['cycle'] for e in edges if e['channel']==6]
        if coil and fuel:
            self.last_firing = min(coil[-1],fuel[-1])
        if self.starting:
            self.start_ticks += 1
            if len(coil)>=4 and len(fuel)>=4:
                self.rotating = True
                self.starting = False
                self.inputs()
            elif self.start_ticks >= 16:
                self.stop()
        elif self.rotating and now-self.last_firing>4000000:
            self.stop()

    def diagnostics(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('Diagnostic state must be boolean')
        self.power(False)
        self.run = not enabled
        self.power(True,diagnostic=enabled)
        self.inputs()

    def diagnostic_test(self, enabled):
        if type(enabled) is not bool or self.meter.mode != 'diagnostic':
            raise ValueError('Enter diagnostics before running a test')
        if self.meter.diag_id not in (30,36,37,48,50,51,52,57):
            raise ValueError('Select an actuator diagnostic first')
        self.control('run',False)
        for _ in range(2):self.tick()
        if enabled:self.control('run',True)

    def diagnostic_item(self, number):
        if type(number) is not int or number not in (61,62):
            raise ValueError('Choose fault history 61 or count 62')
        if self.meter.mode != 'diagnostic':
            raise ValueError('Wait for diagnostic entry to finish')
        for _ in range(24):
            if self.meter.diag_id == number:
                return
            self.diagnostic_next(-1)
        raise RuntimeError('ECU did not select the requested diagnostic item')

    def diagnostic_next(self, direction):
        if self.meter.mode != 'diagnostic' or type(direction) is not int or direction not in (-1,1):
            raise ValueError('Enter diagnostics and choose Previous or Next')
        if self.run:
            self.control('run',False)
            for _ in range(2):self.tick()
        self.meter.navigate(self.engine.exchange,direction)

    def clear_history(self):
        if self.meter.mode != 'diagnostic' or self.meter.diag_id != 62:
            raise ValueError('Select d:62 before clearing history')
        # The stock diagnostic detects a supply-monitor low/high transition,
        # corresponding to the run-switch procedure. No history RAM is edited.
        for run in (False,True):
            self.control('run',run)
            for _ in range(4):
                self.tick()

    def state(self):
        return dict(selected=self.image, powered=self.engine is not None,
                    gear=self.gear, throttle=self.throttle, coolant=self.coolant,
                    run=self.run, starting=self.starting, rotating=self.rotating,
                    authentication=self.auth, fault=self.fault,
                    faults=[dict(id=k,label=v[0]) for k,v in FAULTS.items()],
                    meter=self.meter.state())
