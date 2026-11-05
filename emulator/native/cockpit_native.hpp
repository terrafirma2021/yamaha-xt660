// SPDX-License-Identifier: GPL-2.0-or-later
// External fixtures and serial meter peer. No firmware variables are forced.
#pragma once
#include "engine_native.hpp"
#include "engine_plant.hpp"
#include <cmath>
#include <map>

inline void require(bool valid,const std::string &message) {if(!valid)throw std::invalid_argument(message);}
inline int integer(const Json &v,int low,int high) {
  require(v.is_number_integer(),"Expected an integer");int n=v.get<int>();
  require(n>=low&&n<=high,"Value outside supported range");return n;
}
inline bool bool_value(const Json &v) {require(v.is_boolean(),"Expected a boolean");return v.get<bool>();}
inline int rounded(double n) { // Match Python's round-to-even fixture exactly.
  double f=std::floor(n),d=n-f;return int(d<.5?f:d>.5?f+1:std::fmod(f,2)==0?f:f+1);
}
inline unsigned throttle_adc(int travel) {
  // Yamaha 5VK1-AE1, p. 7-10: d:01 closed 15-17, open 97-100.
  // The reviewed BINs send the left-aligned ADC high byte (10-bit >> 2).
  // Nominal fixture endpoints 16 and 100; interpolate control travel only.
  // This does not establish sensor volts or mechanical degrees between stops.
  return unsigned(rounded(64.0 + travel * 336.0 / 100));
}
inline const std::map<int,std::string> fault_names={
 {11,"Cylinder identification"},{12,"Crank signal"},{13,"Intake pressure circuit"},{14,"Intake pressure"},
 {15,"Throttle circuit"},{16,"Throttle position"},{19,"Start interlock"},{20,"Pressure mismatch"},
 {21,"Coolant sensor circuit"},{22,"Intake temperature circuit"},{23,"Atmospheric pressure"},{24,"Oxygen sensor"},
 {30,"Lean-angle shutdown"},{31,"Oxygen feedback"},{32,"Oxygen feedback"},{33,"Ignition coil"},{34,"Ignition coil 2"},
 {37,"Idle control"},{41,"Lean-angle circuit"},{42,"Speed / neutral"},{43,"Supply monitor"},{44,"EEPROM"},
 {46,"System voltage"},{50,"Internal memory"}};
inline const std::map<int,std::pair<std::string,std::string>> diagnostic_names={
 {1,{"Throttle position","sensor"}},{3,{"Intake pressure","sensor"}},{5,{"Intake temperature","sensor"}},
 {6,{"Coolant temperature","sensor"}},{7,{"Vehicle-speed pulses","sensor"}},{8,{"Lean-angle input","sensor"}},
 {9,{"Fuel-system voltage","sensor"}},{20,{"Sidestand switch","sensor"}},{21,{"Neutral switch","sensor"}},
 {30,{"Ignition coil","actuator"}},{36,{"Injector","actuator"}},{37,{"Variant actuator 37","actuator"}},
 {48,{"Air-induction solenoid","actuator"}},{50,{"Fuel-injection relay","actuator"}},{51,{"Fan relay","actuator"}},
 {52,{"Headlight relay","actuator"}},{57,{"Variant actuator 57","actuator"}},{60,{"EEPROM fault detail","information"}},
 {61,{"Stored fault history","history"}},{62,{"Stored fault count","erase"}},{63,{"Active oxygen-sensor faults","history"}},
 {70,{"Program control number","information"}}};

