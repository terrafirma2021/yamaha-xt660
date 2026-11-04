// SPDX-License-Identifier: GPL-2.0-or-later
// Single-owner worker API. Only explicit tick/control calls execute instructions.
#include "cockpit_native.hpp"
#include <emscripten.h>

namespace {
std::unique_ptr<NativeCockpit> bike;
Json records=Json::object(),images=Json::array();
std::string result;
Json state() {
  require(bool(bike),"Initialize the emulator first");
  Json s=bike->engine?bike->engine->snapshot():Json::object();
  s.update({{"loaded",bool(bike->engine)},{"images",images},{"bike",bike->state()}});return s;
}
template<class F> const char* reply(F operation) {
  try{result=operation().dump();}
  catch(const std::exception& e){result=Json({{"error",e.what()}}).dump();}
  return result.c_str();
}
}
extern "C" {
EMSCRIPTEN_KEEPALIVE const char* xt_init() {return reply([] {
  require(!bike,"Emulator already initialized");
  require(sha256({})=="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","SHA-256 empty vector");
  require(sha256({'a','b','c'})=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad","SHA-256 abc vector");
  auto registry=Json::parse(read_bytes("/data/firmware/registry.json"));
  for(const auto& row:registry["images"]) {
    auto bytes=read_bytes(fs::path("/data")/row.at("file").get<std::string>());
    require(sha256(bytes)==row["sha256"],"Registered BIN hash mismatch");
    unsigned base=row.at("base_address");
    if(base+bytes.size()!=65536||bytes[bytes.size()-2]!=0xf8||bytes.back()!=0||bytes[0xf7a0-base]!=6)continue;
    records[row.at("id").get<std::string>()]=row;
    images.push_back({{"id",row["id"]},{"label",row["label"].get<std::string>()+" · "+row["variant"].get<std::string>()}});
  }
  require(images.size()==5,"Expected five complete BINs");bike=std::make_unique<NativeCockpit>("/data");return state();
});}
EMSCRIPTEN_KEEPALIVE const char* xt_state(){return reply([]{return state();});}
EMSCRIPTEN_KEEPALIVE double xt_cycles(){return bike&&bike->engine?double(bike->engine->cycles()):0;}
EMSCRIPTEN_KEEPALIVE const char* xt_tick(){return reply([] {
  require(bool(bike),"Initialize first");bike->tick();return Json();
});}
EMSCRIPTEN_KEEPALIVE const char* xt_action(const char* message){return reply([&] {
  require(bool(bike),"Initialize first");auto d=Json::parse(message);auto a=d.at("action").get<std::string>();
  if(a=="load") {
    auto id=d.at("image").get<std::string>();require(records.contains(id),"Select a complete registered BIN");bike->select(records[id]);
  }else if(a=="key")bike->power(bool_value(d.at("enabled")),bool_value(d.value("wrong_key",Json(false))));
  else if(a=="control")bike->control(d.at("name"),d.at("value"));
  else if(a=="start")bike->start();
  else if(a=="diagnostics")bike->diagnostics(bool_value(d.at("enabled")));
  else if(a=="diagnostic-item")bike->diagnostic_item(integer(d.at("number"),61,62));
  else if(a=="diagnostic-test")bike->diagnostic_test(bool_value(d.at("enabled")));
  else if(a=="diagnostic-next")bike->diagnostic_next(integer(d.at("direction"),-1,1));
  else if(a=="clear-history")bike->clear_history();
  else {
    require(bool(bike->engine),"Key is off");auto& e=*bike->engine;
    if(a=="tick")bike->tick();
    else if(a=="adc")e.set_adc(integer(d.at("channel"),0,7),integer(d.at("value"),0,1023));
    else if(a=="verify")e.verify();
    else if(a=="storage-export")return Json(e.storage());
    else if(a=="trace-export") {
      Json rows=Json::array();for(const auto& event:e.trace)rows.push_back({event.cycle,event.kind,event.channel,event.value,event.pc});return rows;
    }else throw std::invalid_argument("Unknown control");
  }
  return state();
});}
}
