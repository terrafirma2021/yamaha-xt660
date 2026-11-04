// SPDX-License-Identifier: GPL-2.0-or-later
// Direct, in-process adapter for the existing patched HC12 core.
#pragma once
#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <bcrypt.h>
#include <array>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <vector>
#include "json.hpp"
#define XT660_EMBEDDED
#include "xt660_boot.cc"
using Json=nlohmann::json;
using Clock=std::chrono::steady_clock;
namespace fs=std::filesystem;
inline std::vector<unsigned char> read_bytes(const fs::path &p) {
  std::ifstream f(p,std::ios::binary); if(!f)throw std::runtime_error("Cannot read "+p.string());
  return {std::istreambuf_iterator<char>(f),std::istreambuf_iterator<char>()};
}
inline std::string sha256(const std::vector<unsigned char>& data) {
  unsigned char digest[32];
  if(BCryptHash(BCRYPT_SHA256_ALG_HANDLE,NULL,0,const_cast<PUCHAR>(data.data()),ULONG(data.size()),digest,32)<0)
    throw std::runtime_error("SHA-256 failed");
  std::ostringstream out;out<<std::hex<<std::setfill('0');for(auto c:digest)out<<std::setw(2)<<unsigned(c);return out.str();
}
inline std::string hexbyte(unsigned value) { std::ostringstream out;out<<std::uppercase<<std::hex<<std::setfill('0')<<std::setw(2)<<value;return out.str(); }
struct Event { std::string kind;unsigned channel,value;uint64_t cycle;unsigned pc; };
class NativeEngine {
public:
  xt_cpu *cpu=nullptr;xt_boot_hw *hw=nullptr;
  std::array<unsigned char,65536> original{};
  std::array<unsigned,8> adc{};
  std::deque<Event> trace;
  std::deque<unsigned> tx[2];
  std::array<uint64_t,8> outputs{};
  uint64_t last_coil=0,last_fuel=0;
  uint64_t event_signature=14695981039346656037ull,event_count=0;
  Json record,storage_origin,transcript=Json::array();
  bool early=false,authentication_required=true,reference=false;
  unsigned loop=0,pitch=1600;
  NativeEngine() {
    app_start_at=dnow();cpus=cpus_m68hc12;
    application=new xt_app();application->set_name("XT660_Emulator");
    char a0[]="XT660.Emulator",a1[]="-q",a2[]="-R",a3[]="0",a4[]="-c",a5[]="NUL";
    char* args[]={a0,a1,a2,a3,a4,a5};application->init(6,args);
    cl_sim *sim=new xt_sim(application);if(sim->init())throw std::runtime_error("HC12 initialization failed");
    application->set_simulator(sim);cpu=static_cast<xt_cpu*>(sim->uc);hw=cpu->device;
    hw->event_sink=[this](const char*k,unsigned ch,unsigned v,uint64_t c,unsigned pc) {
      auto hash=[&](uint64_t n){for(unsigned i=0;i<8;++i){event_signature^=(n>>(i*8))&255;event_signature*=1099511628211ull;}};
      for(const char* p=k;*p;++p)hash(static_cast<unsigned char>(*p));hash(ch);hash(v);hash(c);hash(pc);++event_count;
      if(std::string(k)=="serial_tx")tx[ch].push_back(v);
      if(std::string(k)=="output") { ++outputs[ch]; if(ch==3)last_coil=c;if(ch==6)last_fuel=c; }
      trace.push_back({k,ch,v,c,pc});if(trace.size()>10000)trace.pop_front();
    };
  }
  ~NativeEngine() { if(application){application->done();delete application;application=nullptr;} }
  uint64_t cycles()const{return hw->bus_cycles;}
  unsigned byte(unsigned a)const{return cpu->rom->get(a);}
  unsigned word(unsigned a)const{return byte(a)*256+byte(a+1);}
  void config(unsigned n,unsigned value){hw->cfg_write(n,value);}
  void step(unsigned count) {
    for(unsigned n=0;n<count;++n) {
      int result=cpu->run_instruction();
      if(hw->fault || (result!=resGO && result!=resNOT_DONE))throw std::runtime_error("MCU stopped at "+std::to_string(cpu->PC)+", result "+std::to_string(result));
    }
  }
  void until(uint64_t deadline) { while(cycles()<deadline)step(std::max(1u,unsigned(std::min<uint64_t>(10000,(deadline-cycles())/4)))); }
  void reach(unsigned pc,unsigned hits=1,unsigned budget=2000000) {
    while(budget--) { if(cpu->PC==pc && !--hits)return;step(1); }
    throw std::runtime_error("Firmware did not reach reviewed entry");
  }
  void reset_image() {
    for(unsigned a=0x200;a<0x1800;++a)cpu->rom->set(a,original[a]);
    for(unsigned a=0x1800;a<65536;++a)cpu->rom->set(a,original[a]);
    cpu->reset();hw->reference_ticks=reference;
    trace.clear();tx[0].clear();tx[1].clear();outputs.fill(0);last_coil=last_fuel=0;
    event_signature=14695981039346656037ull;event_count=0;
  }
  std::vector<unsigned char> storage()const {std::vector<unsigned char>b(512);for(unsigned i=0;i<512;++i)b[i]=hw->eeprom->get(i);return b;}
  void load(const fs::path &root,const Json &rec,const std::vector<unsigned char>& saved={},unsigned port_b=2) {
    record=rec;auto bytes=read_bytes(root/rec.at("file").get<std::string>());
    if(sha256(bytes)!=rec.at("sha256"))throw std::runtime_error("BIN hash mismatch");
    unsigned base=rec.at("base_address");if(base+bytes.size()!=65536)throw std::runtime_error("Invalid BIN extent");
    original.fill(0);std::copy(bytes.begin(),bytes.end(),original.begin()+base);
    if(original[65534]!=0xf8||original[65535]!=0||original[0xf7a0]!=6)throw std::runtime_error("Missing or unreviewed boot code");
    unsigned entry=original[0xf7a1]*256+original[0xf7a2];if(entry!=0x5000&&entry!=0x4800)throw std::runtime_error("Unreviewed application entry");
    early=entry==0x5000;loop=early?0x538b:0x4bc5;
    unsigned auth=original[early?0x4e7d:0x4619];if(auth!=0&&auth!=128)throw std::runtime_error("Unreviewed authentication option");authentication_required=!auth;
    std::vector<unsigned char> defaults=saved;
    if(defaults.empty()) {
      std::vector<unsigned char> expected;
      const std::vector<unsigned> calls=early?std::vector<unsigned>{0x5857,0x5a13,0x5c05,0x5d4d,0x5d77}:std::vector<unsigned>{0x502d,0x5114,0x5309,0x5454,0x5481};
      for(auto a:calls){expected.push_back(0x16);expected.push_back(a>>8);expected.push_back(a&255);}
      unsigned end=early?0x5854:0x502a;
      expected.insert(expected.end(),{0x14,0x10,0x06,static_cast<unsigned char>(end>>8),static_cast<unsigned char>(end)});
      if(!std::equal(expected.begin(),expected.end(),original.begin()+(early?0x5843:0x5019)))throw std::runtime_error("Unreviewed storage initializer");
      reset_image();for(unsigned a=0x800;a<0x1000;++a)cpu->rom->set(a,0);
      config(18,2);config(13,16);cpu->rom->write(0xda,3);cpu->SP=0xff0;cpu->CC.cc16.cc8.ccl=0xd0;
      cpu->PC=early?0x5843:0x5019;reach(early?0x5854:0x502a,1,1000000);defaults=storage();
      if(sha256(defaults)!="93f11ba1d85ba762b87ee17ba9e9434e1bb8c81d6df23b238892f94f77fb68f6")throw std::runtime_error("Firmware storage initializer differs from reference");
      storage_origin={{"origin","Firmware default-writing routine; not a physical ECU EEPROM dump"},{"sha256",sha256(defaults)}};
    } else storage_origin={{"origin","Retained external storage fixture"}};
    if(defaults.size()!=512)throw std::runtime_error("Storage fixture must contain 512 bytes");
    reset_image();config(18,2);
    const unsigned char registration[]={65,66,67,65,66,67,65,66,67,90,165};std::copy(std::begin(registration),std::end(registration),defaults.begin()+0x50);
    for(unsigned a=0;a<512;++a)hw->eeprom->set(a,defaults[a]);
    config(9,224);config(13,16);config(10,port_b);reach(loop,1000);
    config(25,1);adc.fill(512);transcript=Json::array();
  }
  void set_adc(unsigned n,unsigned v){if(n>7||v>1023)throw std::runtime_error("ADC range");config(n+1,v);adc[n]=v;}
  void drive(int p,bool road=false){if(p<0){config(24,0);config(37,0);config(35,0);config(36,0);return;}config(35,p*32);config(36,road?p*32*3:0);pitch=p;}
  void crank(unsigned p=2800){config(24,0);config(19,p*32);config(20,p*16);config(21,11);config(22,2);config(23,4092);config(24,1);config(37,1);pitch=p;}
  std::vector<unsigned> exchange(unsigned request,unsigned channel=1,unsigned count=5) {
    step(10000);tx[channel].clear();config(26+channel,request);
    unsigned budget=500000;while(tx[channel].size()<count&&budget){step(25000);budget-=25000;}
    std::vector<unsigned> frame(tx[channel].begin(),tx[channel].end());tx[channel].clear();
    std::string reply;for(auto b:frame){if(!reply.empty())reply+=' ';reply+=hexbyte(b);}
    transcript.push_back({{"channel",channel},{"request",hexbyte(request)},{"reply",reply}});if(transcript.size()>256)transcript.erase(transcript.begin());
    if(frame.size()!=count)throw std::runtime_error("Serial reply length mismatch");
    if(channel==1&&count==5&&((frame[0]+frame[1]+frame[2]+frame[3])&255)!=frame[4])throw std::runtime_error("Serial reply checksum mismatch");
    return frame;
  }
  void authenticate(bool corrupt) {
    if(!authentication_required)throw std::runtime_error("Authentication is disabled in this BIN");
    auto challenge=exchange(0x3e);if(challenge[2]!=0x43||exchange(0x3d)[2]!=0x4b)throw std::runtime_error("Authentication exchange differs");
    unsigned a=challenge[0],b=challenge[1],c=challenge[3],response=a*b+b*c+c*a;if(corrupt)response^=1;
    for(int shift:{12,6,0})if(exchange(0x80|((response>>shift)&63))!=std::vector<unsigned>({0x47,0x47,0x47,0x47,0x1c}))throw std::runtime_error("Authentication challenge rejected");
    for(unsigned n=0;n<(corrupt?1u:4u);++n)if(exchange(0x3f)!=(corrupt?std::vector<unsigned>{70,70,70,70,24}:std::vector<unsigned>{69,69,69,69,20}))throw std::runtime_error("Authentication response differs");
  }
  void verify()const{for(unsigned a=0x1800;a<65536;++a)if(byte(a)!=original[a])throw std::runtime_error("Flash differs from registered BIN");}
  Json snapshot()const {
    Json faults=Json::array(),events=Json::array();
    for(unsigned a=early?0x8af:0x8b1;a<(early?0x8b3:0x8b5);++a)faults.push_back(byte(a));
    for(auto i=trace.size()>600?trace.end()-600:trace.begin();i!=trace.end();++i)
      events.push_back({{"kind",i->kind},{"channel",i->channel},{"value",i->value},{"cycle",i->cycle},{"pc",i->pc}});
    Json counts={{"bus_cycles",cycles()},{"fault",hw->fault},{"adc_conversions",hw->adc_conversions},{"irq_count",hw->irq_count},{"timer_edges",hw->timer_edges},{"timer_matches",hw->timer_matches},{"cop_services",hw->cop_services}};
    return {{"image",record["id"]},{"adc",adc},{"counts",counts},{"crank_pitch",pitch},{"authentication_required",authentication_required},
      {"synchronized",bool(byte(early?0xbfe:0xc20)&128)},{"pitch_ticks",word(early?0xa2e:0xa38)},
      {"authentication_inhibit",bool(byte(early?0xd08:0xd21)&1)},{"authentication_complete",bool(byte(early?0xd06:0xd1f)&128)},
      {"lean_sensor_fault",bool(byte(early?0x8b1:0x8b3)&16)},{"sidestand_inhibit",bool(byte(0x88c)&128)},
      {"faults",faults},{"output_transitions",{{"3",outputs[3]},{"6",outputs[6]},{"7",outputs[7]}}},
      {"trace",events},{"storage",storage_origin},{"transcript",Json(transcript.end()-std::min<size_t>(30,transcript.size()),transcript.end())}};
  }
};