class NativeMeter {
public:
  std::vector<unsigned> frame,seen;
  unsigned frames=0,entry_polls=0;
  unsigned speed_sum=0,speed_samples=0;
  double speed_kmh=0;
  uint64_t speed_since=0,last_speed_stamp=0;
  Transmission transmission;
  bool speed_ready=false;
  std::deque<std::string> log;
  std::string mode="normal";
  int diag_id=-1,diag_value=-1;
  uint64_t last_request=0,hold_started=0;
  Json holds=Json::array();
  void reset_speed(uint64_t stamp=0){speed_sum=speed_samples=0;speed_kmh=0;speed_ready=false;speed_since=last_speed_stamp=stamp;}
  void accept(const std::vector<unsigned>& f,unsigned request=1,uint64_t stamp=0) {
    require(f.size()==5,"Meter requires five bytes");
    require(((f[0]+f[1]+f[2]+f[3])&255)==f[4],"Meter rejected checksum");
    require(mode!="normal"||!(f[2]&64),"Unexpected diagnostic/authentication status");
    frame=f;++frames;unsigned fault=mode=="normal"?f[2]&63:0;
    // Real B1 pulse deltas, timed at the completed second SCI byte. The fixed
    // serial offset cancels between replies. Eight intervals smooth counts;
    // browser rendering cadence and request cadence do not set speed units.
    if(mode!="normal"||!stamp)reset_speed();
    else if(!speed_since||stamp<=last_speed_stamp||f[1]==255)reset_speed(stamp);
    else {
      speed_sum+=f[1];
      last_speed_stamp=stamp;
      if(++speed_samples==8){speed_kmh=transmission.pulse_speed_kmh(speed_sum,stamp-speed_since);speed_ready=true;speed_sum=speed_samples=0;speed_since=stamp;}
    }
    if(fault&&std::find(seen.begin(),seen.end(),fault)==seen.end())seen.push_back(fault);
    std::string line="TX "+hexbyte(request)+"  →  RX";for(auto b:f)line+=' '+hexbyte(b);
    log.push_back(line);if(log.size()>48)log.pop_front();
    if(mode=="diagnostic") {
      if(f[2]&64){if(diag_id!=int(f[3]))diag_value=-1;diag_id=f[3];}
      else if(diag_id>=0)diag_value=f[3];
    }
  }
  std::vector<unsigned> send(NativeEngine& e,unsigned request) {
    if(last_request&&e.cycles()<last_request+256000)e.until(last_request+256000);
    last_request=e.cycles();auto f=e.exchange(request);accept(f,request,e.speed_reply_cycle);return f;
  }
  void connect(NativeEngine& e,bool diagnostic) {
    e.exchange(0xfe);if(diagnostic){mode="hold-menu";hold_started=0;}else poll(e);
  }
  void poll(NativeEngine& e) {
    if(mode=="hold-menu"||mode=="hold-confirm")require(++entry_polls<=1600,"Diagnostic entry timed out");
    if(mode=="normal"){auto f=e.exchange(1);accept(f,1,e.speed_reply_cycle);}
    else if(mode=="hold-menu") {
      auto f=send(e,0xcd);if(!hold_started)hold_started=e.cycles();
      if((f[2]&64)&&f[3]==0xd0&&e.cycles()-hold_started>=128000000) {
        holds.push_back({{"stage","menu"},{"cycles",e.cycles()-hold_started}});
        send(e,0xca);mode="hold-confirm";hold_started=e.cycles();
      }
    } else if(mode=="hold-confirm") {
      auto f=send(e,0xcd);if((f[2]&64)&&f[3]==1) {
        mode="diagnostic";diag_id=1;
        holds.push_back({{"stage","confirm"},{"cycles",e.cycles()-hold_started}});send(e,0xca);
      }
    } else send(e,0xca);
  }
  void navigate(NativeEngine& e,int direction) {
    require(mode=="diagnostic"&&(direction==-1||direction==1),"Enter diagnostics first");
    send(e,0xca);send(e,direction==1?0xcb:0xcc);diag_id=diag_value=-1;
    for(int n=0;n<9;++n)poll(e);
  }
  Json state(uint64_t cycles=0)const {
    auto info=diagnostic_names.find(diag_id);
    Json s={{"connected",!frame.empty()},{"frames",frames},{"seen",seen},{"log",log},{"mode",mode},
      {"speed_kmh",speed_ready?Json(speed_kmh):Json()},{"speed_mph",speed_ready?Json(speed_kmh/1.609344):Json()},
      {"diagnostic_id",diag_id<0?Json():Json(diag_id)},{"diagnostic_value",diag_value<0?Json():Json(diag_value)},
      {"diagnostic_name",info==diagnostic_names.end()?"Waiting for diagnostic number":info->second.first},
      {"diagnostic_kind",info==diagnostic_names.end()?"information":info->second.second},
      {"entry_seconds",hold_started&&mode!="diagnostic"?rounded(double(cycles-hold_started)/1600000)/10.0:0.0}};
    if(!frame.empty()) {
      unsigned fault=mode=="normal"?frame[2]&63:0;auto name=fault_names.find(fault);
      s.update({{"frame",frame},{"engine_code",frame[0]},{"speed_pulses",frame[1]},{"coolant_code",frame[3]},
        {"warning",bool(frame[2]&128)},{"fault",fault},{"fault_name",!fault?"":name==fault_names.end()?"Unclassified ECU fault":name->second}});
    }
    return s;
  }
};

