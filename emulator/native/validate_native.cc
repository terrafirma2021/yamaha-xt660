// SPDX-License-Identifier: GPL-2.0-or-later
// Headless checks; the browser is absent throughout this executable.
#include "cockpit_native.hpp"
#include <iostream>
#include <set>

Json checkpoint(NativeCockpit& b) {
  auto& e=*b.engine;std::vector<unsigned char> ram(2048),regs(512);
  for(unsigned i=0;i<2048;++i)ram[i]=e.byte(0x800+i);
  for(unsigned i=0;i<512;++i)regs[i]=e.byte(i);
  e.verify();return {{"cycles",e.cycles()},{"pc",e.cpu->PC},{"ram",sha256(ram)},{"registers",sha256(regs)},
    {"storage",sha256(e.storage())},{"event_signature",e.event_signature},{"event_count",e.event_count},
    {"outputs",e.outputs},{"meter",b.meter.frame},{"auth",b.auth},{"rotating",b.rotating},{"starting",b.starting},
    {"synchronized",e.snapshot()["synchronized"]}};
}
template<class F> void until(NativeCockpit& b,F condition,int limit) {
  while(!condition()&&limit-->0)b.tick();require(condition(),"Firmware condition not reached");
}
void check_plant_math() {
  EnginePlant p;p.omega=200;p.last_cycle=1;
  auto initial=p.rpm();p.advance(16001);
  require(p.rpm()>0&&p.rpm()<initial,"Inertia must coast, not freeze or stop instantly");
  p.output(3,1,16002,1);p.output(3,0,32002,1);
  require(p.firings==0,"Spark alone produced combustion");
  p.output(6,1,33002,1);p.output(6,0,34002,1);
  require(p.injections==0,"Injector idle-high was treated as a pulse");
  p.output(6,1,50002,1);require(p.injections==1&&p.last_injection_ms==1,"Active-low injector duration");
  p.output(3,1,51002,3);p.output(3,0,52002,3);
  require(p.firings==1,"Completed fuel pulse and coil release did not ignite");
  p.output(3,1,53002,4);p.output(3,0,54002,4);
  require(p.firings==1,"Wasted spark incorrectly produced another power stroke");
  p.output(3,1,55002,5);p.output(3,0,56002,5);
  require(p.firings==1,"Consumed fuel pulse was reused");
  require(std::abs(EnginePlant::envelope(5250)-58.4)<1e-9,"Yamaha torque anchor");
  require(std::abs(EnginePlant::envelope(6000)*6000*2*EnginePlant::pi/60-35300)<1e-6,"Yamaha power anchor");
}
Json check_dynamics(NativeCockpit& b) {
  Json modes=Json::array();
  for(int gear:{0,1}) {
    b.power(false);b.control("run",true);b.control("gear",0);b.control("throttle",0);b.power(true);b.start();
    until(b,[&]{return b.rotating;},100);
    auto idle=b.engine->cycles();while(b.engine->cycles()-idle<48000000)b.tick();
    double idle_min=1e9,idle_max=0;
    for(int n=0;n<12;++n){b.tick();idle_min=std::min(idle_min,b.plant.rpm());idle_max=std::max(idle_max,b.plant.rpm());}
    require(idle_min>700&&idle_max<2200&&idle_max-idle_min>1,"Idle must retain power-stroke ripple");
    b.control("gear",gear);b.control("throttle",100);auto begin=b.engine->cycles();
    auto advance=b.engine->plant_tick;
    unsigned previous=0,entries=0,resumes=0;uint64_t first_cut=0,cut_begin=0;
    uint64_t gap_sparks=0,gap_fuel=0,longest_cut=0;bool coast_during_cut=false;
    double peak=0,cut_rpm=0;
    b.engine->plant_tick=[&](uint64_t c) {
      advance(c);peak=std::max(peak,b.plant.rpm());unsigned mask=b.engine->byte(0x88c)&10;
      if(mask==10&&previous!=10) {
        ++entries;if(!first_cut)first_cut=c;cut_begin=c;cut_rpm=b.plant.rpm();
      }
      if(first_cut){gap_sparks=std::max(gap_sparks,c-b.plant.last_spark);gap_fuel=std::max(gap_fuel,c-b.plant.last_fuel);}
      if(mask==0&&previous==10) {
        ++resumes;longest_cut=std::max(longest_cut,c-cut_begin);
        if(b.plant.rpm()<cut_rpm-10)coast_during_cut=true;
      }
      previous=mask;
    };
    while(b.engine->cycles()-begin<128000000) {
      b.tick();require(b.rotating&&b.meter.state()["fault"]==0,"WOT engine stopped or faulted");
    }
    b.engine->plant_tick=advance;
    require(entries>=3&&resumes>=3&&coast_during_cut&&peak>7000&&peak<8500,"Original ECU did not govern the limiter cycle");
    require(longest_cut>160000,"Cut did not persist across combustion opportunities");
    require(gap_sparks>480000&&gap_fuel>480000,"Cut flags did not interrupt actual spark and injector pulses");
    double before=b.plant.rpm();b.control("throttle",0);auto coast=b.engine->cycles();b.tick();
    // A power stroke already in progress can finish after closing the throttle.
    require(b.plant.rpm()>500&&std::abs(b.plant.rpm()-before)<500,"Throttle release must preserve crank inertia");
    while(b.engine->cycles()-coast<32000000)b.tick();
    require(b.plant.rpm()<before-500,"Closed throttle did not decelerate");
    b.control("run",false);auto stop=b.engine->cycles();b.tick();
    require(b.plant.rpm()>0,"Run switch froze the crank");
    while(b.engine->cycles()-stop<480000000&&b.plant.rpm()>0)b.tick();
    require(b.plant.rpm()==0&&!b.rotating,"Stopped engine kept turning: "+std::to_string(b.plant.rpm()));b.engine->verify();
    require(b.engine->adc[4]==614,"Stopped engine retained charging voltage");
    modes.push_back({{"gear",gear},{"idle_min_rpm",idle_min},{"idle_max_rpm",idle_max},{"peak_rpm",peak},
      {"first_cut_seconds",double(first_cut-begin)/16000000},{"cut_entries",entries},{"cut_resumes",resumes},
      {"longest_cut_ms",double(longest_cut)/16000},{"longest_spark_gap_ms",double(gap_sparks)/16000},
      {"longest_injection_gap_ms",double(gap_fuel)/16000},{"coasts_during_cut",coast_during_cut},{"flash_unchanged",true}});
  }
  require(modes[1]["first_cut_seconds"].get<double>()>modes[0]["first_cut_seconds"].get<double>(),"Load did not slow acceleration");
  b.power(false);return modes;
}
void check_meter_display() {
  auto reply=[](unsigned p){return std::vector<unsigned>{0,p,0,57,(p+57)&255};};
  NativeMeter m;uint64_t stamp=1000;m.accept(reply(0),1,stamp);
  auto sample=[&](unsigned count,unsigned interval=800000){stamp+=interval;m.accept(reply(count),1,stamp);};
  for(int i=0;i<7;++i)sample(5);
  require(m.state()["speed_mph"].is_null(),"Speed needs eight timed intervals");
  auto before=m.state();for(int i=0;i<30;++i)require(m.state()==before,"Snapshot changed speed window");
  auto invalid=reply(5);invalid[4]^=1;
  bool rejected=false;try{m.accept(invalid,1,stamp+800000);}catch(const std::invalid_argument&){rejected=true;}
  require(rejected&&m.state()==before,"Bad checksum changed speed window");
  sample(5);require(std::abs(m.speed_kmh-11.7582)<1e-9,"100 pulses/sec X tyre conversion");
  require(std::abs(m.state()["speed_mph"].get<double>()-11.7582/1.609344)<1e-9,"MPH conversion");
  for(int i=0;i<8;++i)sample(i%2?3:2,400000);
  require(std::abs(m.speed_kmh-11.7582)<1e-9,"Reply cadence changed speed");
  for(int i=0;i<8;++i)sample(0);
  require(m.state()["speed_mph"]==0,"Stopped speed did not become zero");
  sample(255);require(m.state()["speed_mph"].is_null(),"Saturated count treated as a complete measurement");
  m.mode="diagnostic";sample(5);require(m.state()["speed_mph"].is_null(),"Diagnostic byte counted as speed");
  m.mode="normal";m.transmission.trail=true;sample(0);for(int i=0;i<8;++i)sample(5);
  require(std::abs(m.speed_kmh-12.06)<1e-9,"100 pulses/sec R tyre conversion");
  m=NativeMeter();require(m.state()["speed_mph"].is_null(),"Key cycle retained speed");
}
void check_gearing_math() {
  Transmission t;
  for(int model=0;model<2;++model) {
    t.trail=model;std::array<double,5> expected=model?std::array<double,5>{56.3,86.7,122.5,154.9,183.1}:std::array<double,5>{54.9,84.5,119.4,151.1,178.5};
    for(int g=1;g<=5;++g)require(std::abs(t.kmh(7300,g)-expected[g-1])<.06,"Gearing Commander stock speed mismatch");
  }
  require(std::abs(Transmission::shaft_pulses_hz(7300,1)-467.2)<1e-9,"First gear VSS frequency");
  require(std::abs(Transmission::shaft_pulses_hz(7300,5)-1518.4)<1e-9,"Fifth gear VSS frequency");
  EnginePlant p;p.omega=6000*2*EnginePlant::pi/60;p.select_gear(1);
  auto wheel=p.wheel_omega;p.select_gear(2);
  require(std::abs(p.rpm()-3900)<1e-9&&std::abs(p.wheel_omega-wheel)<1e-9,"Upshift did not preserve road speed");
  p.select_gear(1);require(std::abs(p.rpm()-6000)<1e-9,"Downshift RPM ratio");
  p.select_gear(0);p.last_cycle=1;p.advance(160001);
  require(p.wheel_omega>0&&p.wheel_omega<wheel,"Neutral should coast independently");
}
Json check_gearing(NativeCockpit& b) {
  Json results=Json::array();auto models=b.state()["models"];
  for(auto model:models) {
    b.power(false);b.control("model",model);b.control("gear",0);b.control("run",true);b.power(true);
    auto& e=*b.engine;
    // A fixed-speed external crank bench isolates the pulse/count/serial path.
    // No ECU RAM, flash, return values or reported speed are substituted.
    e.plant_tick=nullptr;e.config(39,160);e.crank(417);
    double rpm=2500000.0/417;Transmission t;t.trail=model=="xt660r";
    for(int gear=1;gear<=5;++gear) {
      b.control("gear",gear);e.config(39,160);
      auto period=unsigned(rounded(16000000/Transmission::shaft_pulses_hz(rpm,gear)));e.road(period);
      for(int i=0;i<24;++i)b.tick();
      double expected=t.kmh(rpm,gear);
      require(b.meter.speed_ready&&std::abs(b.meter.speed_kmh-expected)<1.0,"Actual VSS/K-line speed does not match gearing");
      require(e.hw->gpio(1)&16,"An engaged gear asserted neutral");e.verify();
      results.push_back({{"model",model},{"gear",gear},{"nominal_rpm",rpm},{"expected_kmh",expected},
        {"received_kmh",b.meter.speed_kmh},{"pulse_period_cycles",period},{"last_frame",b.meter.frame},{"flash_unchanged",true}});
    }
    b.control("gear",0);require(!(e.hw->gpio(1)&16),"Neutral input did not assert");
    for(int i=0;i<12;++i)b.tick();require(b.meter.speed_kmh>0,"Neutral discarded actual road pulses");
    e.road(0);for(int i=0;i<18;++i)b.tick();require(b.meter.speed_kmh==0,"Stopped road input retained speed");
    b.power(false);
  }
  return results;
}

