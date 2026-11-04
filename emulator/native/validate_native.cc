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
void check_meter_display() {
  auto reply=[](unsigned p){return std::vector<unsigned>{0,p,0,57,(p+57)&255};};
  NativeMeter m;
  for(int i=0;i<7;++i)m.accept(reply(5));
  require(m.state()["speed_mph"].is_null(),"Speed needs eight replies");
  auto before=m.state();
  for(int i=0;i<30;++i)require(m.state()==before,"Snapshot changed speed window");
  auto invalid=reply(5);invalid[4]^=1;
  bool rejected=false;try{m.accept(invalid);}catch(const std::invalid_argument&){rejected=true;}
  require(rejected&&m.state()==before,"Bad checksum changed speed window");
  m.accept(reply(5));
  require(m.state()["speed_kmh"]==40&&std::abs(m.state()["speed_mph"].get<double>()-24.85484768949336)<1e-10,"Logger km/h to MPH conversion");
  for(int i=0;i<7;++i){m.accept(reply(0));require(m.state()["speed_kmh"]==40,"Speed did not hold completed window");}
  m.accept(reply(0));require(m.state()["speed_mph"]==0,"Stopped speed did not become zero");
  for(int i=0;i<8;++i)m.accept(reply(255));
  require(m.state()["speed_kmh"]==2040,"Speed accumulator wrapped");
  m.mode="diagnostic";m.accept(reply(255));
  require(m.state()["speed_mph"].is_null(),"Diagnostic bytes counted as speed");
  m.mode="normal";for(int i=0;i<8;++i)m.accept(reply(5));
  require(m.state()["speed_kmh"]==40,"Diagnostic exit retained stale pulses");
  m=NativeMeter();require(m.state()["speed_mph"].is_null(),"Key-cycle reset retained speed");
}
int main(int argc,char**argv){try {
  check_meter_display();
  require(argc>=3,"Usage: validate.exe ROOT report.json [reference] [full]");
  fs::path root=argv[1];bool reference=argc>3&&std::string(argv[3])=="reference",full=argc>4;
  auto registry=Json::parse(read_bytes(root/"firmware/registry.json"));Json results=Json::array();
  for(const auto& row:registry["images"]) {
    auto data=read_bytes(root/row["file"].get<std::string>());
    if(data[data.size()-2]!=0xf8||data.back()!=0)continue;
    NativeCockpit b(root);b.reference=reference;b.select(row);Json checkpoints=Json::array();
    auto start=Clock::now();b.power(true);double key=std::chrono::duration<double>(Clock::now()-start).count();
    checkpoints.push_back(checkpoint(b));auto key_cycles=b.engine->cycles();b.start();require(b.engine->cycles()==key_cycles,"Starter command advanced CPU");
    until(b,[&]{return b.rotating;},16);checkpoints.push_back(checkpoint(b));
    Json performance=Json::array();
    for(int t:{0,100,0}) {
      b.control("throttle",t);b.control("gear",t?1:0);start=Clock::now();auto cycles=b.engine->cycles();
      for(int n=0;n<40;++n){b.tick();require(b.rotating&&b.meter.state()["fault"]==0,"Healthy engine stopped or reported a fault");}
      double wall=std::chrono::duration<double>(Clock::now()-start).count(),sim=double(b.engine->cycles()-cycles)/16000000;
      performance.push_back({{"throttle",t},{"wall_seconds",wall},{"simulated_seconds",sim},{"unpaced_ratio",sim/wall}});
      checkpoints.push_back(checkpoint(b));
    }
    b.control("run",false);b.tick();checkpoints.push_back(checkpoint(b));
    Json r={{"image",row["id"]},{"sha256",row["sha256"]},{"key_seconds",key},{"performance",performance},{"checkpoints",checkpoints}};
    if(b.engine->authentication_required) {
      b.power(false);b.power(true,true);require(b.auth=="Key rejected","Bad key accepted");
      bool rejected=false;try{b.start();}catch(const std::invalid_argument&){rejected=true;}require(rejected,"Bad key permitted starter");
      r["bad_key"]=checkpoint(b);
    }
    b.power(false);
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