class NativeCockpit {
public:
  fs::path root;
  std::unique_ptr<NativeEngine> engine;
  Json image;
  std::vector<unsigned char> storage;
  NativeMeter meter;
  EnginePlant plant;
  bool crank_running=false;
  bool trail=false;
  int gear=0,throttle=0,coolant=512,pitch=2800;
  bool run=true,rotating=false,starting=false,reference=false;
  std::string auth="Key off",fault="none";
  uint64_t start_cycle=0,start_firings=0;
  explicit NativeCockpit(fs::path p):root(p){}
  void select(const Json& rec) {
    power(false);if(image.is_null()||image["id"]!=rec["id"])storage.clear();
    image=rec;fault="none";throttle=gear=0;trail=rec["id"]=="xt660-2c1-10"||rec["id"]=="xt660-2c1-10-immo-off"||rec["id"]=="xt660-5vk-11";
  }
  void power(bool enabled,bool wrong_key=false,bool diagnostic=false) {
    if(!enabled) {
      if(engine){storage=engine->storage();engine.reset();}
      meter=NativeMeter();plant=EnginePlant();crank_running=false;rotating=starting=false;auth="Key off";return;
    }
    if(engine)return;require(!image.is_null(),"Select a BIN first");
    engine=std::make_unique<NativeEngine>();engine->reference=reference;
    try {
      engine->load(root,image,storage,(gear?16:0)|2);meter=NativeMeter();engine->config(41,1);
      plant.transmission.trail=meter.transmission.trail=trail;
      plant.last_cycle=engine->cycles();plant.run=run;plant.travel=throttle;plant.select_gear(gear);
      engine->plant_output=[this](unsigned ch,unsigned value,uint64_t cycle){plant.output(ch,value,cycle,engine->hw->pulse_count/11);};
      engine->plant_tick=[this](uint64_t cycle){advance_plant(cycle);};
      inputs();engine->step(200000);auth="Disabled in BIN";
      if(engine->authentication_required){engine->authenticate(wrong_key);auth=wrong_key?"Key rejected":"Key accepted";}
      if(auth!="Key rejected")meter.connect(*engine,diagnostic);
    } catch(...) {engine.reset();throw;}
  }
  void advance_plant(uint64_t cycle) {
    plant.advance(cycle);
    if(meter.mode!="normal")return;
    if(starting&&plant.firings-start_firings>=4&&plant.rpm()>900) {
      starting=false;rotating=true;plant.starter=false;inputs();
    }
    if(starting&&cycle-start_cycle>80000000)stop();
    if(plant.rpm()>=80) {
      int next=std::max(32,rounded(2500000/plant.rpm()));
      if(!crank_running){plant.last_power_cycle=-1;engine->crank(next);crank_running=true;}
      if(next!=pitch){pitch=next;engine->drive(pitch);pressure_input();}
    }else if(crank_running) {
      engine->drive(-1);crank_running=false;rotating=false;pressure_input();
    }
    double frequency=Transmission::wheel_pulses_hz(plant.wheel_omega);
    // Config 36 supports periods up to one nominal second. Below one pulse
    // per second (under 0.13 km/h), the numerical VSS fixture is stopped.
    engine->road(frequency>=1?unsigned(rounded(EnginePlant::clock_hz/frequency)):0);
  }
  void pressure_input() {
    int ambient=512,dip=0;
    if(starting||rotating)dip=rounded(std::clamp(rounded(160.0*1800/pitch),64,224)*(1-.75*throttle/100));
    if(fault=="pressure")ambient=dip=0;
    engine->set_adc(1,ambient);engine->config(39,dip);
  }
  void inputs() {
    if(!engine)return;engine->config(10,(gear?16:0)|(starting?0:2));
    std::array<unsigned,8> v={throttle_adc(throttle),512,512,512,unsigned(meter.mode!="normal"&&!run?0:512),512,unsigned(coolant),512};
    if(fault=="coolant"||fault=="combined")v[6]=1023;
    if(fault=="throttle"||fault=="combined")v[0]=0;
    if(fault=="pressure")v[1]=0;if(fault=="air")v[3]=1023;
    for(unsigned n=0;n<8;++n)engine->set_adc(n,v[n]);
    pressure_input();engine->config(40,meter.mode=="normal"?1:0);
  }
  void control(const std::string& name,const Json& value) {
    if(name=="gear")gear=integer(value,0,5);
    else if(name=="model") {
      require(!engine,"Turn the key off before changing motorcycle");
      require(!image.is_null(),"Select an ECU first");
      std::string model=value.get<std::string>();require(model=="xt660x"||model=="xt660r","Choose XT660X or XT660R");
      require(model=="xt660r"||image["id"]=="xt660-2004-2006-companion"||image["id"]=="xt660-5vk-1x-2008","This BIN is catalogued for XT660R");
      trail=model=="xt660r";
    }
    else if(name=="throttle")throttle=integer(value,0,100);
    else if(name=="coolant")coolant=integer(value,0,1023);
    else if(name=="fault") {
      std::string f=value.get<std::string>();require(f=="none"||f=="coolant"||f=="throttle"||f=="pressure"||f=="air"||f=="combined","Unknown sensor fault");fault=f;
    } else if(name=="run"){run=bool_value(value);if(!run)stop();}
    else throw std::invalid_argument("Unknown control");
    plant.travel=throttle;plant.select_gear(gear);plant.run=run;inputs();
  }
  void stop(){starting=false;plant.starter=false;if(engine)inputs();}
  void start() {
    require(engine&&run,"Turn the key and run switch on first");
    require(meter.mode=="normal","Leave diagnostics before starting");
    require(auth!="Key rejected","The ECU rejected this key");
    if(rotating||starting)return;starting=true;plant.starter=true;plant.run=run;plant.travel=throttle;plant.select_gear(gear);inputs();
    start_cycle=engine->cycles();start_firings=plant.firings;
  }
  void tick() {
    require(bool(engine),"Key is off");
    if(meter.mode!="normal")for(int n=0;n<8;++n)meter.poll(*engine);
    else {engine->step(200000);if(auth!="Key rejected")meter.poll(*engine);}
  }
  void diagnostics(bool enabled){power(false);run=!enabled;power(true,false,enabled);inputs();}
  void diagnostic_next(int direction) {
    require(engine&&meter.mode=="diagnostic","Enter diagnostics first");require(direction==1||direction==-1,"Choose Previous or Next");
    if(run){control("run",false);tick();tick();}meter.navigate(*engine,direction);
  }
  void diagnostic_item(int n) {
    require(n==61||n==62,"Choose history 61 or count 62");require(meter.mode=="diagnostic","Wait for diagnostics");
    for(int i=0;i<24;++i){if(meter.diag_id==n)return;diagnostic_next(-1);}throw std::runtime_error("ECU did not select diagnostic item");
  }
  void diagnostic_test(bool enabled) {
    auto d=diagnostic_names.find(meter.diag_id);
    require(meter.mode=="diagnostic"&&d!=diagnostic_names.end()&&d->second.second=="actuator","Select an actuator diagnostic");
    control("run",false);tick();tick();if(enabled)control("run",true);
  }
  void clear_history() {
    require(meter.mode=="diagnostic"&&meter.diag_id==62,"Select d:62 first");
    for(bool r:{false,true}){control("run",r);for(int n=0;n<4;++n)tick();}
  }
  Json state()const {
    Json faults=Json::array();
    for(auto f:std::vector<std::pair<std::string,std::string>>{{"none","Healthy sensors"},{"coolant","Coolant disconnected"},
      {"throttle","Throttle circuit low"},{"pressure","Intake pressure circuit low"},{"air","Intake temperature disconnected"},{"combined","Coolant + throttle faults"}})
      faults.push_back({{"id",f.first},{"label",f.second}});
    return {{"selected",image.is_null()?Json():image["id"]},{"powered",bool(engine)},{"gear",gear},{"throttle",throttle},
      {"model",trail?"xt660r":"xt660x"},{"models",image.is_null()||image["id"]=="xt660-2004-2006-companion"||image["id"]=="xt660-5vk-1x-2008"?Json({"xt660x","xt660r"}):Json({"xt660r"})},
      {"coolant",coolant},{"run",run},{"starting",starting},{"rotating",rotating},{"authentication",auth},{"fault",fault},
      {"faults",faults},{"plant",{{"rpm",plant.rpm()},{"crank_revolutions",plant.angle/(2*EnginePlant::pi)},
      {"combustions",plant.firings},{"sparks",plant.sparks},{"injections",plant.injections},{"injection_ms",plant.last_injection_ms},
      {"inertia_kg_m2",plant.inertia()},{"road_kmh",plant.wheel_omega*plant.transmission.wheel_radius()*3.6},
      {"vss_pulses_hz",Transmission::wheel_pulses_hz(plant.wheel_omega)},{"tyre_circumference_mm",trail?2010:1959.7},
      {"vss_pulses_per_shaft_turn",Transmission::pulses_per_shaft_turn},{"fixture",true}}},{"meter",meter.state(engine?engine->cycles():0)}};
  }
};
