// SPDX-License-Identifier: GPL-2.0-or-later
// Windows process owns MCU time. HTTP serves snapshots and queues controls only.
#include "httplib.h"
#include "cockpit_native.hpp"
#include <condition_variable>
#include <future>
#include <iostream>
#include <mutex>
#include <thread>
#include <shellapi.h>

class NativeRuntime {
  struct Command {Json data;std::promise<Json> reply;};
  std::mutex mutex;
  std::condition_variable wake;
  std::deque<std::shared_ptr<Command>> commands;
  std::thread worker;
  bool quitting=false,paused=true;
  Json cached,records=Json::object(),images=Json::array();
  NativeCockpit bike;
  Clock::time_point anchor=Clock::now();
  uint64_t anchor_cycles=0;
  double ratio=0,late=0;
  std::string error;
  void reanchor() {anchor=Clock::now();anchor_cycles=bike.engine?bike.engine->cycles():0;ratio=0;late=0;}
  void publish() {
    Json s=bike.engine?bike.engine->snapshot():Json::object();
    s.update({{"loaded",bool(bike.engine)},{"images",images},{"error",error},{"bike",bike.state()},
      {"runtime",{{"native",true},{"paused",paused},{"clock_hz",16000000},{"realtime_ratio",ratio},{"behind_ms",late},
        {"timing_profile","Nominal 16 MHz; physical oscillator unconfirmed"},{"independent",true}}}});
    std::lock_guard<std::mutex> guard(mutex);cached=std::move(s);
  }
  void action(const Json& d) {
    require(d.is_object(),"Expected a control object");std::string a=d.at("action").get<std::string>();
    if(a=="load") {
      std::string id=d.at("image").get<std::string>();require(records.contains(id),"Select a complete registered BIN");
      bike.select(records[id]);paused=true;error.clear();reanchor();
    } else if(a=="key") {
      bool enabled=bool_value(d.at("enabled"));bike.power(enabled,bool_value(d.value("wrong_key",Json(false))));
      paused=!enabled;error.clear();reanchor();
    } else if(a=="control")bike.control(d.at("name"),d.at("value"));
    else if(a=="start") {bike.start();if(paused){paused=false;reanchor();}}
    else if(a=="pause") {paused=bool_value(d.at("paused"));reanchor();}
    else if(a=="diagnostics") {bike.diagnostics(bool_value(d.at("enabled")));paused=false;error.clear();reanchor();}
    else if(a=="diagnostic-item")bike.diagnostic_item(integer(d.at("number"),61,62));
    else if(a=="diagnostic-test")bike.diagnostic_test(bool_value(d.at("enabled")));
    else if(a=="diagnostic-next")bike.diagnostic_next(integer(d.at("direction"),-1,1));
    else if(a=="clear-history")bike.clear_history();
    else {
      require(bool(bike.engine),"Key is off");auto& e=*bike.engine;
      if(a=="tick"||a=="step") {
        require(paused,"Pause before single stepping");
        if(a=="tick")bike.tick();else e.step(integer(d.value("instructions",Json(100000)),1,1000000));reanchor();
      } else if(a=="adc")e.set_adc(integer(d.at("channel"),0,7),integer(d.at("value"),0,1023));
      else if(a=="verify")e.verify();
      else if(a=="storage-export")return;
      else if(a=="trace-export")return;
      else throw std::invalid_argument("Unknown control");
    }
  }
  void loop() {
    publish();
    for(;;) {
      std::shared_ptr<Command> command;
      {
        std::unique_lock<std::mutex> guard(mutex);
        if(commands.empty()&&!quitting) {
          if(paused||!bike.engine)wake.wait(guard,[&]{return quitting||!commands.empty();});
          else {
            auto deadline=anchor+std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(double(bike.engine->cycles()-anchor_cycles)/16000000));
            wake.wait_until(guard,deadline,[&]{return quitting||!commands.empty();});
          }
        }
        if(quitting)break;
        if(!commands.empty()){command=commands.front();commands.pop_front();}
      }
      if(command) {
        try {
          action(command->data);publish();auto name=command->data.value("action","");
          if(name=="storage-export")command->reply.set_value(bike.engine->storage());
          else if(name=="trace-export") {
            Json rows=Json::array();for(const auto& e:bike.engine->trace)rows.push_back({e.cycle,e.kind,e.channel,e.value,e.pc});command->reply.set_value(rows);
          }else command->reply.set_value(state());
        }catch(const std::invalid_argument&){command->reply.set_exception(std::current_exception());}
        catch(const Json::exception&){command->reply.set_exception(std::current_exception());}
        catch(const std::exception& ex){error=ex.what();paused=true;publish();command->reply.set_exception(std::current_exception());}
      }else if(!paused&&bike.engine) {
        try {
          bike.tick();double wall=std::chrono::duration<double>(Clock::now()-anchor).count();
          double sim=double(bike.engine->cycles()-anchor_cycles)/16000000;
          ratio=wall>.5?sim/wall:0;late=std::max(0.0,(wall-sim)*1000);publish();
        }catch(const std::exception& ex){error=ex.what();paused=true;publish();}
      }
    }
    bike.power(false);
  }
