(() => {
  "use strict";
  function rewrite(){
    document.querySelectorAll("#cotIntelligence .cot-intel-head p").forEach(node=>{
      if((node.textContent||"").includes("Tuesday positions become usable only after the Friday public release.")) node.textContent="CFTC positions become usable only after their documented or scheduled public availability timestamp.";
    });
    document.querySelectorAll("#cotIntelligence .cot-intel-strip span").forEach(node=>{
      const text=node.textContent||"";
      if(text.startsWith("Tuesday snapshot")){const b=node.querySelector("b");node.childNodes[0].textContent="CFTC as-of ";if(b)b.textContent=b.textContent;}
      if(text.startsWith("Friday availability")){const b=node.querySelector("b");node.childNodes[0].textContent="Public availability ";if(b)b.textContent=b.textContent;}
    });
    document.querySelectorAll("#cotIntelligence .cot-empty").forEach(node=>{
      if((node.textContent||"").includes("OOS-supported percentile threshold")) node.textContent=node.textContent.replace("OOS-supported percentile threshold","release-corrected governed percentile threshold");
    });
  }
  const observer=new MutationObserver(rewrite);
  function start(){rewrite();observer.observe(document.documentElement,{subtree:true,childList:true});}
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start,{once:true});else start();
})();
