export class BufferedPlayer {
  constructor({context,tracks,duration,fetchWindow,createChain,onSources,onError,onProgress}){
    Object.assign(this,{context,tracks,duration,fetchWindow,createChain,onSources,onError,onProgress});
    this.cache=new Map();this.controllers=new Map();this.nodes=[];this.generation=0;this.windowSeconds=30;
    this.controller=new AbortController();this.timer=null;this.active=false;
  }
  async window(index){
    if(!this.cache.has(index)){
      const controller=new AbortController();this.controllers.set(index,controller);
      const promise=(async()=>{
        const result=new Map();
        for(const track of this.tracks){
          if(controller.signal.aborted)throw new DOMException('Aborted','AbortError');
          const buffer=await this.fetchWindow(track,index,controller.signal);
          if(controller.signal.aborted)throw new DOMException('Aborted','AbortError');
          result.set(track.family,buffer);this.onProgress?.(index,result.size,track);
        }
        return result;
      })();
      this.cache.set(index,promise);
      promise.catch(()=>{if(this.cache.get(index)===promise)this.cache.delete(index)});
    }
    return this.cache.get(index);
  }
  prepare(position=0){return this.window(Math.floor(position/this.windowSeconds))}
  stop(){
    this.generation++;this.active=false;clearTimeout(this.timer);
    for(const item of this.nodes){try{item.source.stop()}catch{}item.source.disconnect();item.gain.disconnect()}
    this.nodes=[];this.onSources([]);
  }
  dispose(){this.stop();this.controller.abort();for(const c of this.controllers.values())c.abort();this.controllers.clear();this.cache.clear()}
  schedule(buffers,index,start,offset=0){
    for(const track of this.tracks){
      const item=this.createChain(track,buffers.get(track.family));
      item.windowIndex=index;this.nodes.push(item);item.source.start(start,offset);
    }
    this.onSources(this.nodes);
  }
  async start(position){
    this.stop();const ticket=this.generation;
    const index=Math.floor(position/this.windowSeconds);
    for(const key of this.cache.keys())if(key!==index&&key!==index+1){this.controllers.get(key)?.abort();this.controllers.delete(key);this.cache.delete(key)}
    const buffers=await this.window(index);
    if(ticket!==this.generation)return false;
    await this.context.resume();if(ticket!==this.generation)return false;
    const start=this.context.currentTime+.08;
    this.origin=start-position;this.active=true;
    this.schedule(buffers,index,start,position-index*this.windowSeconds);
    this.advance(index,ticket);return true;
  }
  async advance(index,ticket){
    const next=index+1,boundary=next*this.windowSeconds;
    if(boundary>=this.duration)return;
    try{
      const buffers=await this.window(next);
      if(ticket!==this.generation)return;
      const when=this.origin+boundary;
      if(when<this.context.currentTime+.02)throw Error('다음 구간을 준비하는 데 시간이 걸립니다. 재생을 다시 눌러 주세요.');
      this.schedule(buffers,next,when);
      this.timer=setTimeout(()=>{
        if(ticket!==this.generation)return;
        // Disconnect finished sources and keep only the current and next windows.
        this.nodes=this.nodes.filter(item=>{
          if(item.windowIndex>=next)return true;
          item.source.disconnect();item.gain.disconnect();return false;
        });
        this.onSources(this.nodes);
        for(const key of this.cache.keys())if(key!==next&&key!==next+1){this.controllers.get(key)?.abort();this.controllers.delete(key);this.cache.delete(key)}
        this.advance(next,ticket);
      },Math.max(0,(when-this.context.currentTime+.03)*1000));
    }catch(error){if(ticket===this.generation&&error.name!=='AbortError')this.onError(error)}
  }
}