public:
  explicit NativeRuntime(fs::path root,std::string initial="",std::vector<unsigned char> fixture={}):bike(root) {
    auto registry=Json::parse(read_bytes(root/"firmware/registry.json"));
    for(const auto& row:registry["images"]) {
      auto b=read_bytes(root/row.at("file").get<std::string>());unsigned base=row.at("base_address");
      if(base+b.size()!=65536||b[b.size()-2]!=0xf8||b.back()!=0||b[0xf7a0-base]!=6)continue;
      if(sha256(b)!=row["sha256"])throw std::runtime_error("Registered BIN hash mismatch");
      records[row.at("id").get<std::string>()]=row;
      images.push_back({{"id",row["id"]},{"label",row["label"].get<std::string>()+" · "+row["variant"].get<std::string>()}});
    }
    if(!initial.empty()) {
      require(records.contains(initial),"Initial image must have complete boot code");
      require(fixture.empty()||fixture.size()==512,"Storage fixture must contain 512 bytes");
      bike.select(records[initial]);bike.storage=std::move(fixture);
    }else require(fixture.empty(),"Choose --image with --storage");
    publish();worker=std::thread([this]{loop();});
  }
  ~NativeRuntime() {{std::lock_guard<std::mutex> guard(mutex);quitting=true;}wake.notify_all();worker.join();}
  Json state(){std::lock_guard<std::mutex> guard(mutex);return cached;}
  Json request(Json d) {
    auto c=std::make_shared<Command>();c->data=std::move(d);auto result=c->reply.get_future();
    {std::lock_guard<std::mutex> guard(mutex);require(commands.size()<16,"Control queue is full");commands.push_back(c);}wake.notify_all();return result.get();
  }
};