int main(int argc,char**argv){try {
  check_meter_display();
  check_plant_math();
  check_gearing_math();
  require(argc>=3,"Usage: validate.exe ROOT report.json [reference] [full]");
  fs::path root=argv[1];bool reference=argc>3&&std::string(argv[3])=="reference",full=argc>4;
  auto registry=Json::parse(read_bytes(root/"firmware/registry.json"));Json results=Json::array();
  for(const auto& row:registry["images"]) {
    auto data=read_bytes(root/row["file"].get<std::string>());
    if(data[data.size()-2]!=0xf8||data.back()!=0)continue;
    NativeCockpit b(root);b.reference=reference;b.select(row);Json checkpoints=Json::array();
    auto start=Clock::now();b.power(true);double key=std::chrono::duration<double>(Clock::now()-start).count();
    require(b.engine->adc[4]==614,"Key-on supply must be the 12 V fixture");
    unsigned supply_address=b.engine->early?0xbce:0xbf0;
    require(b.engine->byte(supply_address)==153,"Firmware did not sample the stopped supply");
    Json supply={{"stopped_adc10",b.engine->adc[4]},{"stopped_firmware_high",b.engine->byte(supply_address)}};
    checkpoints.push_back(checkpoint(b));auto key_cycles=b.engine->cycles();b.start();require(b.engine->cycles()==key_cycles,"Starter command advanced CPU");
    require(b.starting&&!b.rotating&&b.engine->adc[4]==614,"Cranking must retain battery voltage");
    until(b,[&]{return b.rotating;},100);checkpoints.push_back(checkpoint(b));
    require(b.engine->adc[4]==737,"Running supply must be the 14.4 V fixture");
    Json performance=Json::array();
    for(int t:{0,100,0}) {
      b.control("throttle",t);b.control("gear",t?1:0);start=Clock::now();auto cycles=b.engine->cycles();
      for(int n=0;n<40;++n){b.tick();require(b.rotating&&b.meter.state()["fault"]==0,"Healthy engine stopped or reported a fault");}
      require(b.engine->adc[4]==737&&b.engine->byte(supply_address)==184,"Firmware did not sample charging voltage");
      double wall=std::chrono::duration<double>(Clock::now()-start).count(),sim=double(b.engine->cycles()-cycles)/16000000;
      performance.push_back({{"throttle",t},{"wall_seconds",wall},{"simulated_seconds",sim},{"unpaced_ratio",sim/wall}});
      checkpoints.push_back(checkpoint(b));
    }
    supply.update({{"running_adc10",b.engine->adc[4]},{"running_firmware_high",b.engine->byte(supply_address)}});
    b.control("run",false);b.tick();checkpoints.push_back(checkpoint(b));
    require(b.engine->adc[4]==614,"Run-off must restore battery voltage");
    supply["run_off_adc10"]=b.engine->adc[4];
    Json r={{"image",row["id"]},{"sha256",row["sha256"]},{"key_seconds",key},{"performance",performance},{"checkpoints",checkpoints},{"supply",supply}};
    if(b.engine->authentication_required) {
      b.power(false);b.power(true,true);require(b.auth=="Key rejected","Bad key accepted");
      bool rejected=false;try{b.start();}catch(const std::invalid_argument&){rejected=true;}require(rejected,"Bad key permitted starter");
      r["bad_key"]=checkpoint(b);
    }
    b.power(false);
    if(full){r["dynamics"]=check_dynamics(b);r["gearing"]=check_gearing(b);}
    // End-to-end TPS: physical-input fixture -> original ADC/diagnostic code
    // -> checked K-line reply. No forced RAM or dashboard percentage mapping.
    b.diagnostics(true);until(b,[&]{return b.meter.mode=="diagnostic";},240);
    require(b.meter.diag_id==1,"TPS diagnostic item missing");
    Json tps=Json::array();
    for(auto point:std::array<std::array<int,3>,7>{{{0,64,16},{25,148,37},{50,232,58},{75,316,79},{100,400,100},{50,232,58},{0,64,16}}}) {
      b.control("throttle",point[0]);for(int n=0;n<3;++n)b.tick();
      require(b.engine->adc[0]==unsigned(point[1])&&b.meter.diag_value==point[2],"TPS input / serial diagnostic mismatch");
      tps.push_back({{"travel",point[0]},{"adc",b.engine->adc[0]},{"reply",b.meter.frame}});
    }
    b.control("fault","throttle");for(int n=0;n<3;++n)b.tick();
    require(b.meter.diag_value==0,"TPS fault was hidden by nominal fixture scaling");
    b.control("fault","none");for(int n=0;n<3;++n)b.tick();
    require(b.meter.diag_value==16,"TPS did not restore closed input after fault");
    b.engine->verify();r["tps"]=tps;r["tps_fault_reply"]=0;b.power(false);
    if(full&&(row["id"]=="xt660-2004-2006-companion"||row["id"]=="xt660-2c1-10"||row["id"]=="xt660-2c1-10-immo-off")) {
      b.run=true;b.power(true);b.control("fault","combined");
      until(b,[&]{auto& s=b.meter.seen;return std::find(s.begin(),s.end(),15)!=s.end()&&std::find(s.begin(),s.end(),21)!=s.end();},200);
      r["active_faults"]=b.meter.seen;b.control("fault","none");until(b,[&]{return b.meter.state()["fault"]==0;},160);
      for(int n=0;n<6;++n)b.tick();auto before=b.engine->storage();b.diagnostics(true);
      until(b,[&]{return b.meter.mode=="diagnostic";},240);
      require(b.meter.holds.at(0).at("cycles").get<uint64_t>()>=128000000&&b.meter.holds.at(1).at("cycles").get<uint64_t>()>=32000000,"Diagnostic hold too short");
      r["holds"]=b.meter.holds;
      std::vector<int> menu={1,3,5,6,7,8,9,20,21,30,36,48,50,51,52,60,61,62};if(!b.engine->early)menu.push_back(63);menu.push_back(70);
      for(int n:menu){require(b.meter.diag_id==n,"Wrong diagnostic menu order");b.diagnostic_next(1);}
      require(b.meter.diag_id==1,"Menu did not wrap");for(auto it=menu.rbegin();it!=menu.rend();++it){b.diagnostic_next(-1);require(b.meter.diag_id==*it,"Wrong reverse diagnostic order");}
      r["menu"]=menu;b.diagnostic_item(61);std::set<int> history;
      until(b,[&]{if(b.meter.diag_value>0)history.insert(b.meter.diag_value);return history.count(15)&&history.count(21);},400);
      r["history"]=history;b.diagnostic_item(62);require(b.meter.diag_value>=2,"Stored fault count missing");b.clear_history();
      until(b,[&]{return b.meter.diag_value==0;},80);for(int n=0;n<6;++n)b.tick();auto after=b.engine->storage();
      require(before!=after&&std::all_of(after.begin()+0x24,after.begin()+0x28,[](int x){return x==0;}),"EEPROM history did not clear");
      r["cleared_history"]=checkpoint(b);
      while(b.meter.diag_id!=30)b.diagnostic_next(1);
      b.diagnostic_test(true);auto cycles=b.engine->cycles();std::map<uint64_t,unsigned> edges;unsigned warning=0;
      while(b.engine->cycles()-cycles<96000000) {
        b.engine->step(1000000);b.meter.poll(*b.engine);warning+=b.meter.state()["warning"].get<bool>();
        for(const auto& e:b.engine->trace)if(e.cycle>cycles&&e.kind=="output"&&e.channel==3)edges[e.cycle]=e.value;
      }
      std::vector<uint64_t> rises,falls;for(auto e:edges)(e.second?rises:falls).push_back(e.first);
      require(rises.size()==5&&falls.size()==5&&warning,"Coil diagnostic pulse count/warning incorrect");
      for(unsigned i=1;i<rises.size();++i)require(std::abs(double(rises[i]-rises[i-1])/16000000-1)<.02,"Coil diagnostic timing incorrect");
      r["coil_test"]=checkpoint(b);r["coil_rises"]=rises;r["coil_falls"]=falls;
      b.diagnostic_test(false);b.diagnostics(false);require(b.meter.mode=="normal"&&b.meter.frames>0,"Normal mode reconnect failed");
      r["normal_after_diag"]=checkpoint(b);b.power(false);
    }
    results.push_back(r);std::cout<<"PASS "<<row["id"]<<std::endl;
  }
  require(results.size()==5,"Expected five complete images");
  std::ofstream out(argv[2]);out<<Json({{"reference",reference},{"full",full},{"images",results}}).dump(2)<<'\n';return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 1;}}