int main(int argc,char**argv) {try {
  wchar_t executable[32768];GetModuleFileNameW(nullptr,executable,32768);
  fs::path root=fs::path(executable).parent_path(),storage_path;int port=8766;bool open_browser=true;std::string initial;
  for(int i=1;i<argc;++i) {
    std::string a=argv[i];if(a=="--root"&&i+1<argc)root=fs::absolute(argv[++i]);
    else if(a=="--port"&&i+1<argc)port=std::stoi(argv[++i]);
    else if(a=="--no-browser")open_browser=false;
    else if(a=="--image"&&i+1<argc)initial=argv[++i];
    else if(a=="--storage"&&i+1<argc)storage_path=argv[++i];
    else throw std::invalid_argument("Usage: XT660.Emulator.exe [--root folder] [--port 8766] [--no-browser] [--image ID --storage fixture.bin]");
  }
  require(port>=1024&&port<=65535,"Port must be 1024..65535");
  unsigned char nonce[32];if(BCryptGenRandom(nullptr,nonce,32,BCRYPT_USE_SYSTEM_PREFERRED_RNG)<0)throw std::runtime_error("Session token generation failed");
  std::string token;for(auto b:nonce)token+=hexbyte(b);
  NativeRuntime runtime(root,initial,storage_path.empty()?std::vector<unsigned char>{}:read_bytes(storage_path));httplib::Server server;
  server.new_task_queue=[] {return new httplib::ThreadPool(4);};server.set_payload_max_length(4096);
  std::string host="127.0.0.1:"+std::to_string(port),origin="http://"+host;
  server.set_default_headers({{"Cache-Control","no-store"},{"X-Content-Type-Options","nosniff"},
    {"Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"}});
  server.set_pre_routing_handler([&](const httplib::Request& req,httplib::Response& res) {
    if(req.get_header_value("Host")!=host) {res.status=403;res.set_content("Use the loopback URL printed at startup","text/plain");return httplib::Server::HandlerResponse::Handled;}
    return httplib::Server::HandlerResponse::Unhandled;
  });
  std::map<std::string,std::pair<fs::path,std::string>> assets={
    {"/",{root/"emulator/web/dashboard.html","text/html; charset=utf-8"}},
    {"/dashboard.js",{root/"emulator/web/dashboard.js","text/javascript; charset=utf-8"}},
    {"/dashboard.css",{root/"emulator/web/dashboard.css","text/css"}},
    {"/logo.png",{root/"site/assets/yamaha-motor-logo.png","image/png"}},
    {"/cockpit.png",{root/"emulator/web/cockpit.png","image/png"}},
    {"/ignition-key.png",{root/"emulator/web/ignition-key.png","image/png"}}};
  server.Get("/.*",[&](const httplib::Request& req,httplib::Response& res) {
    if(auto it=assets.find(req.path);it!=assets.end()) {
      auto b=read_bytes(it->second.first);std::string content(b.begin(),b.end());
      if(req.path=="/"){auto at=content.find("{{TOKEN}}");require(at!=std::string::npos,"Dashboard session token missing");content.replace(at,9,token);}
      res.set_content(content,it->second.second);return;
    }
    if(req.path=="/api/state"){res.set_content(runtime.state().dump(),"application/json");return;}
    if(req.path=="/storage.bin") {
      auto b=runtime.request({{"action","storage-export"}}).get<std::vector<unsigned char>>();
      res.set_content(reinterpret_cast<const char*>(b.data()),b.size(),"application/octet-stream");return;
    }
    if(req.path=="/trace.csv") {
      auto rows=runtime.request({{"action","trace-export"}});std::ostringstream csv;csv<<"cycle,kind,channel,value,pc\n";
      for(const auto& r:rows)csv<<r[0]<<','<<r[1].get<std::string>()<<','<<r[2]<<','<<r[3]<<','<<r[4]<<'\n';res.set_content(csv.str(),"text/csv");return;
    }
    res.status=404;res.set_content("Not found","text/plain");
  });
  server.Post("/api/action",[&](const httplib::Request& req,httplib::Response& res) {
    auto from=req.get_header_value("Origin");
    if((!from.empty()&&from!=origin)||req.get_header_value("X-XT660-Token")!=token) {res.status=403;res.set_content("{\"error\":\"Invalid local session\"}","application/json");return;}
    try{res.set_content(runtime.request(Json::parse(req.body)).dump(),"application/json");}
    catch(const std::invalid_argument& e){res.status=400;res.set_content(Json({{"error",e.what()}}).dump(),"application/json");}
    catch(const Json::exception& e){res.status=400;res.set_content(Json({{"error",e.what()}}).dump(),"application/json");}
  });
  server.set_exception_handler([](const auto&,auto& res,std::exception_ptr error) {
    std::string message="Runtime error";try{std::rethrow_exception(error);}catch(const std::exception&e){message=e.what();}
    res.status=500;res.set_content(Json({{"error",message}}).dump(),"application/json");
  });
  require(server.bind_to_port("127.0.0.1",port),"Cannot bind local port; another simulator may already be running");
  std::cout<<"XT660 native emulator\n"<<origin<<"/\nThe MCU runs independently of the browser. Close this process to stop it.\n"<<std::flush;
  if(open_browser)ShellExecuteA(nullptr,"open",(origin+"/").c_str(),nullptr,nullptr,SW_SHOWNORMAL);
  server.listen_after_bind();return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 1;}}
